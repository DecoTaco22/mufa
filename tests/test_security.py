"""Pruebas del módulo de seguridad."""

from __future__ import annotations

import pytest

from mufa.security import assert_allowed, is_write_command
from mufa.ssh import SesionSoloLectura


def test_is_write_command_detecta_verbos_de_escritura() -> None:
    assert is_write_command("/ip firewall filter add chain=input")
    assert is_write_command("/ip service set winbox disabled=yes")
    assert not is_write_command("/ip dns export")


def test_assert_allowed_rechaza_comando_fuera_de_la_lista() -> None:
    with pytest.raises(ValueError):
        assert_allowed("/ip firewall filter print", "mikrotik")


def test_assert_allowed_acepta_comando_de_la_lista_blanca() -> None:
    assert_allowed("/ip dns export", "mikrotik")


def test_la_sesion_ssh_rechaza_comandos_fuera_de_la_lista_antes_de_ejecutar() -> None:
    # Sin conectar: si assert_allowed no corriera primero, esto fallaría al
    # intentar ejecutar sobre un cliente SSH sin conexión, no con ValueError.
    sesion = SesionSoloLectura("10.0.0.1", "readonly", "mikrotik")
    with pytest.raises(ValueError, match="lista blanca"):
        sesion.run_readonly("/ip firewall filter remove 0")


def test_assert_allowed_rechaza_comando_de_otra_marca() -> None:
    with pytest.raises(ValueError):
        assert_allowed("/ip dns export", "cisco")


def test_verbos_de_escritura_de_otras_marcas() -> None:
    assert is_write_command("configure terminal")
    assert is_write_command("system-view")
    assert is_write_command("undo snmp-agent")
    assert not is_write_command("show running-config")
    assert not is_write_command("display current-configuration")
