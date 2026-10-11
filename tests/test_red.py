"""Datos por SNMP, interfaces vigiladas, importación al IPAM y VLANs, "¿dónde está?",
explorador SNMP, caja de herramientas y límites del plan gratis."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from mufa import herramientas, importacion, monitoreo, snmp
from mufa.db import DireccionIP, DominioL2, Equipo, Evento, Prefijo
from mufa.marcas.mikrotik import vlans_desde_texto
from mufa.permisos import Rol
from tests.api_routeros_falsa import MENUS, PASSWORD, ApiRouterOSFalsa
from tests.conftest import CrearUsuario
from tests.snmp_falso import CLAVE_AUTH, CLAVE_PRIV, USUARIO, AgenteSNMPFalso

API = "/api/v1"


def _snmp_v3(puerto: int = 161) -> dict[str, object]:
    return {
        "version": "3",
        "puerto": puerto,
        "usuario": USUARIO,
        "clave_auth": CLAVE_AUTH,
        "clave_priv": CLAVE_PRIV,
        "protocolo_auth": "sha",
        "protocolo_priv": "aes",
    }


def _crear(cliente: TestClient, admin: dict[str, str], nombre: str = "CCR", **extra: object) -> int:
    equipo = {
        "nombre": nombre,
        "marca": "mikrotik",
        "ip_gestion": "127.0.0.1",
        "snmp": _snmp_v3(),
        **extra,
    }
    respuesta = cliente.post(f"{API}/equipos", json=equipo, headers=admin)
    assert respuesta.status_code == 201, respuesta.text
    return int(respuesta.json()["id"])


class Reloj:
    def __init__(self) -> None:
        self.momento = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.momento

    def avanzar(self, minutos: int) -> None:
        self.momento += timedelta(minutes=minutos)


@pytest.fixture
def reloj(monkeypatch: pytest.MonkeyPatch) -> Reloj:
    reloj = Reloj()
    monkeypatch.setattr(monitoreo, "ahora", reloj)
    return reloj


class EquipoSimulado:
    """Lo que devolvería un sondeo SNMP, editable entre sondeos."""

    def __init__(self) -> None:
        self.uptime = 1_000
        self.serie = "SERIE-A"
        self.operativa = True
        self.octetos = 0
        self.mbps_de_trafico = 0

    def avanzar(self, segundos: int) -> None:
        self.uptime += segundos
        self.octetos += self.mbps_de_trafico * 1_000_000 // 8 * segundos

    def __call__(
        self, _host: str, _cred: snmp.CredencialesSNMP, _timeout: float
    ) -> snmp.ResultadoSondeo:
        return snmp.ResultadoSondeo(
            nombre="MK_CORE",
            descripcion="RouterOS CCR1009-7G-1C-1S+",
            object_id="1.3.6.1.4.1.14988.1",
            uptime_segundos=self.uptime,
            marca_detectada="mikrotik",
            interfaces=[
                snmp.Interfaz(7, "sfp-uplink", self.operativa, 1_000, self.octetos, self.octetos)
            ],
            ubicacion="Core Caminero",
            serie=self.serie,
            modelo="CCR1009-7G-1C-1S+",
            version="6.48.6",
        )


def _sondear(cliente: TestClient, equipo_id: int, simulado: EquipoSimulado) -> None:
    estado_app = cliente.app.state.mufa  # type: ignore[attr-defined]
    with estado_app.sesiones() as db:
        equipo = db.get(Equipo, equipo_id)
        assert equipo is not None
        monitoreo.sondear_equipo(db, equipo, estado_app.cifrador, sondeo=simulado)
        db.commit()


def _eventos(cliente: TestClient, accion: str) -> list[Evento]:
    with cliente.app.state.mufa.sesiones() as db:  # type: ignore[attr-defined]
        return [e for e in db.query(Evento).all() if e.accion == accion]


# --- Datos por SNMP y reinicios


def test_datos_del_equipo_por_snmp(
    cliente: TestClient, admin: dict[str, str], reloj: Reloj
) -> None:
    equipo_id = _crear(cliente, admin)
    simulado = EquipoSimulado()
    _sondear(cliente, equipo_id, simulado)

    estado = cliente.get(f"{API}/equipos/{equipo_id}/estado", headers=admin).json()
    assert (estado["modelo"], estado["version"], estado["ubicacion"]) == (
        "CCR1009-7G-1C-1S+",
        "6.48.6",
        "Core Caminero",
    )
    # La ficha vacía se completa sola.
    equipo = cliente.get(f"{API}/equipos/{equipo_id}", headers=admin).json()
    assert (equipo["modelo"], equipo["numero_serie"]) == ("CCR1009-7G-1C-1S+", "SERIE-A")


def test_reinicio_y_cambio_de_serie(
    cliente: TestClient, admin: dict[str, str], reloj: Reloj
) -> None:
    equipo_id = _crear(cliente, admin)
    simulado = EquipoSimulado()
    _sondear(cliente, equipo_id, simulado)
    simulado.uptime = 60
    simulado.serie = "SERIE-B"
    _sondear(cliente, equipo_id, simulado)
    assert len(_eventos(cliente, "equipo.reinicio")) == 1
    cambio = _eventos(cliente, "equipo.cambio_serie")
    assert cambio and cambio[0].detalle == {"antes": "SERIE-A", "ahora": "SERIE-B"}


def test_version_de_la_descripcion() -> None:
    assert snmp._version_y_modelo_de_descripcion(
        "cisco", "Cisco IOS Software, C2960 Software, Version 15.2(4)E10, RELEASE"
    ) == ("15.2(4)E10", "")
    assert snmp._version_y_modelo_de_descripcion("mikrotik", "RouterOS RB4011") == ("", "RB4011")


# --- Interfaces vigiladas


def test_interfaz_caida_y_saturada(
    cliente: TestClient, admin: dict[str, str], reloj: Reloj
) -> None:
    equipo_id = _crear(cliente, admin)
    simulado = EquipoSimulado()
    _sondear(cliente, equipo_id, simulado)
    vigilada = cliente.post(
        f"{API}/equipos/{equipo_id}/vigiladas",
        json={"if_index": 7, "umbral_saturacion": 80, "minutos_saturacion": 15},
        headers=admin,
    )
    assert vigilada.status_code == 201, vigilada.text
    interfaces = cliente.get(f"{API}/equipos/{equipo_id}/interfaces", headers=admin).json()
    assert interfaces[0]["vigilada_id"] == vigilada.json()["id"]

    # Se cae y vuelve.
    simulado.operativa = False
    _sondear(cliente, equipo_id, simulado)
    simulado.operativa = True
    _sondear(cliente, equipo_id, simulado)
    assert len(_eventos(cliente, "interfaz.caida")) == 1
    assert len(_eventos(cliente, "interfaz.recuperada")) == 1

    # 900 Mbps en un puerto de 1 Gbps: 90 %. Avisa recién a los 15 minutos.
    simulado.mbps_de_trafico = 900
    for _ in range(3):
        reloj.avanzar(5)
        simulado.avanzar(300)
        _sondear(cliente, equipo_id, simulado)
    assert _eventos(cliente, "interfaz.saturada") == []
    reloj.avanzar(5)
    simulado.avanzar(300)
    _sondear(cliente, equipo_id, simulado)
    saturada = _eventos(cliente, "interfaz.saturada")
    assert len(saturada) == 1 and saturada[0].objeto == "CCR · sfp-uplink"
    # Un solo aviso mientras dure; otro cuando se normaliza.
    reloj.avanzar(5)
    simulado.avanzar(300)
    _sondear(cliente, equipo_id, simulado)
    assert len(_eventos(cliente, "interfaz.saturada")) == 1
    simulado.mbps_de_trafico = 100
    reloj.avanzar(5)
    simulado.avanzar(300)
    _sondear(cliente, equipo_id, simulado)
    assert len(_eventos(cliente, "interfaz.normal")) == 1


def test_plan_gratis_vigila_hasta_5_interfaces(
    cliente: TestClient, admin: dict[str, str], reloj: Reloj
) -> None:
    simulado = EquipoSimulado()
    for numero in range(6):
        equipo_id = _crear(cliente, admin, nombre=f"R{numero}")
        _sondear(cliente, equipo_id, simulado)
        respuesta = cliente.post(
            f"{API}/equipos/{equipo_id}/vigiladas", json={"if_index": 7}, headers=admin
        )
        if numero < 5:
            assert respuesta.status_code == 201, respuesta.text
    assert respuesta.status_code == 402
    assert "Pro" in respuesta.json()["detail"]


def test_plan_gratis_hasta_3_usuarios(cliente: TestClient, admin: dict[str, str]) -> None:
    codigos = []
    for numero in range(3):
        usuario = {
            "usuario": f"tecnico{numero}",
            "nombre": "T",
            "rol": "tecnico_n2",
            "password": "una-clave-de-tecnico",
        }
        codigos.append(cliente.post(f"{API}/usuarios", json=usuario, headers=admin).status_code)
    # El admin ya es uno: entran dos más.
    assert codigos == [201, 201, 402]


# --- Importación


def test_importar_direcciones(cliente: TestClient, admin: dict[str, str]) -> None:
    core = _crear(cliente, admin, nombre="CORE")
    otro = _crear(cliente, admin, nombre="OTRO")
    with cliente.app.state.mufa.sesiones() as db:  # type: ignore[attr-defined]
        db.add(Prefijo(prefijo="10.255.255.0/24", descripcion="loopbacks"))
        db.flush()
        db.add(
            DireccionIP(prefijo_id=db.query(Prefijo).one().id, ip="10.255.255.9", equipo_id=otro)
        )
        equipo = db.get(Equipo, core)
        assert equipo is not None
        leidas = [
            snmp.DireccionEnEquipo("10.20.0.1", 30, "sfp-uplink"),
            snmp.DireccionEnEquipo("10.255.255.1", 32, "loopback"),
            snmp.DireccionEnEquipo("10.255.255.9", 32, "lo2"),
            snmp.DireccionEnEquipo("127.0.0.1", 8, "lo"),
        ]
        resultado = importacion.importar_direcciones(db, equipo, leidas)
        db.commit()
    assert resultado.prefijos_creados == ["10.20.0.0/30"]
    assert resultado.nuevas == 2
    assert len(resultado.conflictos) == 1 and "OTRO" in resultado.conflictos[0]

    buscada = cliente.get(f"{API}/ipam/buscar", params={"ip": "10.255.255.1"}, headers=admin)
    asignacion = buscada.json()["asignacion"]
    assert (asignacion["equipo_id"], asignacion["interfaz"]) == (core, "loopback")
    # Volver a importar no duplica.
    with cliente.app.state.mufa.sesiones() as db:  # type: ignore[attr-defined]
        equipo = db.get(Equipo, core)
        assert equipo is not None
        segunda = importacion.importar_direcciones(db, equipo, leidas[:2])
    assert (segunda.nuevas, segunda.actualizadas) == (0, 2)

    # Cada red dice en qué equipo e interfaz está.
    prefijos = {
        p["prefijo"]: p["equipos"]
        for p in cliente.get(f"{API}/ipam/prefijos", headers=admin).json()
    }
    assert prefijos["10.20.0.0/30"] == ["CORE · sfp-uplink"]
    lista = cliente.get(f"{API}/ipam/prefijos", headers=admin).json()
    assert next(p for p in lista if p["prefijo"] == "10.20.0.0/30")["equipo"] == "CORE"
    assert "OTRO" in prefijos["10.255.255.0/24"]


def test_vlans_desde_export() -> None:
    texto = (
        "/interface vlan\n"
        "add interface=sfp-sfpplus1 name=vlan100-clientes vlan-id=100\n"
        'add interface=bonding1 name="vlan 200 gestion" vlan-id=200\n'
    )
    assert vlans_desde_texto(texto) == [
        snmp.VlanEnEquipo(100, "vlan100-clientes", "sfp-sfpplus1"),
        snmp.VlanEnEquipo(200, "vlan 200 gestion", "bonding1"),
    ]


@pytest.fixture
def router_con_vlans() -> Iterator[ApiRouterOSFalsa]:
    menus = {
        **MENUS,
        "/interface/vlan/print": [
            {".id": "*1", "name": "clientes", "vlan-id": "100", "interface": "ether2"},
            {".id": "*2", "name": "gestion", "vlan-id": "200", "interface": "ether2"},
        ],
    }
    falso = ApiRouterOSFalsa(menus)
    yield falso
    falso.cerrar()


def test_importar_vlans_por_la_api(
    cliente: TestClient, admin: dict[str, str], router_con_vlans: ApiRouterOSFalsa
) -> None:
    equipo_id = _crear(
        cliente,
        admin,
        acceso="api",
        puerto_ssh=router_con_vlans.puerto,
        usuario_ssh="mufa",
        password_ssh=PASSWORD,
    )
    with cliente.app.state.mufa.sesiones() as db:  # type: ignore[attr-defined]
        dominio = DominioL2(nombre="Red de acceso")
        db.add(dominio)
        db.commit()
        dominio_id = dominio.id
    cliente.post(
        f"{API}/vlans/dominios/{dominio_id}/vlans",
        json={"numero": 200, "nombre": "otra-cosa"},
        headers=admin,
    )

    resultado = cliente.post(
        f"{API}/equipos/{equipo_id}/importar/vlans",
        json={"dominio_id": dominio_id},
        headers=admin,
    ).json()
    assert (resultado["fuente"], resultado["nuevas"]) == ("API", 1)
    assert "se llama 'gestion'" in resultado["conflictos"][0]

    vlans = cliente.get(f"{API}/vlans/dominios/{dominio_id}/vlans", headers=admin).json()
    assert [(v["numero"], v["equipos"][0]["interfaz"]) for v in vlans] == [
        (100, "ether2"),
        (200, "ether2"),
    ]
    assert all(c == "/login" or c.endswith("/print") for c in router_con_vlans.comandos)


# --- ¿Dónde está? y explorador


def test_donde_esta(
    cliente: TestClient, admin: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _crear(cliente, admin, nombre="CORE")

    def vecinos(_host: str, _cred: snmp.CredencialesSNMP) -> list[snmp.Ubicacion]:
        return [
            snmp.Ubicacion("10.9.0.5", "AA:BB:CC:00:11:22", "vlan100", "arp"),
            snmp.Ubicacion("", "AA:BB:CC:00:11:22", "ether5", "bridge"),
        ]

    monkeypatch.setattr(snmp, "leer_vecinos", vecinos)
    por_mac = cliente.get(f"{API}/donde", params={"q": "aabb.cc00.1122"}, headers=admin).json()
    assert por_mac["consulta"] == "AA:BB:CC:00:11:22"
    assert {(r["interfaz"], r["fuente"]) for r in por_mac["resultados"]} == {
        ("vlan100", "arp"),
        ("ether5", "bridge"),
    }
    por_ip = cliente.get(f"{API}/donde", params={"q": "10.9.0.5"}, headers=admin).json()
    assert [r["mac"] for r in por_ip["resultados"]] == ["AA:BB:CC:00:11:22"]
    malo = cliente.get(f"{API}/donde", params={"q": "no-es-nada"}, headers=admin)
    assert malo.status_code == 422


def test_explorador_snmp(cliente: TestClient, admin: dict[str, str]) -> None:
    agente = AgenteSNMPFalso()
    try:
        equipo = {
            "nombre": "R",
            "marca": "otra",
            "ip_gestion": "127.0.0.1",
            "snmp": _snmp_v3(agente.puerto),
        }
        equipo_id = cliente.post(f"{API}/equipos", json=equipo, headers=admin).json()["id"]
        filas = cliente.post(
            f"{API}/equipos/{equipo_id}/snmp/recorrer",
            json={"oid": "1.3.6.1.2.1.1"},
            headers=admin,
        ).json()
        assert any(f["oid"] == "1.3.6.1.2.1.1.1.0" and "PySNMP" in f["valor"] for f in filas)
        malo = cliente.post(
            f"{API}/equipos/{equipo_id}/snmp/recorrer", json={"oid": "1.3; rm"}, headers=admin
        )
        assert malo.status_code == 422
    finally:
        agente.cerrar()


# --- Caja de herramientas


@pytest.mark.parametrize("destino", ["-c 1 127.0.0.1", "127.0.0.1; ls", "a b", "$(id)", ""])
def test_destinos_que_no_se_aceptan(destino: str) -> None:
    with pytest.raises(herramientas.DestinoInvalido):
        herramientas.validar_destino(destino)


def test_puerto_abierto_y_cerrado(cliente: TestClient, admin: dict[str, str]) -> None:
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    puerto = servidor.getsockname()[1]
    try:
        abierto = cliente.post(
            f"{API}/herramientas/puerto",
            json={"destino": "127.0.0.1", "puerto": puerto},
            headers=admin,
        ).json()
        assert abierto["ok"] is True and "abierto" in abierto["texto"]
    finally:
        servidor.close()


def test_dns_de_localhost(cliente: TestClient, admin: dict[str, str]) -> None:
    salida = cliente.post(
        f"{API}/herramientas/dns", json={"destino": "localhost"}, headers=admin
    ).json()
    assert salida["ok"] is True and "localhost →" in salida["texto"]


def test_lector_no_usa_herramientas(cliente: TestClient, crear_usuario: object) -> None:
    from mufa.permisos import Rol

    lector = crear_usuario("lector1", Rol.LECTURA)  # type: ignore[operator]
    respuesta = cliente.post(
        f"{API}/herramientas/ping", json={"destino": "127.0.0.1"}, headers=lector
    )
    assert respuesta.status_code == 403


def test_ping_en_vivo_manda_la_salida_y_como_termino(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    respuesta = cliente.post(
        f"{API}/herramientas/ping/en-vivo",
        json={"destino": "127.0.0.1", "cantidad": 2},
        headers=admin,
    )
    assert respuesta.status_code == 200, respuesta.text
    texto, _, codigo = respuesta.text.rpartition("\x1e")
    assert "127.0.0.1" in texto
    assert codigo == "0"


def test_en_vivo_valida_el_destino(cliente: TestClient, admin: dict[str, str]) -> None:
    for destino in ("-t 8.8.8.8", "1.1.1.1; whoami", "$(id)"):
        respuesta = cliente.post(
            f"{API}/herramientas/ping/en-vivo", json={"destino": destino}, headers=admin
        )
        assert respuesta.status_code == 422, destino
    otra = cliente.post(
        f"{API}/herramientas/rm/en-vivo", json={"destino": "127.0.0.1"}, headers=admin
    )
    assert otra.status_code == 404


def test_agente_n1_diagnostica_pero_no_entra_a_los_equipos(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    agente = crear_usuario("mesa", Rol.AGENTE_N1)
    lectura = crear_usuario("gerencia", Rol.LECTURA)
    cuerpo = {"destino": "127.0.0.1"}
    assert cliente.post(f"{API}/herramientas/dns", json=cuerpo, headers=agente).status_code == 200
    assert cliente.post(f"{API}/herramientas/dns", json=cuerpo, headers=lectura).status_code == 403
    assert cliente.get(f"{API}/terminal/puertos-serie", headers=agente).status_code == 403
