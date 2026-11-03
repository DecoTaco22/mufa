"""Adaptador de Huawei VRP (routers AR/NE y switches S/CE).

Lee `display current-configuration`, el mismo comando del respaldo. Traduce al
Contexto los servicios de gestión (Telnet, STelnet/SSH, HTTP), las comunidades
SNMP, NTP y el envío de logs (info-center). Las ACL todavía no se evalúan: por
eso el Contexto declara firewall_conocido=False, y una línea vty con «acl ...
inbound» cuenta como acceso restringido.

Las comunidades SNMP guardadas con «cipher» no se pueden leer: no se dan por
débiles.
"""

from __future__ import annotations

import re

from mufa.marcas.base import Adaptador
from mufa.marcas.otras import SoloRespaldo
from mufa.models import AgenteSNMP, ComunidadSNMP, Contexto, ServicioGestion
from mufa.ssh import SesionDeLectura

COMANDO = "display current-configuration"
_RESPALDO = SoloRespaldo(
    "huawei",
    "Huawei VRP",
    (COMANDO,),
    re.compile(r"^\s*!(Software Version|Last configuration was|Time:|\s*Last )"),
)
_VERSION = re.compile(r"^\s*!Software Version (\S+)", re.MULTILINE)
_NTP = re.compile(r"^\s*ntp-service unicast-(server|peer) ", re.MULTILINE)
_LOG_REMOTO = re.compile(r"^\s*info-center loghost (?!source)\S", re.MULTILINE)


def _bloques(texto: str) -> list[list[str]]:
    """Agrupa la configuración: una línea sin sangría y las que la siguen con sangría.

    En VRP los bloques se separan con «#» y algunas órdenes globales vienen con
    un espacio adelante (« ntp-service ...»): esas también son bloques propios.
    """
    bloques: list[list[str]] = []
    abierto = False  # el último bloque admite líneas con sangría (user-interface, interface...)
    for linea in texto.replace("\r\n", "\n").split("\n"):
        limpia = linea.strip()
        if not limpia or limpia.startswith("!"):
            continue
        if limpia == "#":
            abierto = False
            continue
        if linea.startswith(" ") and abierto and bloques:
            bloques[-1].append(limpia)
        else:
            bloques.append([limpia])
            abierto = not linea.startswith(" ")
    return bloques


def _comunidad(linea: str) -> ComunidadSNMP | None:
    """«snmp-agent community read [cipher] NOMBRE [acl 2000]» -> la comunidad."""
    partes = linea.split()
    if len(partes) < 4 or partes[2] not in {"read", "write"}:
        return None
    resto = partes[3:]
    if resto and resto[0] == "cipher":
        # Cifrada en la configuración: no se sabe cuál es (no se da por débil).
        return ComunidadSNMP(nombre="(cifrada)")
    return ComunidadSNMP(nombre=resto[0]) if resto else None


def contexto_desde_texto(texto: str) -> Contexto:
    servicios: list[ServicioGestion] = []
    snmp = AgenteSNMP()
    telnet_servidor: bool | None = None  # None: la configuración no lo dice
    ssh_servidor = False
    http = https = False
    http_restringido = False
    telnet_vty: list[bool] = []  # por cada bloque vty que acepta telnet: ¿tiene acl?
    ssh_vty: list[bool] = []

    for bloque in _bloques(texto):
        cabecera = bloque[0]
        if cabecera == "telnet server enable":
            telnet_servidor = True
        elif cabecera == "undo telnet server enable":
            telnet_servidor = False
        elif cabecera in {"stelnet server enable", "ssh server enable"}:
            ssh_servidor = True
        elif cabecera == "http server enable":
            http = True
        elif cabecera == "http secure-server enable":
            https = True
        elif cabecera.startswith(("http acl ", "http server-source")):
            http_restringido = True
        elif cabecera == "snmp-agent":
            snmp.habilitado = True
        elif cabecera.startswith("snmp-agent community "):
            snmp.habilitado = True
            if comunidad := _comunidad(cabecera):
                snmp.comunidades.append(comunidad)
        elif cabecera.startswith(("user-interface vty", "line vty")):
            restringido = any(re.match(r"acl (ipv6 )?\S+ inbound", linea) for linea in bloque[1:])
            protocolo = next(
                (linea.split()[2] for linea in bloque[1:] if linea.startswith("protocol inbound")),
                None,
            )
            if protocolo in {"telnet", "all"}:
                telnet_vty.append(restringido)
            if protocolo in {"ssh", "all"}:
                ssh_vty.append(restringido)
            if protocolo is None:
                # Sin «protocol inbound»: acepta lo que el servidor tenga encendido.
                telnet_vty.append(restringido)
                ssh_vty.append(restringido)

    # Telnet: hace falta el servidor encendido y una línea vty que lo acepte.
    if (
        telnet_servidor is not False
        and telnet_vty
        and (telnet_servidor or _telnet_explicito(texto))
    ):
        servicios.append(
            ServicioGestion(
                nombre="telnet",
                puerto=23,
                habilitado=True,
                texto_plano=True,
                restringido=all(telnet_vty),
            )
        )
    if ssh_servidor and ssh_vty:
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
        marca="huawei",
        firewall_conocido=False,
        servicios=servicios,
        snmp=snmp,
        version=version.group(1) if version else "",
        ntp_activo=bool(_NTP.search(texto)),
        log_remoto=bool(_LOG_REMOTO.search(texto)),
    )


def _telnet_explicito(texto: str) -> bool:
    """Una línea vty que pide telnet a propósito («protocol inbound telnet» o «all»)."""
    return bool(re.search(r"^\s*protocol inbound (telnet|all)\s*$", texto, re.MULTILINE))


class HuaweiVRP(Adaptador):
    marca = "huawei"
    nombre = "Huawei VRP"

    def contexto_desde_texto(self, texto: str) -> Contexto:
        return contexto_desde_texto(texto)

    def leer(self, sesion: SesionDeLectura) -> str:
        return _RESPALDO.leer_respaldo(sesion)

    def leer_respaldo(self, sesion: SesionDeLectura) -> str:
        return _RESPALDO.leer_respaldo(sesion)

    def normalizar_respaldo(self, texto: str) -> str:
        return _RESPALDO.normalizar_respaldo(texto)
