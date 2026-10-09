"""Pruebas de la evaluación de la chain input (FirewallConfig.bloquea_entrada)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mufa.engine import evaluar
from mufa.marcas import contexto_desde_archivo
from mufa.marcas.mikrotik import contexto_desde_texto
from mufa.models import PaqueteEntrante

FIXTURES = Path(__file__).parent / "fixtures"
DNS = PaqueteEntrante(protocolo="udp", puerto=53)


def _bloquea(reglas: str) -> bool:
    ctx = contexto_desde_texto("/ip firewall filter\n" + reglas)
    return ctx.firewall.bloquea_entrada(DNS)


def test_firewall_por_defecto_de_routeros_bloquea_dns_desde_wan() -> None:
    ctx = contexto_desde_archivo(FIXTURES / "defconf.rsc")

    assert ctx.firewall.bloquea_entrada(DNS)
    assert "MUFA-DNS-001" not in [h.id for h in evaluar(ctx)]


@pytest.mark.parametrize(
    ("reglas", "esperado"),
    [
        pytest.param("", False, id="sin-reglas-la-politica-es-aceptar"),
        pytest.param(
            "add action=drop chain=input connection-state=invalid\n",
            False,
            id="drop-invalid-no-cubre-conexiones-nuevas",
        ),
        pytest.param(
            "add action=drop chain=input protocol=tcp dst-port=53 in-interface-list=WAN\n",
            False,
            id="drop-solo-tcp-no-cubre-udp",
        ),
        pytest.param(
            "add action=drop chain=input protocol=udp dst-port=53 in-interface-list=WAN"
            " disabled=yes\n",
            False,
            id="regla-deshabilitada-no-cuenta",
        ),
        pytest.param(
            "add action=accept chain=input protocol=udp dst-port=53\n"
            "add action=drop chain=input protocol=udp dst-port=53 in-interface-list=WAN\n",
            False,
            id="accept-anterior-gana",
        ),
        pytest.param(
            "add action=drop chain=input protocol=udp dst-port=1-1024 in-interface-list=WAN\n",
            True,
            id="rango-de-puertos",
        ),
        pytest.param(
            "add action=drop chain=input protocol=udp dst-port=!53 in-interface-list=WAN\n",
            False,
            id="puerto-negado",
        ),
        pytest.param(
            "add action=drop chain=input protocol=udp dst-port=53 in-interface-list=LAN\n",
            False,
            id="drop-solo-desde-lan",
        ),
        pytest.param(
            "add action=drop chain=input protocol=17 dst-port=53,123\n",
            True,
            id="protocolo-numerico-y-lista-de-puertos",
        ),
        pytest.param(
            "add action=accept chain=input src-address-list=confiables protocol=udp dst-port=53\n"
            "add action=drop chain=input in-interface-list=WAN\n",
            True,
            id="accept-limitado-por-origen-no-abre-a-internet",
        ),
        pytest.param(
            "add action=drop chain=input in-interface=ether1 protocol=udp dst-port=53\n",
            False,
            id="drop-con-criterio-desconocido-no-se-asume",
        ),
        pytest.param(
            "add action=jump chain=input jump-target=desde-wan in-interface-list=WAN\n"
            "add action=drop chain=desde-wan protocol=udp dst-port=53\n",
            True,
            id="sigue-jump-a-chain-propia",
        ),
        pytest.param(
            "add action=jump chain=input jump-target=desde-wan\n"
            "add action=return chain=desde-wan\n"
            "add action=drop chain=desde-wan protocol=udp dst-port=53\n",
            False,
            id="return-vuelve-a-la-chain-que-llamo",
        ),
        pytest.param(
            "add action=jump chain=input jump-target=bucle\n"
            "add action=jump chain=bucle jump-target=input\n",
            False,
            id="jump-circular-no-cuelga",
        ),
    ],
)
def test_bloquea_entrada(reglas: str, esperado: bool) -> None:
    assert _bloquea(reglas) is esperado
