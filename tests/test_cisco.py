"""Adaptador de Cisco IOS: verificaciones, respaldo y lectura por SSH."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mufa.engine import evaluar
from mufa.marcas.cisco import CiscoIOS, contexto_desde_texto
from tests.ssh_falso import ServidorSSHFalso

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = (FIXTURES / "cisco_ios.txt").read_text(encoding="utf-8")


def test_hallazgos_de_un_running_config() -> None:
    hallazgos = {h.id: h for h in evaluar(contexto_desde_texto(CONFIG))}
    # Telnet en vty 0 4 sin access-class, y HTTP sin cifrar.
    assert "telnet (tcp/23)" in hallazgos["MUFA-SVC-001"].evidencia
    assert "http (tcp/80)" in hallazgos["MUFA-SVC-001"].evidencia
    assert "line vty 0 15" in hallazgos["MUFA-SVC-001"].remediacion
    # Comunidad public: sin ACL de interfaces conocidas no se puede dar por filtrada.
    assert "public" in hallazgos["MUFA-SNMP-001"].evidencia
    assert "Xk29" not in hallazgos["MUFA-SNMP-001"].evidencia
    assert hallazgos["MUFA-SNMP-001"].remediacion == ["no snmp-server community public"]
    # MUFA-DNS-001 se apoya en la chain input de RouterOS: no aplica a Cisco.
    assert "MUFA-DNS-001" not in hallazgos
    # SVC-002 es de MikroTik.
    assert "MUFA-SVC-002" not in hallazgos


def test_vty_con_access_class_no_se_marca() -> None:
    seguro = (
        "line vty 0 15\n access-class GESTION in\n transport input telnet ssh\n"
        "ntp server 10.0.0.1\nlogging host 10.0.0.2\n"
    )
    assert evaluar(contexto_desde_texto(seguro)) == []


def test_la_fecha_del_ultimo_cambio_no_cuenta_como_diferencia() -> None:
    otra = CONFIG.replace("10:20:31 UTC Mon Oct 5 2026", "08:00:00 UTC Tue Oct 6 2026").replace(
        "2114 bytes", "2120 bytes"
    )
    adaptador = CiscoIOS()
    assert adaptador.normalizar_respaldo(CONFIG) == adaptador.normalizar_respaldo(otra)


def test_auditar_y_respaldar_un_cisco_por_ssh(cliente: TestClient, admin: dict[str, str]) -> None:
    router = ServidorSSHFalso(lambda c: CONFIG if c == "show running-config" else "")
    try:
        equipo = {
            "nombre": "R Sucursal 2",
            "marca": "cisco",
            "ip_gestion": "127.0.0.1",
            "puerto_ssh": router.puerto,
            "usuario_ssh": "mufa",
            "password_ssh": "clave-correcta",
        }
        equipo_id = cliente.post("/api/v1/equipos", json=equipo, headers=admin).json()["id"]
        auditoria = cliente.post(f"/api/v1/equipos/{equipo_id}/auditar", headers=admin).json()
        assert auditoria["estado"] == "ok", auditoria["error"]
        assert {h["check_id"] for h in auditoria["hallazgos"]} == {
            "MUFA-SVC-001",
            "MUFA-SNMP-001",
            "MUFA-NTP-001",
            "MUFA-LOG-001",
        }
        respaldo = cliente.post(f"/api/v1/equipos/{equipo_id}/respaldar", headers=admin).json()
        assert respaldo["cambio"] is True
        assert router.comandos == ["show running-config", "show running-config"]
    finally:
        router.cerrar()
