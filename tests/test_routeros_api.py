"""Lectura de MikroTik por la API de RouterOS: auditoría y respaldo sin SSH."""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mufa.routeros_api import ErrorApiRouterOS, SesionApiRouterOS, codificar_oracion
from tests.api_routeros_falsa import PASSWORD, ApiRouterOSFalsa

API = "/api/v1"


@pytest.fixture
def router() -> Iterator[ApiRouterOSFalsa]:
    falso = ApiRouterOSFalsa()
    yield falso
    falso.cerrar()


def _crear(
    cliente: TestClient, admin: dict[str, str], puerto: int, password: str = PASSWORD
) -> int:
    equipo = {
        "nombre": "CCR por API",
        "marca": "mikrotik",
        "ip_gestion": "127.0.0.1",
        "acceso": "api",
        "puerto_ssh": puerto,
        "usuario_ssh": "mufa",
        "password_ssh": password,
    }
    respuesta = cliente.post(f"{API}/equipos", json=equipo, headers=admin)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["acceso"] == "api"
    return int(respuesta.json()["id"])


def test_largos_del_protocolo() -> None:
    # Palabras de 1, 2 y 3 bytes de largo (127, 128 y 16384 bytes).
    for largo, prefijo in ((127, b"\x7f"), (128, b"\x80\x80"), (0x4000, b"\xc0\x40\x00")):
        assert codificar_oracion(["x" * largo]).startswith(prefijo)


def test_auditoria_por_api(
    cliente: TestClient, admin: dict[str, str], router: ApiRouterOSFalsa
) -> None:
    equipo_id = _crear(cliente, admin, router.puerto)
    auditoria = cliente.post(f"{API}/equipos/{equipo_id}/auditar", headers=admin).json()
    assert auditoria["estado"] == "ok", auditoria["error"]
    hallazgos = {h["check_id"] for h in auditoria["hallazgos"]}
    assert {"MUFA-DNS-001", "MUFA-SVC-001", "MUFA-SNMP-001"} <= hallazgos


def test_por_la_api_solo_se_consulta(
    cliente: TestClient, admin: dict[str, str], router: ApiRouterOSFalsa
) -> None:
    equipo_id = _crear(cliente, admin, router.puerto)
    cliente.post(f"{API}/equipos/{equipo_id}/auditar", headers=admin)
    cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin)
    assert router.comandos
    assert all(c == "/login" or c.endswith("/print") for c in router.comandos), router.comandos


def test_la_sesion_rechaza_comandos_que_no_son_print(router: ApiRouterOSFalsa) -> None:
    with SesionApiRouterOS("127.0.0.1", "mufa", PASSWORD, port=router.puerto) as sesion:
        with pytest.raises(ValueError):
            sesion._enviar_comando("/system/reboot")
        with pytest.raises(ValueError):
            sesion.run_readonly("/system reboot")
    assert "/system/reboot" not in router.comandos


def test_respaldo_por_api_sin_secretos_ni_contadores(
    cliente: TestClient, admin: dict[str, str], router: ApiRouterOSFalsa
) -> None:
    equipo_id = _crear(cliente, admin, router.puerto)
    sin_secretos = {"activo": True, "hora": "12:00", "secretos": False}
    assert (
        cliente.put(f"{API}/respaldos/programa", json=sin_secretos, headers=admin).status_code
        == 200
    )
    primero = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).json()
    texto = cliente.get(f"{API}/respaldos/{primero['respaldo']['id']}", headers=admin).json()[
        "contenido"
    ]
    assert "Generado por mufa con la API" in texto
    assert "set name=router-de-prueba" in texto
    assert "no-debe-aparecer" not in texto
    assert "bytes=" not in texto and "packets=" not in texto and ".id" not in texto
    # Las entradas dinámicas no son configuración.
    assert "fasttrack-connection" not in texto
    # Los contadores no cuentan como cambio.
    router.menus["/ip/firewall/filter/print"][0]["bytes"] = "999999"
    segundo = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).json()
    assert segundo["cambio"] is False

    # Con la opción de secretos (la de fábrica) sí van, para poder restaurar.
    con_secretos = {**sin_secretos, "secretos": True}
    cliente.put(f"{API}/respaldos/programa", json=con_secretos, headers=admin)
    tercero = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).json()
    texto = cliente.get(f"{API}/respaldos/{tercero['respaldo']['id']}", headers=admin).json()[
        "contenido"
    ]
    assert "no-debe-aparecer" in texto
    assert "habilita SSH" in texto


def test_contraseña_incorrecta(
    cliente: TestClient, admin: dict[str, str], router: ApiRouterOSFalsa
) -> None:
    equipo_id = _crear(cliente, admin, router.puerto, password="otra-cosa")
    auditoria = cliente.post(f"{API}/equipos/{equipo_id}/auditar", headers=admin).json()
    assert auditoria["estado"] == "error"
    assert "usuario o la contraseña" in auditoria["error"]


def test_puerto_cerrado() -> None:
    # Un puerto libre en el que nunca escuchó nadie.
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]
    with (
        pytest.raises(ErrorApiRouterOS, match=r"el puerto \d+ (rechazó la conexión|no responde)"),
        SesionApiRouterOS("127.0.0.1", "mufa", PASSWORD, port=puerto, timeout=2),
    ):
        pass


def test_api_solo_para_mikrotik(cliente: TestClient, admin: dict[str, str]) -> None:
    equipo = {"nombre": "R", "marca": "cisco", "ip_gestion": "10.0.0.1", "acceso": "api"}
    assert cliente.post(f"{API}/equipos", json=equipo, headers=admin).status_code == 422
