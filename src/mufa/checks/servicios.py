"""Servicios de gestión expuestos a internet."""

from __future__ import annotations

from mufa.engine import check
from mufa.models import Contexto, Hallazgo, ServicioGestion, Severidad


def _lista(servicios: list[ServicioGestion]) -> str:
    return ", ".join(f"{s.nombre} ({s.protocolo}/{s.puerto})" for s in servicios)


def _motivo(ctx: Contexto) -> str:
    if ctx.firewall_conocido:
        return "sin restricción de origen y sin una regla que los descarte desde WAN"
    return "sin restricción de origen (mufa no puede evaluar todavía el filtrado de esta marca)"


@check(
    id="MUFA-SVC-001",
    severidad=Severidad.ALTO,
    titulo="Servicios en texto plano accesibles desde internet",
)
def servicios_en_texto_plano(ctx: Contexto) -> Hallazgo | None:
    expuestos = [s for s in ctx.servicios if s.texto_plano and ctx.expuesto_a_internet(s)]
    if not expuestos:
        return None
    nombres = {s.nombre for s in expuestos}
    remediacion = [f"/ip service disable {','.join(sorted(nombres))}"]
    if ctx.marca == "cisco":
        remediacion = [
            "line vty 0 15",
            " transport input ssh",
            "no ip http server",
        ]
    return Hallazgo(
        id="MUFA-SVC-001",
        severidad=Severidad.ALTO,
        titulo="Servicios en texto plano accesibles desde internet",
        evidencia=f"Habilitados {_motivo(ctx)}: {_lista(expuestos)}",
        impacto=(
            "Telnet, FTP, HTTP y la API sin TLS mandan usuario y contraseña sin cifrar: "
            "cualquiera en el camino los puede leer. Además reciben ataques de fuerza "
            "bruta automatizados las 24 horas."
        ),
        remediacion=remediacion,
        referencia="https://mufa.dev/checks/MUFA-SVC-001",
    )


_ADMINISTRACION = {"winbox", "ssh", "api-ssl", "www-ssl"}


@check(
    id="MUFA-SVC-002",
    severidad=Severidad.ALTO,
    titulo="Administración del equipo accesible desde internet",
    marcas=["mikrotik"],
)
def administracion_expuesta(ctx: Contexto) -> Hallazgo | None:
    expuestos = [
        s for s in ctx.servicios if s.nombre in _ADMINISTRACION and ctx.expuesto_a_internet(s)
    ]
    if not expuestos:
        return None
    return Hallazgo(
        id="MUFA-SVC-002",
        severidad=Severidad.ALTO,
        titulo="Administración del equipo accesible desde internet",
        evidencia=f"Habilitados {_motivo(ctx)}: {_lista(expuestos)}",
        impacto=(
            "Cualquiera en internet puede intentar entrar. Winbox tuvo vulnerabilidades "
            "graves (por ejemplo CVE-2018-14847, que permitía leer las contraseñas sin "
            "autenticarse) y los equipos expuestos son los primeros en caer."
        ),
        remediacion=[
            "# Limitar cada servicio a las redes de gestión:",
            "/ip service set winbox,ssh,api-ssl,www-ssl address=<red-de-gestion>",
            "# O descartar todo lo que entra por WAN salvo lo establecido:",
            "/ip firewall filter add chain=input in-interface-list=WAN \\",
            "    connection-state=new action=drop comment=MUFA-SVC-002",
        ],
        referencia="https://mufa.dev/checks/MUFA-SVC-002",
    )
