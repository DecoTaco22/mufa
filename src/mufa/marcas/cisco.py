"""Adaptador de Cisco IOS / IOS XE.

Lee `show running-config`. Por ahora traduce al Contexto los servicios de
gestión (vty, HTTP), el servidor DNS y las comunidades SNMP. Las ACL de
las interfaces todavía no se evalúan: por eso el Contexto declara
firewall_conocido=False y las verificaciones no dan nada por filtrado.
"""

from __future__ import annotations

import re

from mufa.marcas.base import Adaptador
from mufa.models import AgenteSNMP, ComunidadSNMP, Contexto, DnsConfig, ServicioGestion
from mufa.ssh import SesionDeLectura

# Líneas que cambian solas entre dos lecturas de la misma configuración.
_VOLATILES = re.compile(
    r"^(Building configuration\.\.\.|Current configuration : \d+ bytes"
    r"|! Last configuration change at |! NVRAM config last updated at "
    r"|! No configuration change since last restart|ntp clock-period )"
)
_VERSION = re.compile(r"^version (\S+)", re.MULTILINE)
_NTP = re.compile(r"^ntp server ", re.MULTILINE)
_LOG_REMOTO = re.compile(r"^logging (host )?\S*\d", re.MULTILINE)
_COMUNIDAD = re.compile(r"^snmp-server community (\S+)(?: view \S+)? (RO|RW)\b")


def _bloques(texto: str) -> list[list[str]]:
    """Agrupa la configuración en bloques: una línea sin sangría y las que la siguen con sangría."""
    bloques: list[list[str]] = []
    for linea in texto.replace("\r\n", "\n").split("\n"):
        if not linea.strip() or linea.startswith("!"):
            continue
        if linea.startswith(" ") and bloques:
            bloques[-1].append(linea.strip())
        else:
            bloques.append([linea.strip()])
    return bloques


def contexto_desde_texto(texto: str) -> Contexto:
    dns = DnsConfig()
    servicios: list[ServicioGestion] = []
    snmp = AgenteSNMP()
    http_restringido = False
    http = https = False
    telnet_vty: list[bool] = []  # por cada bloque vty que permite telnet: ¿tiene access-class?
    ssh_vty: list[bool] = []

    for bloque in _bloques(texto):
        cabecera = bloque[0]
        if cabecera == "ip dns server":
            dns.allow_remote_requests = True
        elif cabecera == "ip http server":
            http = True
        elif cabecera == "ip http secure-server":
            https = True
        elif cabecera.startswith("ip http access-class"):
            http_restringido = True
        elif cabecera.startswith("line vty"):
            restringido = any(linea.startswith("access-class") for linea in bloque[1:])
            for linea in bloque[1:]:
                if linea.startswith("transport input"):
                    protocolos = set(linea.split()[2:])
                    if protocolos & {"telnet", "all"}:
                        telnet_vty.append(restringido)
                    if protocolos & {"ssh", "all"}:
                        ssh_vty.append(restringido)
        elif coincidencia := _COMUNIDAD.match(cabecera):
            snmp.habilitado = True
            snmp.comunidades.append(ComunidadSNMP(nombre=coincidencia.group(1)))

    if telnet_vty:
        servicios.append(
            ServicioGestion(
                nombre="telnet",
                puerto=23,
                habilitado=True,
                texto_plano=True,
                restringido=all(telnet_vty),
            )
        )
    if ssh_vty:
        servicios.append(
            ServicioGestion(nombre="ssh", puerto=22, habilitado=True, restringido=all(ssh_vty))
        )
    if http:
        servicios.append(
            ServicioGestion(
                nombre="http",
                puerto=80,
                habilitado=True,
                texto_plano=True,
                restringido=http_restringido,
            )
        )
    if https:
        servicios.append(
            ServicioGestion(
                nombre="https", puerto=443, habilitado=True, restringido=http_restringido
            )
        )

    version = _VERSION.search(texto)
    return Contexto(
        marca="cisco",
        dns=dns,
        firewall_conocido=False,
        servicios=servicios,
        snmp=snmp,
        version=version.group(1) if version else "",
        ntp_activo=bool(_NTP.search(texto)),
        log_remoto=bool(_LOG_REMOTO.search(texto)),
    )


class CiscoIOS(Adaptador):
    marca = "cisco"
    nombre = "Cisco IOS / IOS XE"

    def contexto_desde_texto(self, texto: str) -> Contexto:
        return contexto_desde_texto(texto)

    def leer(self, sesion: SesionDeLectura) -> str:
        return sesion.run_readonly("show running-config")

    def leer_respaldo(self, sesion: SesionDeLectura) -> str:
        return sesion.run_readonly("show running-config")

    def normalizar_respaldo(self, texto: str) -> str:
        lineas = super().normalizar_respaldo(texto).split("\n")
        return "\n".join(linea for linea in lineas if not _VOLATILES.match(linea))
