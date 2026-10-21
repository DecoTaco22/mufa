"""Mapa de topología: vecinos LLDP, CDP y MikroTik, y cómo se unen con los equipos."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mufa import snmp, topologia
from mufa.db import Equipo, EstadoEquipo

API = "/api/v1"


def _tablas_core() -> dict[str, dict[str, int | str]]:
    """Un Cisco con un vecino por LLDP y otro por CDP."""
    return {
        snmp.IF_NAME: {"1": "Gi0/1", "2": "Gi0/2"},
        topologia.LLDP_LOC_PUERTO_DESC: {"5": "GigabitEthernet0/1"},
        # tiempo.puerto local.índice
        topologia.LLDP_REM_NOMBRE: {"0.5.1": "borde.isp.local"},
        topologia.LLDP_REM_PUERTO_DESC: {"0.5.1": "sfp-sfpplus1"},
        topologia.LLDP_REM_DESCRIPCION: {"0.5.1": "MikroTik RouterOS 7.16\nCCR2004"},
        topologia.LLDP_REM_DIRECCION: {"0.5.1.1.4.10.0.0.2": 1},
        # ifIndex.índice
        topologia.CDP_NOMBRE: {"2.1": "SW-ACCESO-07"},
        topologia.CDP_PUERTO: {"2.1": "GigabitEthernet1/0/48"},
        topologia.CDP_DIRECCION: {"2.1": "0x0a000063"},  # 10.0.0.99
        topologia.CDP_PLATAFORMA: {"2.1": "cisco WS-C2960X"},
    }


def _tablas_borde() -> dict[str, dict[str, int | str]]:
    """Un MikroTik que ve al Cisco (por su tabla de vecinos y por LLDP: el mismo)."""
    return {
        snmp.IF_NAME: {"7": "sfp-sfpplus1"},
        topologia.MTXR_NOMBRE: {"3": "CORE"},
        topologia.MTXR_IP: {"3": "0x0a000001"},
        topologia.MTXR_INTERFAZ: {"3": 7},
        topologia.MTXR_PLATAFORMA: {"3": "Cisco"},
        topologia.LLDP_LOC_PUERTO_DESC: {"9": "sfp-sfpplus1"},
        topologia.LLDP_REM_NOMBRE: {"0.9.1": "CORE"},
    }


def test_lee_vecinos_de_las_tres_tablas() -> None:
    vecinos = {v.nombre: v for v in topologia.vecinos_de(_tablas_core())}
    borde = vecinos["borde.isp.local"]
    assert (borde.interfaz, borde.puerto, borde.ip, borde.fuente) == (
        "GigabitEthernet0/1",
        "sfp-sfpplus1",
        "10.0.0.2",
        "lldp",
    )
    assert borde.plataforma == "MikroTik RouterOS 7.16"
    acceso = vecinos["SW-ACCESO-07"]
    assert (acceso.interfaz, acceso.ip, acceso.fuente) == ("Gi0/2", "10.0.0.99", "cdp")
    # El MikroTik ve al Cisco por dos tablas: queda uno solo, con los datos de ambas.
    unico = topologia.vecinos_de(_tablas_borde())
    assert [(v.nombre, v.ip, v.interfaz, v.plataforma) for v in unico] == [
        ("CORE", "10.0.0.1", "sfp-sfpplus1", "Cisco")
    ]


def test_el_mapa_une_por_ip_o_nombre_y_muestra_lo_que_falta(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    estado = cliente.app.state.mufa  # type: ignore[attr-defined]
    with estado.sesiones() as db:
        core = Equipo(
            nombre="CORE",
            marca="cisco",
            ip_gestion="10.0.0.1",
            snmp_version="2c",
            snmp_comunidad_cifrada=estado.cifrador.cifrar("c"),
        )
        borde = Equipo(
            nombre="BORDE",
            marca="mikrotik",
            ip_gestion="10.0.0.2",
            snmp_version="2c",
            snmp_comunidad_cifrada=estado.cifrador.cifrar("c"),
        )
        db.add_all([core, borde])
        db.flush()
        db.add(EstadoEquipo(equipo_id=core.id, en_linea=True))
        db.add(EstadoEquipo(equipo_id=borde.id, en_linea=False, alcanzable=False))
        db.commit()
        ids = {"10.0.0.1": core.id, "10.0.0.2": borde.id}

    respuestas = {"10.0.0.1": _tablas_core(), "10.0.0.2": _tablas_borde()}
    with estado.sesiones() as db:
        resultado = topologia.descubrir(
            db, estado.cifrador, lambda host, cred, columnas: respuestas[host]
        )
        db.commit()
    assert (resultado.equipos, resultado.errores) == (2, {})

    datos = cliente.get(f"{API}/mapa", headers=admin).json()
    nodos = {n["nombre"]: n for n in datos["nodos"]}
    assert nodos["CORE"]["estado"] == "en_linea"
    assert nodos["BORDE"]["estado"] == "caido"
    assert nodos["SW-ACCESO-07"]["estado"] == "fuera"  # no está en mufa
    pares = {tuple(sorted((e["desde"], e["hasta"]))) for e in datos["enlaces"]}
    # CORE-BORDE se ve desde los dos lados (por IP y por nombre): un solo enlace.
    assert tuple(sorted((f"e{ids['10.0.0.1']}", f"e{ids['10.0.0.2']}"))) in pares
    assert len(datos["enlaces"]) == 2
    assert datos["actualizado"] is not None


def test_un_equipo_que_no_responde_conserva_sus_vecinos(cliente: TestClient) -> None:
    estado = cliente.app.state.mufa  # type: ignore[attr-defined]
    with estado.sesiones() as db:
        db.add(
            Equipo(
                nombre="CORE",
                marca="cisco",
                ip_gestion="10.0.0.1",
                snmp_version="2c",
                snmp_comunidad_cifrada=estado.cifrador.cifrar("c"),
            )
        )
        db.commit()
        topologia.descubrir(db, estado.cifrador, lambda h, c, col: _tablas_core())

        def caido(
            host: str, cred: snmp.CredencialesSNMP, columnas: list[str]
        ) -> dict[str, dict[str, int | str]]:
            raise snmp.ErrorSNMP("sin respuesta")

        resultado = topologia.descubrir(db, estado.cifrador, caido)
        db.commit()
        assert resultado.errores == {"CORE": "sin respuesta"}
        _nodos, enlaces = topologia.mapa(db)
    assert len(enlaces) == 2


def test_descubrir_por_la_api_pide_permiso_de_diagnostico(
    cliente: TestClient, crear_usuario
) -> None:  # type: ignore[no-untyped-def]
    from mufa.permisos import Rol

    lectura = crear_usuario("lector", Rol.LECTURA)
    assert cliente.get(f"{API}/mapa", headers=lectura).status_code == 200
    assert cliente.post(f"{API}/mapa/descubrir", headers=lectura).status_code == 403
