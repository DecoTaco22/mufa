"""Modelos de datos: hallazgos y contexto de auditoría."""

from __future__ import annotations

import ipaddress
from enum import Enum

from pydantic import BaseModel, Field


class Severidad(str, Enum):
    CRITICO = "crítico"
    ALTO = "alto"
    MEDIO = "medio"
    INFO = "info"


class Hallazgo(BaseModel):
    id: str
    severidad: Severidad
    titulo: str
    evidencia: str
    impacto: str
    remediacion: list[str]
    referencia: str = ""


class DnsConfig(BaseModel):
    allow_remote_requests: bool = False


class ServicioGestion(BaseModel):
    """Un servicio de gestión del equipo (telnet, ssh, winbox, http...)."""

    nombre: str
    protocolo: str = "tcp"
    puerto: int
    habilitado: bool
    # Si el servicio solo acepta conexiones de ciertas redes (address= en
    # RouterOS, access-class en Cisco).
    restringido: bool = False
    texto_plano: bool = False


class ComunidadSNMP(BaseModel):
    nombre: str
    habilitada: bool = True
    solo_v3: bool = False


class AgenteSNMP(BaseModel):
    habilitado: bool = False
    comunidades: list[ComunidadSNMP] = Field(default_factory=list)


class Coincide(Enum):
    """Si una regla aplica a un paquete hipotético: sí, no, o no se puede saber."""

    SI = "sí"
    NO = "no"
    QUIZAS = "quizás"


class PaqueteEntrante(BaseModel):
    """Paquete nuevo que llega al router desde internet (chain input)."""

    protocolo: str
    puerto: int
    interface_list: str = "WAN"


# Propiedades de una regla que no filtran paquetes: no cambian si la regla aplica.
_PROPIEDADES_NEUTRAS = {
    "chain",
    "action",
    "comment",
    "disabled",
    "log",
    "log-prefix",
    "jump-target",
    "address-list",
    "address-list-timeout",
}

_NUMERO_DE_PROTOCOLO = {"tcp": "6", "udp": "17", "icmp": "1"}

_PROFUNDIDAD_MAXIMA_DE_JUMP = 16


def _negada(valor: str) -> tuple[bool, str]:
    return (True, valor[1:]) if valor.startswith("!") else (False, valor)


def _resultado(coincide: bool, negada: bool) -> Coincide:
    return Coincide.SI if coincide != negada else Coincide.NO


def _coincide_protocolo(valor: str, protocolo: str) -> Coincide:
    negada, valor = _negada(valor)
    buscado = {protocolo, _NUMERO_DE_PROTOCOLO.get(protocolo, protocolo)}
    return _resultado(valor in buscado, negada)


def _coincide_puerto(valor: str, puerto: int) -> Coincide:
    negada, valor = _negada(valor)
    for parte in valor.split(","):
        desde, _, hasta = parte.partition("-")
        try:
            if int(desde) <= puerto <= int(hasta or desde):
                return _resultado(True, negada)
        except ValueError:
            return Coincide.QUIZAS
    return _resultado(False, negada)


def _coincide_connection_state(valor: str) -> Coincide:
    # Una consulta DNS que llega de afuera es una conexión nueva.
    negada, valor = _negada(valor)
    return _resultado("new" in valor.split(","), negada)


def _coincide_interface_list(valor: str, lista: str) -> Coincide:
    # Se asume que la interfaz de entrada está en `lista` (WAN) y en "all",
    # y en ninguna otra (en particular, no en LAN).
    negada, valor = _negada(valor)
    return _resultado(valor.upper() in (lista.upper(), "ALL"), negada)


def _coincide_dst_address(valor: str) -> Coincide:
    # El destino es la IP pública del router, que mufa no conoce. Solo se
    # puede descartar el caso de loopback (regla "accept to local loopback"
    # de la configuración por defecto).
    negada, valor = _negada(valor)
    try:
        red = ipaddress.ip_network(valor, strict=False)
    except ValueError:
        return Coincide.QUIZAS
    if red.is_loopback:
        return _resultado(False, negada)
    return Coincide.QUIZAS


def _coincide_dst_address_type(valor: str) -> Coincide:
    negada, valor = _negada(valor)
    return _resultado("local" in valor.split(","), negada)


class ReglaFirewall(BaseModel):
    chain: str
    action: str
    disabled: bool = False
    propiedades: dict[str, str] = Field(default_factory=dict)

    def coincide(self, paquete: PaqueteEntrante) -> Coincide:
        """Evalúa todos los criterios de la regla contra el paquete.

        Un criterio que mufa no sabe evaluar (in-interface, src-address,
        limit, ...) deja el resultado en QUIZAS en vez de suponer nada.
        """
        resultado = Coincide.SI
        for clave, valor in self.propiedades.items():
            if clave in _PROPIEDADES_NEUTRAS:
                continue
            if clave == "protocol":
                parcial = _coincide_protocolo(valor, paquete.protocolo)
            elif clave == "dst-port":
                parcial = _coincide_puerto(valor, paquete.puerto)
            elif clave == "connection-state":
                parcial = _coincide_connection_state(valor)
            elif clave == "in-interface-list":
                parcial = _coincide_interface_list(valor, paquete.interface_list)
            elif clave == "dst-address":
                parcial = _coincide_dst_address(valor)
            elif clave == "dst-address-type":
                parcial = _coincide_dst_address_type(valor)
            else:
                parcial = Coincide.QUIZAS

            if parcial is Coincide.NO:
                return Coincide.NO
            if parcial is Coincide.QUIZAS:
                resultado = Coincide.QUIZAS
        return resultado


class FirewallConfig(BaseModel):
    reglas: list[ReglaFirewall] = Field(default_factory=list)

    def bloquea_entrada(self, paquete: PaqueteEntrante) -> bool:
        """True solo si se puede asegurar que la chain input descarta el paquete.

        Recorre las reglas en orden, como RouterOS: la primera que aplica con
        certeza decide. Las reglas que "quizás" aplican se saltean: no se
        puede confiar en un drop dudoso, y un accept dudoso (por ejemplo
        limitado a ciertas IPs de origen) no abre el servicio a todo internet.
        Si ninguna regla decide, la política de la chain input es aceptar.
        """
        veredicto = self._evaluar_chain("input", paquete, profundidad=0)
        return veredicto in ("drop", "reject", "tarpit")

    def _evaluar_chain(self, chain: str, paquete: PaqueteEntrante, profundidad: int) -> str | None:
        if profundidad > _PROFUNDIDAD_MAXIMA_DE_JUMP:
            return None
        for regla in self.reglas:
            if regla.chain != chain or regla.disabled:
                continue
            if regla.coincide(paquete) is not Coincide.SI:
                continue
            if regla.action in ("accept", "drop", "reject", "tarpit"):
                return regla.action
            if regla.action == "return":
                return None
            if regla.action == "jump":
                destino = regla.propiedades.get("jump-target", "")
                veredicto = self._evaluar_chain(destino, paquete, profundidad + 1)
                if veredicto is not None:
                    return veredicto
            # log, passthrough, add-*-to-address-list: no terminan la chain.
        return None


class Contexto(BaseModel):
    """Configuración normalizada de un equipo, independiente de la marca.

    FirewallConfig modela hoy la semántica de RouterOS (chains, jump,
    connection-state); cada marca nueva traduce sus ACL a este mismo modelo.
    """

    marca: str = "mikrotik"
    dns: DnsConfig = Field(default_factory=DnsConfig)
    firewall: FirewallConfig = Field(default_factory=FirewallConfig)
    # False cuando la marca no traduce todavía su filtrado al modelo: en ese
    # caso no se puede afirmar que un servicio esté protegido por firewall.
    firewall_conocido: bool = True
    servicios: list[ServicioGestion] = Field(default_factory=list)
    snmp: AgenteSNMP = Field(default_factory=AgenteSNMP)
    # Versión del sistema operativo ("6.48.6", "15.2(4)E10"); vacía si no se sabe.
    version: str = ""
    # None = la configuración leída no lo dice (no se evalúa).
    ntp_activo: bool | None = None
    log_remoto: bool | None = None

    def expuesto_a_internet(self, servicio: ServicioGestion) -> bool:
        """Habilitado, sin restricción de origen y sin un drop seguro desde WAN."""
        if not servicio.habilitado or servicio.restringido:
            return False
        if not self.firewall_conocido:
            return True
        paquete = PaqueteEntrante(protocolo=servicio.protocolo, puerto=servicio.puerto)
        return not self.firewall.bloquea_entrada(paquete)
