"""Lectura de MikroTik por la API de RouterOS (8728, o 8729 con TLS).

Para equipos que por política no abren SSH. Ofrece la misma interfaz que
la sesión SSH (`run_readonly` con los comandos de la lista blanca), así el
adaptador de MikroTik no cambia: cada export de la lista se traduce a
consultas `print` de la API y la respuesta se escribe en formato .rsc,
que es lo que entiende el parser.

Garantía de no-daño: la única palabra de comando que sale por el socket,
además de /login, termina en "/print" (ver `_enviar_comando`).

Con API-SSL no hay CA que valide el certificado del router (casi siempre
es autofirmado), así que se fija su huella SHA-256 en la primera conexión
(trust on first use, como known_hosts de SSH): si cambia, se aborta antes
de mandar la contraseña.
"""

from __future__ import annotations

import hashlib
import re
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from mufa.security import assert_allowed


class ErrorApiRouterOS(Exception):
    """Falla de conexión o de la API. El mensaje ya está listo para mostrar."""


class CertificadoCambiado(ErrorApiRouterOS):
    pass


# --- Protocolo: palabras con prefijo de largo, oraciones terminadas en palabra vacía.


def _codificar_largo(largo: int) -> bytes:
    if largo < 0x80:
        return bytes([largo])
    if largo < 0x4000:
        return (largo | 0x8000).to_bytes(2, "big")
    if largo < 0x200000:
        return (largo | 0xC00000).to_bytes(3, "big")
    if largo < 0x10000000:
        return (largo | 0xE0000000).to_bytes(4, "big")
    return b"\xf0" + largo.to_bytes(4, "big")


def codificar_oracion(palabras: list[str]) -> bytes:
    salida = bytearray()
    for palabra in palabras:
        datos = palabra.encode("utf-8")
        salida += _codificar_largo(len(datos)) + datos
    return bytes(salida + b"\x00")


@dataclass
class Respuesta:
    tipo: str  # "!re", "!done", "!trap" o "!fatal"
    atributos: dict[str, str]


# --- Traducción de los exports de la lista blanca a consultas print.


@dataclass(frozen=True)
class _Menu:
    ruta: str  # "/ip firewall filter"
    unico: bool = False  # menús de un solo objeto ("set ..."), no listas ("add ...")
    por_nombre: bool = False  # "/ip service": "set telnet port=23 ..."


def _unico(ruta: str) -> _Menu:
    return _Menu(ruta, unico=True)


def _por_nombre(ruta: str) -> _Menu:
    return _Menu(ruta, por_nombre=True)


# Los menús del respaldo por API, en el orden de un /export (RouterOS 6 y 7).
_MENUS_RESPALDO: tuple[_Menu, ...] = (
    _unico("/system identity"),
    _unico("/system clock"),
    _unico("/system note"),
    _unico("/system ntp client"),
    _Menu("/system ntp client servers"),
    _unico("/system ntp server"),
    _Menu("/interface bridge"),
    _Menu("/interface bonding"),
    _Menu("/interface eoip"),
    _Menu("/interface gre"),
    _Menu("/interface ipip"),
    _Menu("/interface vxlan"),
    _Menu("/interface wireguard"),
    _Menu("/interface wireguard peers"),
    _Menu("/interface pppoe-client"),
    _Menu("/interface l2tp-client"),
    _Menu("/interface sstp-client"),
    _Menu("/interface ovpn-client"),
    _Menu("/interface vlan"),
    _Menu("/interface vrrp"),
    _por_nombre("/interface ethernet"),
    _Menu("/interface list"),
    _Menu("/interface list member"),
    _Menu("/interface bridge port"),
    _Menu("/interface bridge vlan"),
    _Menu("/interface wireless security-profiles"),
    _Menu("/interface wifi security"),
    _Menu("/interface wifi configuration"),
    _Menu("/interface pppoe-server server"),
    _unico("/interface l2tp-server server"),
    _unico("/interface sstp-server server"),
    _unico("/interface ovpn-server server"),
    _Menu("/ip vrf"),
    _Menu("/ip pool"),
    _Menu("/ip address"),
    _Menu("/ip dhcp-client"),
    _Menu("/ip dhcp-server"),
    _Menu("/ip dhcp-server network"),
    _Menu("/ip dhcp-server lease"),
    _unico("/ip dns"),
    _Menu("/ip dns static"),
    _Menu("/ip arp"),
    _Menu("/ip firewall address-list"),
    _Menu("/ip firewall filter"),
    _Menu("/ip firewall nat"),
    _Menu("/ip firewall mangle"),
    _Menu("/ip firewall raw"),
    _por_nombre("/ip firewall service-port"),
    _Menu("/ip hotspot profile"),
    _Menu("/ip hotspot"),
    _Menu("/ip hotspot user profile"),
    _Menu("/ip ipsec profile"),
    _Menu("/ip ipsec peer"),
    _Menu("/ip ipsec proposal"),
    _Menu("/ip ipsec identity"),
    _Menu("/ip ipsec policy"),
    _unico("/ip neighbor discovery-settings"),
    _unico("/ip settings"),
    _Menu("/ip route"),
    _Menu("/ip route rule"),
    _por_nombre("/ip service"),
    _Menu("/ipv6 address"),
    _Menu("/ipv6 route"),
    _Menu("/ipv6 pool"),
    _Menu("/ipv6 dhcp-client"),
    _Menu("/ipv6 nd"),
    _unico("/ipv6 settings"),
    _Menu("/ipv6 firewall address-list"),
    _Menu("/ipv6 firewall filter"),
    _Menu("/ipv6 firewall mangle"),
    _Menu("/ppp profile"),
    _Menu("/ppp secret"),
    _unico("/ppp aaa"),
    _Menu("/radius"),
    _unico("/radius incoming"),
    _Menu("/queue type"),
    _Menu("/queue simple"),
    _Menu("/queue tree"),
    _Menu("/routing table"),
    _Menu("/routing rule"),
    _Menu("/routing filter rule"),
    _Menu("/routing filter num-list"),
    _Menu("/routing filter community-list"),
    _Menu("/routing bgp template"),
    _Menu("/routing bgp instance"),
    _Menu("/routing bgp connection"),
    _Menu("/routing ospf instance"),
    _Menu("/routing ospf area"),
    _Menu("/routing ospf interface-template"),
    # RouterOS 6
    _Menu("/routing filter"),
    _Menu("/routing bgp peer"),
    _Menu("/routing bgp network"),
    _Menu("/routing bgp aggregate"),
    _Menu("/routing ospf network"),
    _Menu("/routing ospf interface"),
    _unico("/snmp"),
    _Menu("/snmp community"),
    _Menu("/system logging action"),
    _Menu("/system logging"),
    _Menu("/system scheduler"),
    _Menu("/system script"),
    _Menu("/tool netwatch"),
    _unico("/tool romon"),
    _Menu("/user group"),
    _unico("/user aaa"),
)


_CONSULTAS: dict[str, tuple[_Menu, ...]] = {
    "/ip dns export": (_Menu("/ip dns", unico=True),),
    "/ip firewall filter export": (_Menu("/ip firewall filter"),),
    "/ip service export verbose": (_Menu("/ip service", por_nombre=True),),
    "/snmp export verbose": (_Menu("/snmp", unico=True), _Menu("/snmp community")),
    "/interface vlan export": (_Menu("/interface vlan"),),
    "/system ntp client export verbose": (_Menu("/system ntp client", unico=True),),
    "/system logging export verbose": (_Menu("/system logging action"), _Menu("/system logging")),
    # Respaldo: la API no tiene /export, así que se arma leyendo los menús de la
    # configuración. Los que no existen en esa versión de RouterOS se saltan.
    "/export": _MENUS_RESPALDO,
    "/export show-sensitive": _MENUS_RESPALDO,
}

_CABECERA_RESPALDO = (
    "# Generado por mufa con la API de RouterOS (el equipo no permite SSH).\n"
    "# La API no tiene /export: se leyeron uno por uno los menús de la configuración.\n"
    "# Para un /export completo, igual al del equipo, habilita SSH para el usuario de mufa."
)

# Estado y contadores: cambian solos y no son configuración.
_VOLATIL = re.compile(
    r"^\.|byte|packet|-drop|-error|uptime|^running$|^last-|^actual-|^dynamic$|^invalid$"
    r"|^inactive$|^active|^status$|^slave$|^link-downs$|^fp-|^rx-|^tx-|^expires-after$"
    r"|^creation-time$|^immediate-gw$|^gateway-status$|^hw-offloaded$|^time$|^date$"
    r"|^dst-mac-address$|^dhcp$|^ecmp$|^connect$|^static$|^builtin$|^default-name$"
)
# Secretos: solo se guardan con "/export show-sensitive" (como en un export de verdad).
_SECRETO = re.compile(r"password|secret|passphrase|(^|-)key$")


def _valor_rsc(valor: str) -> str:
    valor = {"true": "yes", "false": "no"}.get(valor, valor)
    if valor and re.fullmatch(r"[A-Za-z0-9._:/,@+*!<>-]+", valor):
        return valor
    return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _propiedades(atributos: dict[str, str], menu: _Menu, secretos: bool = False) -> str:
    pares = []
    for clave in sorted(atributos):
        if _VOLATIL.search(clave) or (_SECRETO.search(clave) and not secretos):
            continue
        if menu.por_nombre and clave == "name":
            continue
        pares.append(f"{clave}={_valor_rsc(atributos[clave])}")
    return " ".join(pares)


def a_rsc(menu: _Menu, objetos: list[dict[str, str]], secretos: bool = False) -> str:
    lineas = [menu.ruta]
    for objeto in objetos:
        if objeto.get("dynamic") == "true":
            continue
        props = _propiedades(objeto, menu, secretos)
        if menu.unico:
            lineas.append(f"set {props}")
        elif menu.por_nombre:
            lineas.append(f"set {objeto.get('name', '')} {props}")
        else:
            lineas.append(f"add {props}")
    return "\n".join(lineas)


# --- Sesión


class SesionApiRouterOS:
    """Sesión de solo lectura por la API de RouterOS, con la interfaz de la sesión SSH."""

    def __init__(
        self,
        host: str,
        user: str,
        password: str | None = None,
        port: int = 8728,
        tls: bool = False,
        timeout: float = 10.0,
        certificados: Path | None = None,
    ) -> None:
        self._host = host
        self._user = user
        self._password = password or ""
        self._port = port
        self._tls = tls
        self._timeout = timeout
        self._certificados = certificados
        self._socket: socket.socket | None = None
        self._pendiente = b""

    def __enter__(self) -> Self:
        try:
            crudo = socket.create_connection((self._host, self._port), timeout=self._timeout)
        except ConnectionRefusedError:
            raise ErrorApiRouterOS(
                f"el puerto {self._port} rechazó la conexión: revisa que el servicio "
                f"{'api-ssl' if self._tls else 'api'} esté habilitado en /ip service"
            ) from None
        except TimeoutError:
            raise ErrorApiRouterOS(
                f"el puerto {self._port} no responde: revisa en /ip service que 'Available From' "
                "del servicio incluya la IP de mufa, y el firewall del equipo"
            ) from None
        except OSError as error:
            raise ErrorApiRouterOS(f"no se pudo conectar: {error}") from None
        try:
            self._socket = self._envolver_tls(crudo) if self._tls else crudo
            self._login()
        except BaseException:
            crudo.close()
            raise
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        if self._socket is not None:
            self._socket.close()

    def _envolver_tls(self, crudo: socket.socket) -> socket.socket:
        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # Sin CA: la identidad la da la huella fijada (ver docstring del módulo).
        contexto.check_hostname = False
        contexto.verify_mode = ssl.CERT_NONE
        try:
            envuelto = contexto.wrap_socket(crudo)
        except ssl.SSLError as error:
            raise ErrorApiRouterOS(
                "no se pudo negociar TLS con api-ssl. RouterOS necesita un certificado "
                f"asignado al servicio api-ssl (/ip service). Detalle: {error.reason}"
            ) from None
        der = envuelto.getpeercert(binary_form=True)
        if not der:
            raise ErrorApiRouterOS("el equipo no presentó certificado en api-ssl")
        self._verificar_huella(hashlib.sha256(der).hexdigest())
        return envuelto

    def _verificar_huella(self, huella: str) -> None:
        if self._certificados is None:
            return
        destino = f"{self._host}:{self._port}"
        self._certificados.parent.mkdir(parents=True, exist_ok=True)
        self._certificados.touch(exist_ok=True)
        conocidas = dict(
            linea.split(" ", 1)
            for linea in self._certificados.read_text(encoding="utf-8").splitlines()
            if " " in linea
        )
        guardada = conocidas.get(destino)
        if guardada is None:
            with self._certificados.open("a", encoding="utf-8") as archivo:
                archivo.write(f"{destino} {huella}\n")
        elif guardada != huella:
            raise CertificadoCambiado(
                "el certificado api-ssl del equipo no coincide con el guardado: posible "
                "suplantación. Si se cambió el certificado, hay que confirmar el nuevo."
            )

    # --- E/S de bajo nivel

    def _recibir(self, cantidad: int) -> bytes:
        assert self._socket is not None
        while len(self._pendiente) < cantidad:
            try:
                bloque = self._socket.recv(65536)
            except TimeoutError:
                raise ErrorApiRouterOS("el equipo dejó de responder en la API") from None
            if not bloque:
                raise ErrorApiRouterOS("el equipo cerró la conexión de la API")
            self._pendiente += bloque
        datos, self._pendiente = self._pendiente[:cantidad], self._pendiente[cantidad:]
        return datos

    def _leer_largo(self) -> int:
        primero = self._recibir(1)[0]
        if primero < 0x80:
            return primero
        if primero < 0xC0:
            return ((primero & 0x3F) << 8) | self._recibir(1)[0]
        if primero < 0xE0:
            return ((primero & 0x1F) << 16) | int.from_bytes(self._recibir(2), "big")
        if primero < 0xF0:
            return ((primero & 0x0F) << 24) | int.from_bytes(self._recibir(3), "big")
        return int.from_bytes(self._recibir(4), "big")

    def _leer_respuesta(self) -> Respuesta:
        palabras = []
        while largo := self._leer_largo():
            palabras.append(self._recibir(largo).decode("utf-8", errors="replace"))
        if not palabras:
            return self._leer_respuesta()
        atributos = {}
        for palabra in palabras[1:]:
            if palabra.startswith("="):
                clave, _, valor = palabra[1:].partition("=")
                atributos[clave] = valor
        return Respuesta(palabras[0], atributos)

    def _enviar_comando(self, comando: str, *atributos: str) -> list[Respuesta]:
        # La garantía de no-daño de la API: solo se consulta.
        if comando != "/login" and not comando.endswith("/print"):
            raise ValueError(f"comando de API no autorizado: {comando!r}")
        assert self._socket is not None
        self._socket.sendall(codificar_oracion([comando, *atributos]))
        respuestas = []
        while True:
            respuesta = self._leer_respuesta()
            respuestas.append(respuesta)
            if respuesta.tipo == "!fatal":
                raise ErrorApiRouterOS(f"la API cerró la sesión: {respuesta.atributos}")
            if respuesta.tipo == "!done":
                return respuestas

    def _login(self) -> None:
        respuestas = self._enviar_comando(
            "/login", f"=name={self._user}", f"=password={self._password}"
        )
        reto = respuestas[-1].atributos.get("ret")
        if reto and not any(r.tipo == "!trap" for r in respuestas):
            # RouterOS anterior a 6.43: desafío MD5.
            resumen = hashlib.md5(
                b"\x00" + self._password.encode("utf-8") + bytes.fromhex(reto),
                usedforsecurity=False,
            ).hexdigest()
            respuestas = self._enviar_comando(
                "/login", f"=name={self._user}", f"=response=00{resumen}"
            )
        if any(r.tipo == "!trap" for r in respuestas):
            raise ErrorApiRouterOS(
                "la API rechazó el usuario o la contraseña (o el grupo del usuario no tiene "
                "la política 'api')"
            )

    def imprimir(self, menu: str) -> list[dict[str, str]] | None:
        """Los objetos de un menú; None si esta versión de RouterOS no lo tiene."""
        respuestas = self._enviar_comando(menu.replace(" ", "/") + "/print")
        if any(r.tipo == "!trap" for r in respuestas):
            return None
        return [r.atributos for r in respuestas if r.tipo == "!re"]

    def run_readonly(self, command: str) -> str:
        """Ejecuta un export de la lista blanca, traducido a consultas print de la API."""
        assert_allowed(command, "mikrotik")
        partes = [_CABECERA_RESPALDO] if command.startswith("/export") else []
        secretos = command == "/export show-sensitive"
        for menu in _CONSULTAS[command]:
            objetos = self.imprimir(menu.ruta)
            if objetos:
                partes.append(a_rsc(menu, objetos, secretos))
        return "\n".join(partes) + "\n"
