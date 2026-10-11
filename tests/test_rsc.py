"""Pruebas del parser de exports .rsc."""

from __future__ import annotations

from mufa.rsc import parsear


def test_parsea_set_bajo_su_menu() -> None:
    texto = "/ip dns\nset allow-remote-requests=yes servers=8.8.8.8\n"
    comandos = parsear(texto)

    assert len(comandos) == 1
    assert comandos[0].menu == "/ip dns"
    assert comandos[0].verbo == "set"
    assert comandos[0].propiedades["allow-remote-requests"] == "yes"


def test_ignora_comentarios_y_lineas_vacias() -> None:
    texto = "# comentario\n/ip dns\n\nset allow-remote-requests=no\n"
    comandos = parsear(texto)

    assert len(comandos) == 1


def test_desenvuelve_continuaciones_con_backslash() -> None:
    texto = (
        "/ip firewall filter\n"
        "add action=drop chain=input \\\n"
        '    comment="MUFA-DNS-001" dst-port=53\n'
    )
    comandos = parsear(texto)

    assert len(comandos) == 1
    assert comandos[0].propiedades["comment"] == "MUFA-DNS-001"
    assert comandos[0].propiedades["dst-port"] == "53"
