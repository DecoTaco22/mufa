"""Respaldos: versión nueva solo si cambia la configuración, diferencias y permisos."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mufa.db import Respaldo
from mufa.marcas.mikrotik import MikroTik
from mufa.permisos import Rol
from tests.conftest import CrearUsuario
from tests.ssh_falso import ServidorSSHFalso

API = "/api/v1"

CONFIG = """# 2026-10-05 02:00:00 by RouterOS 7.16
# software id = ABCD-1234
/ip dns
set allow-remote-requests=no servers=8.8.8.8
/system identity
set name=nodo-norte
"""


class RouterConConfig:
    """Un router falso cuya configuración se puede cambiar entre respaldos."""

    def __init__(self) -> None:
        self.config = CONFIG
        self.servidor = ServidorSSHFalso(self._responder)

    def _responder(self, comando: str) -> str:
        return self.config if comando.startswith("/export") else ""


@pytest.fixture
def router() -> Iterator[RouterConConfig]:
    falso = RouterConConfig()
    yield falso
    falso.servidor.cerrar()


def _crear_equipo(cliente: TestClient, admin: dict[str, str], puerto: int) -> int:
    equipo = {
        "nombre": "Nodo Norte",
        "marca": "mikrotik",
        "ip_gestion": "127.0.0.1",
        "puerto_ssh": puerto,
        "usuario_ssh": "mufa",
        "password_ssh": "clave-correcta",
    }
    respuesta = cliente.post(f"{API}/equipos", json=equipo, headers=admin)
    assert respuesta.status_code == 201, respuesta.text
    return int(respuesta.json()["id"])


def test_la_fecha_del_export_no_cuenta_como_cambio() -> None:
    otra_fecha = CONFIG.replace("2026-10-05 02:00:00", "2026-10-06 02:00:00")
    adaptador = MikroTik()
    assert adaptador.normalizar_respaldo(CONFIG) == adaptador.normalizar_respaldo(otra_fecha)
    assert "software id" in adaptador.normalizar_respaldo(CONFIG)


def test_respaldo_versiones_y_diferencias(
    cliente: TestClient, admin: dict[str, str], router: RouterConConfig
) -> None:
    equipo_id = _crear_equipo(cliente, admin, router.servidor.puerto)

    primero = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).json()
    assert primero["cambio"] is True
    # Con contraseñas y claves: el respaldo sirve para restaurar el equipo.
    assert router.servidor.comandos == ["/export show-sensitive"]

    # Mismo contenido, otra fecha en la cabecera: no se duplica.
    router.config = CONFIG.replace("2026-10-05 02:00:00", "2026-10-06 02:00:00")
    segundo = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).json()
    assert segundo["cambio"] is False
    assert segundo["respaldo"]["id"] == primero["respaldo"]["id"]

    # Alguien abrió el DNS: versión nueva y la diferencia lo muestra.
    router.config = router.config.replace("allow-remote-requests=no", "allow-remote-requests=yes")
    tercero = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).json()
    assert tercero["cambio"] is True

    versiones = cliente.get(f"{API}/equipos/{equipo_id}/respaldos", headers=admin).json()
    assert [v["id"] for v in versiones] == [tercero["respaldo"]["id"], primero["respaldo"]["id"]]

    diff = cliente.get(
        f"{API}/respaldos/{tercero['respaldo']['id']}/diferencias", headers=admin
    ).json()
    assert "-set allow-remote-requests=no servers=8.8.8.8" in diff["diferencias"]
    assert "+set allow-remote-requests=yes servers=8.8.8.8" in diff["diferencias"]
    assert "by RouterOS" not in diff["diferencias"]

    contenido = cliente.get(f"{API}/respaldos/{tercero['respaldo']['id']}", headers=admin).json()
    assert "allow-remote-requests=yes" in contenido["contenido"]


def test_respaldo_se_guarda_cifrado(
    cliente: TestClient, admin: dict[str, str], router: RouterConConfig
) -> None:
    equipo_id = _crear_equipo(cliente, admin, router.servidor.puerto)
    cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin)
    with cliente.app.state.mufa.sesiones() as db:  # type: ignore[attr-defined]
        respaldo = db.scalar(select(Respaldo))
        assert respaldo is not None
        assert "nodo-norte" not in respaldo.contenido_cifrado


def test_lector_ve_la_lista_pero_no_el_contenido(
    cliente: TestClient,
    admin: dict[str, str],
    crear_usuario: CrearUsuario,
    router: RouterConConfig,
) -> None:
    equipo_id = _crear_equipo(cliente, admin, router.servidor.puerto)
    respaldo = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).json()
    lector = crear_usuario("lector", Rol.LECTURA)
    assert cliente.get(f"{API}/equipos/{equipo_id}/respaldos", headers=lector).status_code == 200
    respaldo_id = respaldo["respaldo"]["id"]
    assert cliente.get(f"{API}/respaldos/{respaldo_id}", headers=lector).status_code == 403
    assert cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=lector).status_code == 403


def test_respaldo_fallido_responde_502_y_queda_registrado(
    cliente: TestClient, admin: dict[str, str], router: RouterConConfig
) -> None:
    equipo_id = _crear_equipo(cliente, admin, router.servidor.puerto)
    cliente.patch(f"{API}/equipos/{equipo_id}", json={"password_ssh": "clave-mala"}, headers=admin)
    assert cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).status_code == 502
    eventos = cliente.get(f"{API}/eventos", headers=admin).json()
    assert any(e["accion"] == "respaldo.error" for e in eventos)


def test_marca_sin_adaptador_no_se_respalda(cliente: TestClient, admin: dict[str, str]) -> None:
    equipo = {"nombre": "OLT Sur", "marca": "otra", "ip_gestion": "10.0.0.2", "usuario_ssh": "x"}
    equipo_id = cliente.post(f"{API}/equipos", json=equipo, headers=admin).json()["id"]
    respuesta = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin)
    assert respuesta.status_code == 422
    assert "SNMP" in respuesta.json()["detail"]


def test_buscar_en_las_configuraciones(cliente: TestClient, admin: dict[str, str]) -> None:
    from mufa.db import Equipo, Respaldo

    estado = cliente.app.state.mufa  # type: ignore[attr-defined]

    def respaldo(db, equipo: Equipo, texto: str) -> None:  # type: ignore[no-untyped-def]
        db.add(
            Respaldo(
                equipo_id=equipo.id,
                origen="manual",
                hash_normalizado=str(hash(texto)),
                tamano=len(texto),
                contenido_cifrado=estado.cifrador.cifrar(texto),
            )
        )
        db.flush()

    with estado.sesiones() as db:
        core = Equipo(nombre="CORE", marca="cisco", ip_gestion="10.0.0.1")
        borde = Equipo(nombre="BORDE", marca="mikrotik", ip_gestion="10.0.0.2")
        db.add_all([core, borde])
        db.flush()
        respaldo(
            db, core, "hostname CORE\nrouter bgp 65000\n neighbor 198.51.100.1 remote-as 65001\nend"
        )
        respaldo(
            db, core, "hostname CORE\nrouter bgp 65000\n neighbor 203.0.113.1 remote-as 65002\nend"
        )
        respaldo(db, borde, "/ip address\nadd address=203.0.113.10/30 interface=sfp1")
        db.commit()

    r = cliente.get(f"{API}/respaldos/buscar", params={"q": "203.0.113.1"}, headers=admin)
    assert r.status_code == 200, r.text
    encontrados = r.json()
    assert [(e["equipo"], e["lineas"][0]["numero"]) for e in encontrados] == [
        ("BORDE", 2),
        ("CORE", 3),
    ]
    # La IP vieja ya no está en la última versión... pero sí en el historial.
    assert (
        cliente.get(f"{API}/respaldos/buscar", params={"q": "198.51.100.1"}, headers=admin).json()
        == []
    )
    historial = cliente.get(
        f"{API}/respaldos/buscar", params={"q": "198.51.100.1", "todas": True}, headers=admin
    ).json()
    assert [e["equipo"] for e in historial] == ["CORE"]
    assert (
        cliente.get(f"{API}/respaldos/buscar", params={"q": "x"}, headers=admin).status_code == 422
    )
