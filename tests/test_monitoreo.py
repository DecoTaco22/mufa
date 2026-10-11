"""Monitoreo SNMP: configuración, sondeo real contra un agente SNMPv3, caídas y tráfico."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from mufa import monitoreo, snmp
from mufa.db import Equipo
from tests.snmp_falso import CLAVE_AUTH, CLAVE_PRIV, COMUNIDAD, USUARIO, AgenteSNMPFalso

API = "/api/v1"


@pytest.fixture(scope="module")
def agente() -> Iterator[AgenteSNMPFalso]:
    falso = AgenteSNMPFalso()
    yield falso
    falso.cerrar()


def _snmp_v3(puerto: int, priv: str = CLAVE_PRIV) -> dict[str, object]:
    return {
        "version": "3",
        "puerto": puerto,
        "usuario": USUARIO,
        "clave_auth": CLAVE_AUTH,
        "clave_priv": priv,
        "protocolo_auth": "sha",
        "protocolo_priv": "aes",
    }


def _crear(cliente: TestClient, admin: dict[str, str], snmp_config: dict[str, object]) -> int:
    equipo = {"nombre": "OLT", "marca": "huawei", "ip_gestion": "127.0.0.1", "snmp": snmp_config}
    respuesta = cliente.post(f"{API}/equipos", json=equipo, headers=admin)
    assert respuesta.status_code == 201, respuesta.text
    return int(respuesta.json()["id"])


def test_snmp_v3_incompleto_se_rechaza(cliente: TestClient, admin: dict[str, str]) -> None:
    sin_priv = {"version": "3", "usuario": "mufa", "clave_auth": "12345678"}
    equipo = {"nombre": "R", "marca": "cisco", "ip_gestion": "10.0.0.1", "snmp": sin_priv}
    assert cliente.post(f"{API}/equipos", json=equipo, headers=admin).status_code == 422
    corta = {**sin_priv, "clave_priv": "corta"}
    assert (
        cliente.post(f"{API}/equipos", json={**equipo, "snmp": corta}, headers=admin).status_code
        == 422
    )
    v2c_sin_comunidad = {"version": "2c"}
    assert (
        cliente.post(
            f"{API}/equipos", json={**equipo, "snmp": v2c_sin_comunidad}, headers=admin
        ).status_code
        == 422
    )


def test_las_claves_snmp_no_se_devuelven(cliente: TestClient, admin: dict[str, str]) -> None:
    respuesta = cliente.post(
        f"{API}/equipos",
        json={"nombre": "R", "marca": "cisco", "ip_gestion": "10.0.0.1", "snmp": _snmp_v3(161)},
        headers=admin,
    )
    assert CLAVE_AUTH not in respuesta.text and CLAVE_PRIV not in respuesta.text
    assert respuesta.json()["snmp"] == {
        "version": "3",
        "puerto": 161,
        "usuario": USUARIO,
        "protocolo_auth": "sha",
        "protocolo_priv": "aes",
    }


def test_sondeo_snmpv3_real(
    cliente: TestClient, admin: dict[str, str], agente: AgenteSNMPFalso
) -> None:
    equipo_id = _crear(cliente, admin, _snmp_v3(agente.puerto))
    estado = cliente.post(f"{API}/equipos/{equipo_id}/sondear", headers=admin).json()
    assert estado["en_linea"] is True, estado["error"]
    assert "PySNMP" in estado["sys_descripcion"]
    assert estado["sys_object_id"].startswith("1.3.6.1.4.1.")

    assert cliente.get(f"{API}/equipos/{equipo_id}/estado", headers=admin).json()["en_linea"]
    resumen = cliente.get(f"{API}/monitoreo/resumen", headers=admin).json()
    assert (resumen["monitoreados"], resumen["en_linea"], resumen["caidos"]) == (1, 1, [])


def test_sondeo_snmp_v2c(
    cliente: TestClient, admin: dict[str, str], agente: AgenteSNMPFalso
) -> None:
    v2c = {"version": "2c", "puerto": agente.puerto, "comunidad": COMUNIDAD}
    equipo_id = _crear(cliente, admin, v2c)
    assert cliente.post(f"{API}/equipos/{equipo_id}/sondear", headers=admin).json()["en_linea"]


def test_equipo_que_deja_de_responder_aparece_caido(
    cliente: TestClient, admin: dict[str, str], agente: AgenteSNMPFalso
) -> None:
    equipo_id = _crear(cliente, admin, _snmp_v3(agente.puerto))
    assert cliente.post(f"{API}/equipos/{equipo_id}/sondear", headers=admin).json()["en_linea"]

    # Clave de privacidad equivocada: el agente no responde nada descifrable.
    cliente.patch(
        f"{API}/equipos/{equipo_id}",
        json={"snmp": _snmp_v3(agente.puerto, priv="otra-clave-de-priv")},
        headers=admin,
    )
    estado = cliente.post(f"{API}/equipos/{equipo_id}/sondear", headers=admin).json()
    assert estado["en_linea"] is False
    assert estado["error"]
    resumen = cliente.get(f"{API}/monitoreo/resumen", headers=admin).json()
    assert [c["nombre"] for c in resumen["caidos"]] == ["OLT"]
    eventos = cliente.get(f"{API}/eventos", headers=admin).json()
    assert any(e["accion"] == "equipo.caido" for e in eventos)


def test_trafico_entre_dos_muestras(
    cliente: TestClient, admin: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    equipo_id = _crear(cliente, admin, _snmp_v3(161))
    inicio = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    # Dos sondeos separados 10 s, con el reloj de mufa fijo en cada uno.
    momentos = iter([inicio, inicio + timedelta(seconds=10)])
    monkeypatch.setattr(monitoreo, "ahora", lambda: next(momentos))
    contadores = iter([(1_000, 5_000), (126_000, 30_005_000)])

    def sondeo_falso(
        _host: str, _cred: snmp.CredencialesSNMP, _timeout: float
    ) -> snmp.ResultadoSondeo:
        entrada, salida = next(contadores)
        return snmp.ResultadoSondeo(
            nombre="olt",
            descripcion="",
            object_id="1.3.6.1.4.1.2011.2.1",
            uptime_segundos=100,
            marca_detectada="huawei",
            interfaces=[snmp.Interfaz(1, "uplink", True, 10_000, entrada, salida)],
        )

    with cliente.app.state.mufa.sesiones() as db:  # type: ignore[attr-defined]
        equipo = db.get(Equipo, equipo_id)
        assert equipo is not None
        cifrador = cliente.app.state.mufa.cifrador  # type: ignore[attr-defined]
        for _ in range(2):
            estado = monitoreo.sondear_equipo(db, equipo, cifrador, sondeo=sondeo_falso)
        db.commit()
        assert estado.marca_detectada == "huawei"

    interfaces = cliente.get(f"{API}/equipos/{equipo_id}/interfaces", headers=admin).json()
    assert interfaces == [
        {
            "if_index": 1,
            "nombre": "uplink",
            "operativa": True,
            "velocidad_mbps": 10_000,
            "bps_entrada": 100_000.0,  # 125.000 bytes en 10 s
            "bps_salida": 24_000_000.0,  # 30.000.000 bytes en 10 s
            "vigilada_id": None,
            "umbral_saturacion": None,
        }
    ]


def test_marca_por_object_id() -> None:
    assert snmp.marca_por_object_id("1.3.6.1.4.1.14988.1") == "mikrotik"
    assert snmp.marca_por_object_id("1.3.6.1.4.1.9.1.2066") == "cisco"
    assert snmp.marca_por_object_id("1.3.6.1.4.1.99999.1") == ""
    assert snmp.marca_por_object_id("") == ""


def test_probar_snmp_antes_de_guardar(
    cliente: TestClient, admin: dict[str, str], agente: AgenteSNMPFalso
) -> None:
    prueba = {"ip_gestion": "127.0.0.1", "snmp": _snmp_v3(agente.puerto)}
    resultado = cliente.post(f"{API}/snmp/probar", json=prueba, headers=admin).json()
    assert resultado["ok"] is True, resultado["mensaje"]
    assert "PySNMP" in resultado["sys_descripcion"]
    assert resultado["ip_origen"] == "127.0.0.1"

    otro_usuario = {**_snmp_v3(agente.puerto), "usuario": "no-existe"}
    resultado = cliente.post(
        f"{API}/snmp/probar", json={**prueba, "snmp": otro_usuario}, headers=admin
    ).json()
    assert resultado["ok"] is False
    assert "nombre (Name) de la comunidad" in resultado["mensaje"]


def test_probar_snmp_devuelve_la_identidad_del_equipo(
    cliente: TestClient, admin: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con lo que responde el equipo, el formulario se completa solo."""

    def mikrotik(host: str, cred: snmp.CredencialesSNMP) -> snmp.ResultadoSondeo:
        return snmp.ResultadoSondeo(
            nombre="SN-SEM-RT",
            descripcion="RouterOS CCR2004-1G-12S+2XS",
            object_id="1.3.6.1.4.1.14988.1",
            uptime_segundos=10,
            marca_detectada="mikrotik",
            ubicacion="Torre Norte",
            serie="HD3089ABC12",
            modelo="CCR2004-1G-12S+2XS",
            version="7.16.1",
        )

    monkeypatch.setattr(snmp, "probar", mikrotik)
    prueba = {"ip_gestion": "10.0.0.1", "snmp": _snmp_v3(161)}
    resultado = cliente.post(f"{API}/snmp/probar", json=prueba, headers=admin).json()
    assert resultado["ok"] is True
    assert resultado["sys_nombre"] == "SN-SEM-RT"
    assert resultado["marca_detectada"] == "mikrotik"
    assert (resultado["modelo"], resultado["serie"]) == ("CCR2004-1G-12S+2XS", "HD3089ABC12")
    assert (resultado["version"], resultado["ubicacion"]) == ("7.16.1", "Torre Norte")


def test_editar_sin_reescribir_las_claves_snmp(
    cliente: TestClient, admin: dict[str, str], agente: AgenteSNMPFalso
) -> None:
    equipo_id = _crear(cliente, admin, _snmp_v3(agente.puerto))
    sin_claves = {**_snmp_v3(agente.puerto), "clave_auth": None, "clave_priv": None}
    respuesta = cliente.patch(
        f"{API}/equipos/{equipo_id}", json={"snmp": sin_claves}, headers=admin
    )
    assert respuesta.status_code == 200, respuesta.text
    assert cliente.post(f"{API}/equipos/{equipo_id}/sondear", headers=admin).json()["en_linea"]

    # La prueba también usa las claves guardadas del equipo.
    prueba = {"ip_gestion": "127.0.0.1", "snmp": sin_claves, "equipo_id": equipo_id}
    assert cliente.post(f"{API}/snmp/probar", json=prueba, headers=admin).json()["ok"]


def test_encendido_pero_sin_snmp(cliente: TestClient, admin: dict[str, str]) -> None:
    equipo_id = _crear(cliente, admin, _snmp_v3(161))
    sesiones = cliente.app.state.mufa.sesiones  # type: ignore[attr-defined]
    cifrador = cliente.app.state.mufa.cifrador  # type: ignore[attr-defined]

    def sin_respuesta(
        host: str, cred: snmp.CredencialesSNMP, timeout: float
    ) -> snmp.ResultadoSondeo:
        raise snmp.ErrorSNMP("No SNMP response received before timeout")

    with sesiones() as db:
        equipo = db.get(Equipo, equipo_id)
        assert equipo is not None
        estado = monitoreo.sondear_equipo(
            db, equipo, cifrador, sondeo=sin_respuesta, verificar_alcance=lambda h, p: "ping"
        )
        assert (estado.en_linea, estado.alcanzable) == (False, True)
        assert estado.error.startswith("El equipo está encendido (responde a ping)")
        estado = monitoreo.sondear_equipo(
            db, equipo, cifrador, sondeo=sin_respuesta, verificar_alcance=lambda h, p: ""
        )
        assert (estado.en_linea, estado.alcanzable) == (False, False)


def test_explicar_errores_snmp() -> None:
    cred = snmp.CredencialesSNMP(version="3", usuario="monitoreo")
    timeout = snmp.explicar("No SNMP response received before timeout", "127.0.0.1", cred)
    assert "127.0.0.1" in timeout and "Addresses" in timeout
    assert "monitoreo" in snmp.explicar("Unknown USM user", "127.0.0.1", cred)
    assert "autenticación" in snmp.explicar("Wrong SNMP PDU digest", "127.0.0.1", cred)
