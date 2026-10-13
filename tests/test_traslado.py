"""Llevar mufa a otra computadora: exportar en una, importar en otra sin usuarios."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mufa import primera_vez
from mufa.api import crear_app
from mufa.config import Ajustes
from mufa.db import Equipo
from tests.conftest import PASSWORD

API = "/api/v1"
FRASE = "una frase para el traslado"


def _otra_computadora(tmp_path: Path, ajustes: Ajustes) -> Ajustes:
    datos = tmp_path / "otra"
    return Ajustes(
        dir_datos=datos,
        url_base_datos=f"sqlite:///{(datos / 'mufa.db').as_posix()}",
        exigir_dos_pasos=ajustes.exigir_dos_pasos,
        intervalo_sondeo_minutos=0,
        intervalo_respaldo_horas=0,
        enviar_alertas=False,
    )


def _exportar(cliente: TestClient, admin: dict[str, str]) -> tuple[str, str]:
    respuesta = cliente.post(
        f"{API}/sistema/exportar", json={"password": PASSWORD, "frase": FRASE}, headers=admin
    )
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["nombre"].endswith(".mufa")
    return datos["nombre"], datos["contenido"]


def _importar(cliente: TestClient, contenido: str, frase: str = FRASE, token: str | None = None):  # type: ignore[no-untyped-def]
    token = token if token is not None else cliente.app.state.mufa.token_inicial  # type: ignore[attr-defined]
    return cliente.post(
        f"{API}/sistema/importar",
        data={"frase": frase, "token": token or ""},
        files={"archivo": ("mufa.mufa", contenido.encode("ascii"), "text/plain")},
    )


def test_la_cuenta_y_los_equipos_pasan_a_otra_computadora(
    cliente: TestClient, admin: dict[str, str], ajustes: Ajustes, tmp_path: Path
) -> None:
    creado = cliente.post(
        f"{API}/equipos",
        json={
            "nombre": "core-1",
            "marca": "mikrotik",
            "ip_gestion": "192.0.2.1",
            "usuario_ssh": "lectura",
            "password_ssh": "clave-del-equipo",
        },
        headers=admin,
    )
    assert creado.status_code == 201, creado.text
    (ajustes.dir_datos / "known_hosts").write_text("[192.0.2.1]:22 ssh-ed25519 AAAA\n")
    _, contenido = _exportar(cliente, admin)
    # El archivo no deja ver nada sin la frase.
    assert "core-1" not in contenido and "admin" not in contenido

    otra = _otra_computadora(tmp_path, ajustes)
    with TestClient(crear_app(otra)) as nueva:
        assert nueva.get(f"{API}/sistema/inicial").json() == {
            "necesita_admin": True,
            "puede_importar": True,
        }
        assert _importar(nueva, contenido, frase="otra frase cualquiera").status_code == 422
        assert _importar(nueva, contenido, token="no-es-el-token").status_code == 403
        importado = _importar(nueva, contenido)
        assert importado.status_code == 201, importado.text
        assert importado.json() == {"usuarios": 1}
        assert not primera_vez.archivo_token(otra.dir_datos).exists()
        assert (otra.dir_datos / "known_hosts").read_text() == "[192.0.2.1]:22 ssh-ed25519 AAAA\n"

        # Se entra con la misma cuenta, y las credenciales se descifran con la clave que viajó.
        login = nueva.post(f"{API}/auth/login", json={"usuario": "admin", "password": PASSWORD})
        assert login.status_code == 200, login.text
        estado = nueva.app.state.mufa  # type: ignore[attr-defined]
        with estado.sesiones() as db:
            equipo = db.query(Equipo).one()
            assert estado.cifrador.descifrar(equipo.password_cifrada) == "clave-del-equipo"

        # Con cuentas ya creadas, no se puede importar encima.
        assert _importar(nueva, contenido, token="").status_code == 409


def test_exportar_pide_la_contrasena_y_solo_admin(
    cliente: TestClient,
    admin: dict[str, str],
    crear_usuario,  # type: ignore[no-untyped-def]
) -> None:
    from mufa.permisos import Rol

    malo = cliente.post(
        f"{API}/sistema/exportar",
        json={"password": "no-es-la-clave", "frase": FRASE},
        headers=admin,
    )
    assert malo.status_code == 400
    corta = cliente.post(
        f"{API}/sistema/exportar", json={"password": PASSWORD, "frase": "corta"}, headers=admin
    )
    assert corta.status_code == 422
    senior = crear_usuario("senior", Rol.SENIOR)
    prohibido = cliente.post(
        f"{API}/sistema/exportar", json={"password": PASSWORD, "frase": FRASE}, headers=senior
    )
    assert prohibido.status_code == 403


def test_archivo_que_no_es_de_mufa(cliente: TestClient) -> None:
    respuesta = _importar(cliente, "hola\nesto no es\nun traslado\n")
    assert respuesta.status_code == 422
    assert "no es un archivo de traslado" in respuesta.json()["detail"]
