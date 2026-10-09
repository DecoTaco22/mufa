"""Adaptador de MikroTik RouterOS.

Construye el Contexto a partir de texto de export (.rsc). Lo usan tanto el
modo offline (lee un archivo) como el recolector SSH (lee la salida de
`export` sobre la conexión): el parseo es el mismo en los dos casos, solo
cambia de dónde viene el texto.
"""

from __future__ import annotations

import re

from mufa.marcas.base import Adaptador
from mufa.models import (
    AgenteSNMP,
    ComunidadSNMP,
    Contexto,
    DnsConfig,
    FirewallConfig,
    ReglaFirewall,
    ServicioGestion,
)
from mufa.rsc import Comando, parsear
from mufa.snmp import VlanEnEquipo
from mufa.ssh import SesionDeLectura

# Cabecera que RouterOS agrega a cada export con la fecha y hora:
# "# 2026-10-05 12:00:00 by RouterOS 7.16" (v7) o "# oct/05/2026 12:00:00 by RouterOS 6.49".
_CABECERA_CON_FECHA = re.compile(r"^#.* by RouterOS ")
_VERSION_EN_CABECERA = re.compile(r"^#.* by RouterOS (\S+)", re.MULTILINE)
_SIN_DESTINO = {"", "0.0.0.0", "::"}


# Servicios de /ip service: (puerto, habilitado por defecto, viaja en texto plano).
# Un export normal solo lista lo que difiere de esto; "export verbose" lista todo.
_SERVICIOS_POR_DEFECTO = {
    "telnet": (23, True, True),
    "ftp": (21, True, True),
    "www": (80, True, True),
    "api": (8728, True, True),
    "ssh": (22, True, False),
    "winbox": (8291, True, False),
    "www-ssl": (443, False, False),
    "api-ssl": (8729, True, False),
}
_SIN_RESTRICCION = {"", "0.0.0.0/0", "::/0"}


def _restringido(direcciones: str) -> bool:
    redes = {d.strip() for d in direcciones.split(",")}
    return not redes & _SIN_RESTRICCION


def _nombre(comando: Comando) -> str:
    """El objeto de "set telnet ..." o de "set [ find name=telnet ] ..."."""
    argumentos = [a for a in comando.argumentos if a not in ("[", "]", "find")]
    return argumentos[0] if argumentos else comando.propiedades.get("name", "")


def _servicios_por_defecto() -> dict[str, ServicioGestion]:
    return {
        nombre: ServicioGestion(
            nombre=nombre, puerto=puerto, habilitado=habilitado, texto_plano=texto_plano
        )
        for nombre, (puerto, habilitado, texto_plano) in _SERVICIOS_POR_DEFECTO.items()
    }


def contexto_desde_texto(texto: str) -> Contexto:
    dns = DnsConfig()
    reglas: list[ReglaFirewall] = []
    # Solo se evalúan servicios y SNMP si el export los incluye: un export
    # parcial (por ejemplo solo del firewall) no dice nada sobre ellos.
    servicios: dict[str, ServicioGestion] | None = None
    snmp: AgenteSNMP | None = None
    comunidades: dict[str, ComunidadSNMP] = {}
    ntp_activo: bool | None = None
    # Acciones de log que mandan a un servidor remoto, y las que usa alguna regla.
    acciones_remotas: set[str] = set()
    acciones_usadas: set[str] = set()
    vio_logging = False

    for comando in parsear(texto):
        props = comando.propiedades
        if comando.menu == "/ip dns" and comando.verbo == "set":
            valor = props.get("allow-remote-requests")
            if valor is not None:
                dns.allow_remote_requests = valor == "yes"

        elif comando.menu == "/ip firewall filter" and comando.verbo == "add":
            reglas.append(
                ReglaFirewall(
                    chain=props.get("chain", ""),
                    # En RouterOS, una regla sin action= es accept.
                    action=props.get("action", "accept"),
                    disabled=props.get("disabled") == "yes",
                    propiedades=props,
                )
            )

        elif comando.menu == "/ip service" and comando.verbo == "set":
            if servicios is None:
                servicios = _servicios_por_defecto()
            servicio = servicios.get(_nombre(comando))
            if servicio is not None:
                if "disabled" in props:
                    servicio.habilitado = props["disabled"] != "yes"
                if props.get("port", "").isdigit():
                    servicio.puerto = int(props["port"])
                if "address" in props:
                    servicio.restringido = _restringido(props["address"])

        elif comando.menu == "/system ntp client" and comando.verbo == "set":
            if "enabled" in props:
                ntp_activo = props["enabled"] == "yes"

        elif comando.menu == "/system logging action":
            vio_logging = True
            nombre = props.get("name") or _nombre(comando) or "remote"
            if props.get("remote", "") not in _SIN_DESTINO and (
                props.get("target") == "remote" or nombre == "remote"
            ):
                acciones_remotas.add(nombre)

        elif comando.menu == "/system logging" and comando.verbo in ("add", "set"):
            vio_logging = True
            if props.get("disabled") != "yes" and "action" in props:
                acciones_usadas.add(props["action"])

        elif comando.menu == "/snmp":
            snmp = snmp or AgenteSNMP()
            if comando.verbo == "set" and "enabled" in props:
                snmp.habilitado = props["enabled"] == "yes"

        elif comando.menu == "/snmp community":
            snmp = snmp or AgenteSNMP()
            # "set [ find default=yes ] name=x" renombra la comunidad por defecto.
            clave = "default" if props.get("default") == "yes" else props.get("name", "")
            comunidad = comunidades.setdefault(clave, ComunidadSNMP(nombre="public"))
            comunidad.nombre = props.get("name", comunidad.nombre)
            if "disabled" in props:
                comunidad.habilitada = props["disabled"] != "yes"
            # security=authorized/private: la comunidad no sirve sin SNMPv3.
            comunidad.solo_v3 = props.get("security", "none") not in ("", "none")

    if snmp is not None:
        # La comunidad "public" existe por defecto aunque el export no la nombre.
        comunidades.setdefault("default", ComunidadSNMP(nombre="public"))
        snmp.comunidades = list(comunidades.values())

    version = _VERSION_EN_CABECERA.search(texto)
    return Contexto(
        version=version.group(1) if version else "",
        ntp_activo=ntp_activo,
        log_remoto=bool(acciones_remotas & acciones_usadas) if vio_logging else None,
        marca="mikrotik",
        dns=dns,
        firewall=FirewallConfig(reglas=reglas),
        servicios=list(servicios.values()) if servicios else [],
        snmp=snmp or AgenteSNMP(),
    )


def vlans_desde_texto(texto: str) -> list[VlanEnEquipo]:
    """Las interfaces VLAN de un export: número, nombre e interfaz padre."""
    vlans = []
    for comando in parsear(texto):
        props = comando.propiedades
        if (
            comando.menu == "/interface vlan"
            and comando.verbo == "add"
            and props.get("vlan-id", "").isdigit()
        ):
            vlans.append(
                VlanEnEquipo(
                    numero=int(props["vlan-id"]),
                    nombre=props.get("name", ""),
                    interfaz=props.get("interface", ""),
                )
            )
    return vlans


class MikroTik(Adaptador):
    marca = "mikrotik"
    nombre = "MikroTik RouterOS"

    def contexto_desde_texto(self, texto: str) -> Contexto:
        return contexto_desde_texto(texto)

    def leer(self, sesion: SesionDeLectura) -> str:
        partes = [
            sesion.run_readonly("/ip dns export"),
            sesion.run_readonly("/ip firewall filter export"),
            sesion.run_readonly("/ip service export verbose"),
            sesion.run_readonly("/snmp export verbose"),
            sesion.run_readonly("/system ntp client export verbose"),
            sesion.run_readonly("/system logging export verbose"),
        ]
        return "\n".join(partes)

    def leer_vlans(self, sesion: SesionDeLectura) -> list[VlanEnEquipo] | None:
        return vlans_desde_texto(sesion.run_readonly("/interface vlan export"))

    def leer_respaldo(self, sesion: SesionDeLectura) -> str:
        # Sin show-sensitive: RouterOS 7 no incluye contraseñas en el export.
        return sesion.run_readonly("/export")

    def normalizar_respaldo(self, texto: str) -> str:
        lineas = super().normalizar_respaldo(texto).split("\n")
        return "\n".join(linea for linea in lineas if not _CABECERA_CON_FECHA.match(linea))
