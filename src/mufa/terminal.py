"""Terminal interactiva hacia un equipo: SSH, Telnet o puerto serie.

A diferencia del resto de mufa, que solo consulta, acá escribe la persona:
cada tecla que manda la terminal de la app llega tal cual al equipo. mufa
no agrega ni ejecuta nada por su cuenta. Se registra quién abrió la sesión,
hacia dónde y cuánto duró; no lo que se escribió (puede incluir claves).
"""

from __future__ import annotations

import base64
import hashlib
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import paramiko

from mufa.ssh import SHA1, es_incompatible

TERMINAL = "xterm-256color"


class ErrorDeTerminal(Exception):
    pass


class Conexion(Protocol):
    def recibir(self) -> bytes:
        """Bloquea hasta que llega algo. b"" = la conexión terminó."""
        ...

    def enviar(self, datos: bytes) -> None: ...

    def redimensionar(self, columnas: int, filas: int) -> None: ...

    def cerrar(self) -> None: ...


# --- SSH


_CAMBIADA = (
    "la clave SSH de {host} cambió desde la última conexión. Si reinstalaste el equipo "
    "es normal; si no, alguien podría estar haciéndose pasar por él."
)


@dataclass(frozen=True)
class Huella:
    tipo: str
    sha256: str


def huella_sha256(clave: paramiko.PKey) -> str:
    """La huella como la muestran OpenSSH y PuTTY: SHA256:base64 sin relleno."""
    digest = hashlib.sha256(clave.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


# Recibe la clave que presenta el equipo y, si había otra guardada, esa. Devuelve
# "guardar", "una_vez", "reemplazar" (solo con clave anterior) o "cancelar".
Confirmar = Callable[[Huella, Huella | None], str]


class ConexionSSH:
    """Shell interactivo por SSH, para cualquier marca (MikroTik, Cisco, Huawei, Juniper…).

    - La clave del equipo se verifica como en el resto de mufa: la primera vez se
      guarda; si después cambia, no se conecta (no se le manda la contraseña a un
      equipo que se hace pasar por otro).
    - Se entra como PuTTY: con «password» y, si el equipo lo rechaza o no lo ofrece,
      con «keyboard-interactive» (Cisco y Huawei con AAA/TACACS suelen exigirlo).
    """

    def __init__(
        self,
        host: str,
        puerto: int,
        usuario: str,
        password: str | None,
        known_hosts: Path,
        columnas: int = 120,
        filas: int = 32,
        timeout: float = 10.0,
        confirmar: Confirmar | None = None,
    ) -> None:
        self._transporte: paramiko.Transport | None = None
        self._confirmar = confirmar
        # True si el equipo solo habla algoritmos con SHA-1 (se avisa en la terminal).
        self.legado = False
        try:
            self._negociar(host, puerto, timeout, sin_sha1=True)
        except paramiko.SSHException as error:
            if not es_incompatible(error):
                self.cerrar()
                raise self._explicar(error, host, puerto) from None
            self.cerrar()
            self.legado = True
            try:
                self._negociar(host, puerto, timeout, sin_sha1=False)
            except (OSError, EOFError, paramiko.SSHException) as otro:
                self.cerrar()
                raise self._explicar(otro, host, puerto) from None
        except ErrorDeTerminal:
            self.cerrar()
            raise
        except (OSError, EOFError) as error:
            self.cerrar()
            raise self._explicar(error, host, puerto) from None
        try:
            self._verificar_clave(host, puerto, known_hosts)
            self._autenticar(host, usuario, password or "", timeout)
            transporte = self._transporte
            assert transporte is not None
            self._canal: paramiko.Channel = transporte.open_session(timeout=timeout)
            self._canal.get_pty(term=TERMINAL, width=columnas, height=filas)
            self._canal.invoke_shell()
        except ErrorDeTerminal:
            self.cerrar()
            raise
        except (OSError, EOFError, paramiko.SSHException) as error:
            self.cerrar()
            raise self._explicar(error, host, puerto) from None

    def _negociar(self, host: str, puerto: int, timeout: float, sin_sha1: bool) -> None:
        try:
            sock = socket.create_connection((host, puerto), timeout=timeout)
        except ConnectionRefusedError:
            raise ErrorDeTerminal(
                f"{host}:{puerto} rechazó la conexión: el SSH está apagado o en otro puerto"
            ) from None
        except TimeoutError:
            raise ErrorDeTerminal(
                f"{host}:{puerto} no responde: un firewall lo filtra o el equipo no es alcanzable"
            ) from None
        except OSError as error:
            raise ErrorDeTerminal(f"no se pudo conectar a {host}:{puerto}: {error}") from None
        self._transporte = paramiko.Transport(sock, disabled_algorithms=SHA1 if sin_sha1 else None)
        self._transporte.banner_timeout = timeout
        self._transporte.start_client(timeout=timeout)

    @staticmethod
    def _explicar(error: BaseException, host: str, puerto: int) -> ErrorDeTerminal:
        if isinstance(error, ErrorDeTerminal):
            return error
        texto = str(error)
        if isinstance(error, ConnectionRefusedError):
            return ErrorDeTerminal(
                f"{host}:{puerto} rechazó la conexión: el SSH está apagado o en otro puerto"
            )
        if isinstance(error, TimeoutError):
            return ErrorDeTerminal(
                f"{host}:{puerto} no responde: un firewall lo filtra o el equipo no es alcanzable"
            )
        if "banner" in texto.lower() or isinstance(error, (ConnectionResetError, EOFError)):
            return ErrorDeTerminal(
                f"{host} cortó la conexión antes de saludar. Suele ser un bloqueo por "
                "intentos fallidos (Cisco «login block-for»: espera unos minutos), todas "
                "las líneas VTY ocupadas, o una ACL que no permite esta IP."
            )
        if es_incompatible(error):
            return ErrorDeTerminal(f"{host} solo habla algoritmos SSH que mufa no conoce: {texto}")
        return ErrorDeTerminal(f"no se pudo conectar a {host}:{puerto}: {texto}")

    def _verificar_clave(self, host: str, puerto: int, known_hosts: Path) -> None:
        """Como PuTTY: un equipo nuevo o con clave distinta se le muestra a la persona con su
        huella, y ella decide. Sin quien confirme (pruebas, tareas), se guarda la primera."""
        assert self._transporte is not None
        known_hosts.parent.mkdir(parents=True, exist_ok=True)
        known_hosts.touch(exist_ok=True)
        claves = paramiko.HostKeys(str(known_hosts))
        nombre = host if puerto == 22 else f"[{host}]:{puerto}"
        clave = self._transporte.get_remote_server_key()
        guardadas = claves.lookup(nombre)
        nueva = Huella(clave.get_name(), huella_sha256(clave))
        if guardadas and guardadas.get(clave.get_name()) == clave:
            return
        # También si llega con otro tipo de clave: no se acepta como «nueva».
        anterior = None
        if guardadas:
            vieja = next(iter(guardadas.values()))
            anterior = Huella(vieja.get_name(), huella_sha256(vieja))
        if self._confirmar is None:
            if anterior is not None:
                raise ErrorDeTerminal(_CAMBIADA.format(host=host))
            decision = "guardar"
        else:
            decision = self._confirmar(nueva, anterior)
        if decision == "cancelar" or (anterior is not None and decision != "reemplazar"):
            raise ErrorDeTerminal(
                _CAMBIADA.format(host=host)
                if anterior
                else "conexión cancelada: no confiaste en la clave del equipo"
            )
        if decision in ("guardar", "reemplazar"):
            if anterior is not None:
                # Fuera toda clave vieja de este equipo, de cualquier tipo.
                lineas = known_hosts.read_text(encoding="utf-8").splitlines()
                quedan = [
                    linea for linea in lineas if nombre not in linea.split(" ", 1)[0].split(",")
                ]
                known_hosts.write_text("".join(f"{linea}\n" for linea in quedan), encoding="utf-8")
                claves = paramiko.HostKeys(str(known_hosts))
            claves.add(nombre, clave.get_name(), clave)
            claves.save(str(known_hosts))
        # "una_vez": se conecta sin guardar la clave.

    def _autenticar(self, host: str, usuario: str, password: str, timeout: float) -> None:
        assert self._transporte is not None
        transporte = self._transporte
        metodos: list[str] = []
        try:
            transporte.auth_none(usuario)
            return  # el equipo no pide contraseña
        except paramiko.BadAuthenticationType as error:
            metodos = list(error.allowed_types)
        except paramiko.AuthenticationException:
            metodos = ["password", "keyboard-interactive"]

        def responder(
            _titulo: str, _instrucciones: str, preguntas: list[tuple[str, bool]]
        ) -> list[str]:
            # Cada pregunta oculta (Password:, Contraseña:) se contesta con la contraseña.
            return [password if not visible else usuario for _texto, visible in preguntas]

        intentos = [m for m in ("password", "keyboard-interactive") if m in metodos]
        if not intentos:
            raise ErrorDeTerminal(
                f"{host} no acepta entrar con contraseña (acepta: {', '.join(metodos) or 'nada'})"
            )
        for metodo in intentos:
            try:
                if metodo == "password":
                    transporte.auth_password(usuario, password, fallback=False)
                else:
                    transporte.auth_interactive(usuario, responder)
                if transporte.is_authenticated():
                    return
            except paramiko.BadAuthenticationType:
                continue
            except paramiko.AuthenticationException:
                if not transporte.is_active():
                    break
                continue
        raise ErrorDeTerminal(
            f"{host} rechazó el usuario {usuario!r} o su contraseña (probé "
            f"{' y '.join(intentos)}). Revisa en el equipo que el usuario tenga permiso de "
            "entrar por SSH: en MikroTik la política «ssh» y su «Allowed Address»; en "
            "Cisco/Huawei, la configuración de AAA y de las líneas VTY."
        )

    def recibir(self) -> bytes:
        try:
            return bytes(self._canal.recv(32768))
        except OSError:
            return b""

    def enviar(self, datos: bytes) -> None:
        self._canal.sendall(datos)

    def redimensionar(self, columnas: int, filas: int) -> None:
        self._canal.resize_pty(width=columnas, height=filas)

    def cerrar(self) -> None:
        if self._transporte is not None:
            self._transporte.close()


# --- Telnet (telnetlib ya no existe en Python 3.13: lo justo del protocolo, RFC 854)

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
ECHO, SGA, TTYPE, NAWS = 1, 3, 24, 31


class ConexionTelnet:
    def __init__(
        self, host: str, puerto: int, columnas: int = 120, filas: int = 32, timeout: float = 10.0
    ) -> None:
        try:
            self._socket = socket.create_connection((host, puerto), timeout=timeout)
        except OSError as error:
            raise ErrorDeTerminal(f"no se pudo conectar a {host}:{puerto}: {error}") from None
        self._socket.settimeout(None)
        self._tamano = (columnas, filas)
        self._naws = False
        self._envio = threading.Lock()
        self._pendiente = b""

    def _responder(self, *bytes_: int) -> None:
        with self._envio:
            self._socket.sendall(bytes(bytes_))

    def _mandar_tamano(self) -> None:
        columnas, filas = self._tamano
        cuerpo = bytes([columnas >> 8, columnas & 255, filas >> 8, filas & 255])
        cuerpo = cuerpo.replace(bytes([IAC]), bytes([IAC, IAC]))
        with self._envio:
            self._socket.sendall(bytes([IAC, SB, NAWS]) + cuerpo + bytes([IAC, SE]))

    def _negociar(self, orden: int, opcion: int) -> None:
        if orden == DO:
            if opcion == NAWS:
                self._naws = True
                self._responder(IAC, WILL, NAWS)
                self._mandar_tamano()
            elif opcion == TTYPE:
                self._responder(IAC, WILL, TTYPE)
            else:
                self._responder(IAC, WONT, opcion)
        elif orden == WILL:
            self._responder(IAC, DO if opcion in (ECHO, SGA) else DONT, opcion)

    def _subnegociar(self, datos: bytes) -> None:
        # TTYPE SEND -> TTYPE IS "XTERM"
        if len(datos) >= 2 and datos[0] == TTYPE and datos[1] == 1:
            with self._envio:
                self._socket.sendall(bytes([IAC, SB, TTYPE, 0]) + b"XTERM" + bytes([IAC, SE]))

    def filtrar(self, datos: bytes) -> bytes:
        """Saca los comandos del protocolo (y los contesta); devuelve solo el texto."""
        datos = self._pendiente + datos
        self._pendiente = b""
        salida = bytearray()
        i = 0
        while i < len(datos):
            b = datos[i]
            if b != IAC:
                salida.append(b)
                i += 1
                continue
            if i + 1 >= len(datos):
                self._pendiente = datos[i:]
                break
            orden = datos[i + 1]
            if orden == IAC:
                salida.append(IAC)
                i += 2
            elif orden in (DO, DONT, WILL, WONT):
                if i + 2 >= len(datos):
                    self._pendiente = datos[i:]
                    break
                self._negociar(orden, datos[i + 2])
                i += 3
            elif orden == SB:
                fin = datos.find(bytes([IAC, SE]), i + 2)
                if fin == -1:
                    self._pendiente = datos[i:]
                    break
                self._subnegociar(datos[i + 2 : fin])
                i = fin + 2
            else:
                i += 2
        return bytes(salida)

    def recibir(self) -> bytes:
        while True:
            try:
                datos = self._socket.recv(32768)
            except OSError:
                return b""
            if not datos:
                return b""
            texto = self.filtrar(datos)
            if texto:
                return texto

    def enviar(self, datos: bytes) -> None:
        with self._envio:
            self._socket.sendall(datos.replace(bytes([IAC]), bytes([IAC, IAC])))

    def redimensionar(self, columnas: int, filas: int) -> None:
        self._tamano = (columnas, filas)
        if self._naws:
            self._mandar_tamano()

    def cerrar(self) -> None:
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._socket.close()


# --- Puerto serie (consola de un equipo con cable USB-serial)

PARIDADES = {"N": "N", "E": "E", "O": "O"}


def puertos_serie() -> list[dict[str, str]]:
    from serial.tools import list_ports

    return [
        {"puerto": p.device, "descripcion": p.description or p.device}
        for p in sorted(list_ports.comports(), key=lambda p: p.device)
    ]


class ConexionSerial:
    def __init__(
        self, puerto: str, baudios: int = 115200, bits: int = 8, paridad: str = "N", parada: int = 1
    ) -> None:
        import serial

        if puerto not in {p["puerto"] for p in puertos_serie()}:
            raise ErrorDeTerminal(f"el puerto {puerto} no existe en esta computadora")
        try:
            self._serial = serial.Serial(
                puerto,
                baudrate=baudios,
                bytesize=bits,
                parity=PARIDADES.get(paridad, "N"),
                stopbits=parada,
                timeout=0.2,
            )
        except (serial.SerialException, ValueError) as error:
            raise ErrorDeTerminal(f"no se pudo abrir {puerto}: {error}") from None
        self._abierto = True

    def recibir(self) -> bytes:
        while self._abierto:
            try:
                datos = self._serial.read(self._serial.in_waiting or 1)
            except Exception:  # noqa: BLE001 - el cable se desconectó
                return b""
            if datos:
                return bytes(datos)
        return b""

    def enviar(self, datos: bytes) -> None:
        self._serial.write(datos)

    def redimensionar(self, columnas: int, filas: int) -> None:
        pass  # una consola serie no sabe de tamaños

    def cerrar(self) -> None:
        self._abierto = False
        self._serial.close()
