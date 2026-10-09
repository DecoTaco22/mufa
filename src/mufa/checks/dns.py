"""MUFA-DNS-001: resolutor DNS abierto a internet."""

from __future__ import annotations

from mufa.engine import check
from mufa.models import Contexto, Hallazgo, PaqueteEntrante, Severidad


@check(
    id="MUFA-DNS-001",
    severidad=Severidad.CRITICO,
    titulo="Resolutor DNS abierto a internet",
    # La evidencia se apoya en la chain input de RouterOS.
    marcas=["mikrotik"],
)
def dns_abierto(ctx: Contexto) -> Hallazgo | None:
    if not ctx.dns.allow_remote_requests:
        return None
    if ctx.firewall.bloquea_entrada(PaqueteEntrante(protocolo="udp", puerto=53)):
        return None

    return Hallazgo(
        id="MUFA-DNS-001",
        severidad=Severidad.CRITICO,
        titulo="Resolutor DNS abierto a internet",
        evidencia=(
            "allow-remote-requests=yes y ninguna regla de la chain input descarta "
            "con certeza 53/udp entrante desde WAN"
        ),
        impacto=(
            "Cualquiera en internet puede usar tu router para amplificar ataques DDoS. "
            "El upstream puede cortarte el tránsito y tu rango de IPs puede terminar en "
            "listas negras."
        ),
        remediacion=[
            "/ip firewall filter add chain=input protocol=udp dst-port=53 \\",
            '    in-interface-list=WAN action=drop comment="MUFA-DNS-001"',
            "# Después moverla por encima de cualquier accept que deje pasar 53/udp:",
            "# add la pone al final y RouterOS aplica la primera regla que coincide.",
        ],
        referencia="https://mufa.dev/checks/MUFA-DNS-001",
    )
