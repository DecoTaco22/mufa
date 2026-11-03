"""Auditoría de Huawei VRP: de `display current-configuration` al Contexto y los hallazgos."""

from __future__ import annotations

from pathlib import Path

from mufa import marcas
from mufa.engine import evaluar
from mufa.marcas import huawei
from mufa.security import ALLOWED_COMMANDS, is_write_command

EJEMPLO = (Path(__file__).parent / "fixtures" / "huawei_vrp.txt").read_text(encoding="utf-8")


def test_lee_la_configuracion() -> None:
    ctx = huawei.contexto_desde_texto(EJEMPLO)
    assert ctx.marca == "huawei"
    assert ctx.version == "V200R019C10SPC500"
    assert ctx.ntp_activo is False
    assert ctx.log_remoto is True
    assert not ctx.firewall_conocido
    servicios = {s.nombre: s for s in ctx.servicios}
    assert set(servicios) == {"telnet", "ssh", "http", "https"}
    # Telnet solo por la vty 0 4, que no tiene ACL.
    assert servicios["telnet"].texto_plano and not servicios["telnet"].restringido
    # SSH por las dos, y una sin ACL: no está restringido.
    assert not servicios["ssh"].restringido
    assert ctx.snmp.habilitado
    assert [c.nombre for c in ctx.snmp.comunidades] == ["public", "(cifrada)"]


def test_hallazgos_con_arreglo_para_huawei() -> None:
    hallazgos = {h.id: h for h in evaluar(huawei.contexto_desde_texto(EJEMPLO))}
    assert "MUFA-SVC-001" in hallazgos
    assert "undo telnet server enable" in hallazgos["MUFA-SVC-001"].remediacion
    assert "undo snmp-agent community public" in hallazgos["MUFA-SNMP-001"].remediacion
    assert hallazgos["MUFA-NTP-001"].remediacion[1].startswith("ntp-service unicast-server")
    assert "MUFA-LOG-001" not in hallazgos


def test_una_configuracion_cuidada_no_da_hallazgos_de_servicios() -> None:
    cuidada = """#
undo telnet server enable
undo http server enable
stelnet server enable
 ntp-service unicast-server 192.0.2.1
 info-center loghost 192.0.2.50
snmp-agent
snmp-agent sys-info version v3
user-interface vty 0 4
 authentication-mode aaa
 protocol inbound ssh
 acl 2000 inbound
#
return
"""
    ctx = huawei.contexto_desde_texto(cuidada)
    assert [s.nombre for s in ctx.servicios] == ["ssh"]
    assert ctx.servicios[0].restringido
    ids = {h.id for h in evaluar(ctx)}
    assert not ids & {"MUFA-SVC-001", "MUFA-SNMP-001", "MUFA-NTP-001", "MUFA-LOG-001"}


def test_sin_telnet_server_enable_no_hay_telnet() -> None:
    # VRP nuevo: telnet viene apagado; una vty sin «protocol inbound» no lo prende.
    ctx = huawei.contexto_desde_texto("#\nuser-interface vty 0 4\n authentication-mode aaa\n#\n")
    assert all(s.nombre != "telnet" for s in ctx.servicios)


def test_huawei_se_audita_y_se_respalda_con_su_lista_blanca() -> None:
    adaptador = marcas.obtener("huawei")
    assert marcas.respaldador("huawei") is adaptador
    assert huawei.COMANDO in ALLOWED_COMMANDS["huawei"]
    assert not is_write_command(huawei.COMANDO)
    normal = adaptador.normalizar_respaldo(EJEMPLO)
    assert "Last configuration was updated" not in normal
    assert "sysname AR-EJEMPLO" in normal
