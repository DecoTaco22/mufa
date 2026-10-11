"""SNMP con comunidades por defecto."""

from __future__ import annotations

from mufa.engine import check
from mufa.models import Contexto, Hallazgo, ServicioGestion, Severidad

_COMUNIDADES_DEBILES = {"public", "private"}


@check(
    id="MUFA-SNMP-001",
    severidad=Severidad.ALTO,
    titulo="SNMP con comunidad por defecto",
)
def comunidad_por_defecto(ctx: Contexto) -> Hallazgo | None:
    if not ctx.snmp.habilitado:
        return None
    debiles = sorted(
        c.nombre
        for c in ctx.snmp.comunidades
        if c.habilitada and not c.solo_v3 and c.nombre.lower() in _COMUNIDADES_DEBILES
    )
    if not debiles:
        return None

    agente = ServicioGestion(nombre="snmp", protocolo="udp", puerto=161, habilitado=True)
    desde_internet = ctx.expuesto_a_internet(agente)
    remediacion = [
        "# Usar SNMPv3 con autenticación y cifrado, y quitar la comunidad por defecto:",
        "/snmp community set [ find default=yes ] disabled=yes",
    ]
    if ctx.marca == "cisco":
        remediacion = [f"no snmp-server community {nombre}" for nombre in debiles]
    return Hallazgo(
        id="MUFA-SNMP-001",
        severidad=Severidad.CRITICO if desde_internet else Severidad.ALTO,
        titulo="SNMP con comunidad por defecto",
        evidencia=(
            f"SNMP habilitado con la comunidad {', '.join(debiles)}"
            + (", y el puerto 161/udp no está filtrado desde WAN" if desde_internet else "")
        ),
        impacto=(
            "La comunidad por defecto es lo primero que prueba cualquier escáner. Con ella "
            "se lee la configuración, las interfaces, las rutas y las tablas ARP del equipo; "
            "y SNMP v1/v2c viaja sin cifrar."
        ),
        remediacion=remediacion,
        referencia="https://mufa.dev/checks/MUFA-SNMP-001",
    )
