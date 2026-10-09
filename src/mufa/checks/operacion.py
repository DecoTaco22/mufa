"""Buenas prácticas de operación: hora sincronizada y log fuera del equipo."""

from __future__ import annotations

from mufa.engine import check
from mufa.models import Contexto, Hallazgo, Severidad


@check(id="MUFA-NTP-001", severidad=Severidad.MEDIO, titulo="Sin sincronización de hora (NTP)")
def sin_ntp(ctx: Contexto) -> Hallazgo | None:
    if ctx.ntp_activo is not False:
        return None
    if ctx.marca == "cisco":
        remediacion = ["ntp server <ip-del-servidor-ntp>", "clock timezone CST -6 0"]
    else:
        remediacion = [
            "# RouterOS 7:",
            "/system ntp client set enabled=yes servers=<ip-del-servidor-ntp>",
            "# RouterOS 6:",
            "/system ntp client set enabled=yes primary-ntp=<ip-del-servidor-ntp>",
        ]
    return Hallazgo(
        id="MUFA-NTP-001",
        severidad=Severidad.MEDIO,
        titulo="Sin sincronización de hora (NTP)",
        evidencia="El cliente NTP está deshabilitado",
        impacto=(
            "Sin hora correcta, los logs de distintos equipos no se pueden comparar al "
            "investigar una falla o un ataque, y los certificados (API-SSL, HTTPS, VPN) "
            "pueden darse por vencidos o todavía no válidos."
        ),
        remediacion=remediacion,
        referencia="https://mufa.dev/checks/MUFA-NTP-001",
    )


@check(id="MUFA-LOG-001", severidad=Severidad.INFO, titulo="Los logs no salen del equipo")
def sin_log_remoto(ctx: Contexto) -> Hallazgo | None:
    if ctx.log_remoto is not False:
        return None
    if ctx.marca == "cisco":
        remediacion = ["logging host <ip-del-servidor-syslog>", "logging trap informational"]
    else:
        remediacion = [
            "/system logging action set [ find name=remote ] remote=<ip-del-servidor-syslog>",
            "/system logging add topics=info action=remote",
            "/system logging add topics=critical action=remote",
        ]
    return Hallazgo(
        id="MUFA-LOG-001",
        severidad=Severidad.INFO,
        titulo="Los logs no salen del equipo",
        evidencia="Ninguna regla de log manda a un servidor remoto (syslog)",
        impacto=(
            "Los logs quedan solo en la memoria del equipo: se pierden al reiniciar, y "
            "quien entre al equipo los puede borrar para no dejar rastro."
        ),
        remediacion=remediacion,
        referencia="https://mufa.dev/checks/MUFA-LOG-001",
    )
