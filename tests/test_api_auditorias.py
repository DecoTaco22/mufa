"""Auditorías por archivo y por SSH (contra un servidor SSH falso en localhost)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mufa.permisos import Rol
from tests.conftest import CrearUsuario
from tests.ssh_falso import ServidorSSHFalso

API = "/api/v1"
FIXTURES = Path(__file__).parent / "fixtures"
EXPORT_ABIERTO = (FIXTURES / "dns_abierto.rsc").read_text(encoding="utf-8")


@pytest.fixture
def router_falso() -> Iterator[ServidorSSHFalso]:
    servidor = ServidorSSHFalso(
        lambda comando: EXPORT_ABIERTO if comando == "/ip dns export" else ""
    )
    yield servidor
    servidor.cerrar()


def _crear_equipo(cliente: TestClient, admin: dict[str, str], puerto: int, password: str) -> int:
    equipo = {
        "nombre": "Router de prueba",
        "marca": "mikrotik",
        "ip_gestion": "127.0.0.1",
        "puerto_ssh": puerto,
        "usuario_ssh": "mufa",
        "password_ssh": password,
    }
    respuesta = cliente.post(f"{API}/equipos", json=equipo, headers=admin)
    assert respuesta.status_code == 201, respuesta.text
    return int(respuesta.json()["id"])


def test_auditar_archivo_subido(cliente: TestClient, admin: dict[str, str]) -> None:
    respuesta = cliente.post(
        f"{API}/auditorias/archivo",
        files={"archivo": ("router.rsc", EXPORT_ABIERTO.encode("utf-8"))},
        data={"marca": "mikrotik"},
        headers=admin,
    )
    assert respuesta.status_code == 201, respuesta.text
    auditoria = respuesta.json()
    assert auditoria["estado"] == "ok"
    assert [h["check_id"] for h in auditoria["hallazgos"]] == ["MUFA-DNS-001"]


def test_lector_no_puede_auditar(cliente: TestClient, crear_usuario: CrearUsuario) -> None:
    lector = crear_usuario("lector", Rol.LECTURA)
    respuesta = cliente.post(
        f"{API}/auditorias/archivo",
        files={"archivo": ("router.rsc", b"/ip dns\nset allow-remote-requests=yes\n")},
        headers=lector,
    )
    assert respuesta.status_code == 403


def test_auditar_equipo_por_ssh_de_punta_a_punta(
    cliente: TestClient, admin: dict[str, str], router_falso: ServidorSSHFalso
) -> None:
    equipo_id = _crear_equipo(cliente, admin, router_falso.puerto, "clave-correcta")

    respuesta = cliente.post(f"{API}/equipos/{equipo_id}/auditar", headers=admin)
    assert respuesta.status_code == 200, respuesta.text
    auditoria = respuesta.json()
    assert auditoria["estado"] == "ok", auditoria["error"]
    assert [h["check_id"] for h in auditoria["hallazgos"]] == ["MUFA-DNS-001"]
    # Solo se corrieron comandos de la lista blanca de MikroTik.
    assert router_falso.comandos == [
        "/ip dns export",
        "/ip firewall filter export",
        "/ip service export verbose",
        "/snmp export verbose",
        "/system ntp client export verbose",
        "/system logging export verbose",
    ]

    abiertos = cliente.get(f"{API}/hallazgos", headers=admin).json()
    assert [(h["equipo"], h["hallazgo"]["check_id"]) for h in abiertos] == [
        ("Router de prueba", "MUFA-DNS-001")
    ]
    resumen = cliente.get(f"{API}/auditorias?equipo_id={equipo_id}", headers=admin).json()
    assert resumen[0]["cantidad_hallazgos"] == 1


def test_password_incorrecta_queda_como_error_registrado(
    cliente: TestClient, admin: dict[str, str], router_falso: ServidorSSHFalso
) -> None:
    equipo_id = _crear_equipo(cliente, admin, router_falso.puerto, "clave-equivocada")
    auditoria = cliente.post(f"{API}/equipos/{equipo_id}/auditar", headers=admin).json()
    assert auditoria["estado"] == "error"
    assert auditoria["error"]
    assert cliente.get(f"{API}/hallazgos", headers=admin).json() == []


def test_clave_de_host_cambiada_se_rechaza(
    cliente: TestClient, admin: dict[str, str], router_falso: ServidorSSHFalso
) -> None:
    equipo_id = _crear_equipo(cliente, admin, router_falso.puerto, "clave-correcta")
    primera = cliente.post(f"{API}/equipos/{equipo_id}/auditar", headers=admin).json()
    assert primera["estado"] == "ok"

    # Otro "router" en el mismo host:puerto con una clave distinta.
    router_falso.cerrar()
    impostor = ServidorSSHFalso(lambda _comando: "")
    cliente.patch(f"{API}/equipos/{equipo_id}", json={"puerto_ssh": impostor.puerto}, headers=admin)
    known_hosts = cliente.app.state.mufa.ajustes.known_hosts  # type: ignore[attr-defined]
    texto = known_hosts.read_text(encoding="utf-8")
    known_hosts.write_text(
        texto.replace(f"]:{router_falso.puerto} ", f"]:{impostor.puerto} "), encoding="utf-8"
    )
    try:
        segunda = cliente.post(f"{API}/equipos/{equipo_id}/auditar", headers=admin).json()
    finally:
        impostor.cerrar()
    assert segunda["estado"] == "error"
    assert "suplantación" in segunda["error"]
    assert impostor.comandos == []
