"""MUFA-SVC-001/002 y MUFA-SNMP-001 sobre exports de RouterOS."""

from __future__ import annotations

from pathlib import Path

from mufa.engine import evaluar
from mufa.marcas import contexto_desde_archivo
from mufa.marcas.mikrotik import contexto_desde_texto

FIXTURES = Path(__file__).parent / "fixtures"

SERVICIOS_VERBOSE = """/ip service
set telnet address="" disabled=no port=23 vrf=main
set ftp address="" disabled=yes port=21 vrf=main
set www address="" disabled=no port=80 vrf=main
set ssh address="" disabled=no port=22 vrf=main
set www-ssl address="" disabled=yes port=443 vrf=main
set api address="" disabled=yes port=8728 vrf=main
set winbox address=10.0.0.0/8 disabled=no port=8291 vrf=main
set api-ssl address="" disabled=yes port=8729 vrf=main
"""


def _ids(texto: str) -> set[str]:
    return {h.id for h in evaluar(contexto_desde_texto(texto))}


def test_telnet_y_www_sin_filtro_se_marcan() -> None:
    hallazgos = {h.id: h for h in evaluar(contexto_desde_texto(SERVICIOS_VERBOSE))}
    assert "MUFA-SVC-001" in hallazgos
    assert "telnet (tcp/23)" in hallazgos["MUFA-SVC-001"].evidencia
    assert "www (tcp/80)" in hallazgos["MUFA-SVC-001"].evidencia
    assert "ftp" not in hallazgos["MUFA-SVC-001"].evidencia  # deshabilitado
    # ssh expuesto, winbox no (restringido a 10.0.0.0/8).
    assert "ssh (tcp/22)" in hallazgos["MUFA-SVC-002"].evidencia
    assert "winbox" not in hallazgos["MUFA-SVC-002"].evidencia


def test_el_firewall_por_defecto_protege_los_servicios() -> None:
    defconf = (FIXTURES / "defconf.rsc").read_text(encoding="utf-8")
    assert _ids(defconf + SERVICIOS_VERBOSE) & {"MUFA-SVC-001", "MUFA-SVC-002"} == set()


def test_export_parcial_no_inventa_servicios() -> None:
    # Sin sección /ip service no se sabe nada de los servicios: no se asume nada.
    ctx = contexto_desde_archivo(FIXTURES / "dns_abierto.rsc")
    assert ctx.servicios == []
    assert {h.id for h in evaluar(ctx)} == {"MUFA-DNS-001"}


def test_export_normal_usa_los_valores_por_defecto() -> None:
    # En un export sin "verbose" solo aparece lo que cambió: telnet sigue habilitado.
    ids = _ids("/ip service\nset ftp disabled=yes\nset www disabled=yes\n")
    assert "MUFA-SVC-001" in ids


def test_snmp_con_public_habilitado() -> None:
    texto = (
        "/snmp community\n"
        "set [ find default=yes ] addresses=::/0 name=public security=none\n"
        "/snmp\n"
        "set enabled=yes\n"
    )
    hallazgos = {h.id: h for h in evaluar(contexto_desde_texto(texto))}
    assert hallazgos["MUFA-SNMP-001"].severidad.value == "crítico"  # sin filtro desde WAN


def test_snmp_deshabilitado_o_comunidad_renombrada_no_se_marca() -> None:
    assert "MUFA-SNMP-001" not in _ids("/snmp\nset enabled=no\n")
    renombrada = (
        "/snmp community\nset [ find default=yes ] name=Xk29-monitoreo\n/snmp\nset enabled=yes\n"
    )
    assert "MUFA-SNMP-001" not in _ids(renombrada)
    solo_v3 = "/snmp community\nset [ find default=yes ] security=private\n/snmp\nset enabled=yes\n"
    assert "MUFA-SNMP-001" not in _ids(solo_v3)


def test_snmp_habilitado_sin_nombrar_comunidad_usa_public() -> None:
    # Export normal: la comunidad por defecto "public" no aparece pero existe.
    assert "MUFA-SNMP-001" in _ids("/snmp\nset enabled=yes\n")
