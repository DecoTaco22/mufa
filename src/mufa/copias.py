"""Copia de los respaldos a un servidor propio: SFTP, FTPS o FTP.

Después de cada respaldo programado (o con «Enviar ahora») se sube la
última versión de cada equipo a la carpeta elegida, un archivo por equipo:

    por_equipo:  /carpeta/RT-CORE/RT-CORE_2026-10-08_1200.rsc
    por_dia:     /carpeta/2026-10-08/RT-CORE.rsc

Las configuraciones tienen secretos (comunidades SNMP, claves de VPN,
hashes de contraseñas): por eso se recomienda SFTP o FTPS. Con FTP simple
viajan sin cifrar, y la pantalla lo advierte. En SFTP la clave del
servidor se guarda la primera vez y se exige igual después, como con los
equipos.
"""

from __future__ import annotations

import ftplib
import io
import json
import re
import socket
import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

import paramiko
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mufa.cifrado import Cifrador
from mufa.db import AjusteSistema, Equipo, Respaldo, Usuario
from mufa.respaldos import contenido
from mufa.servicios import registrar
from mufa.ssh import SHA1, PoliticaTOFU, es_incompatible
from mufa.terminal import huella_sha256

Protocolo = Literal["sftp", "ftps", "ftp"]
Organizacion = Literal["por_equipo", "por_dia"]

PUERTOS: dict[str, int] = {"sftp": 22, "ftps": 21, "ftp": 21}
_ESPERA = 20.0
_DESTINO = "respaldos.destino"
_ULTIMO_ENVIO = "respaldos.ultimo_envio"
_EXTENSION = {"mikrotik": "rsc"}


# Todo lo que puede salir mal hablando con el servidor (sockets, TLS, SSH, FTP).
_FALLOS = (OSError, EOFError, ValueError, ftplib.Error, paramiko.SSHException)


class ErrorDeCopia(Exception):
    """No se pudo copiar al servidor. El mensaje ya está listo para mostrar."""


@dataclass
class Destino:
    activo: bool = False
    protocolo: Protocolo = "sftp"
    host: str = ""
    puerto: int = 22
    usuario: str = ""
    password_cifrada: str = ""
    carpeta: str = "/mufa"
    organizar: Organizacion = "por_equipo"
    verificar_certificado: bool = True


@dataclass
class UltimoEnvio:
    cuando: str = ""
    ok: bool = False
    archivos: int = 0
    mensaje: str = ""


@dataclass
class ResultadoEnvio:
    archivos: int
    huella: str = ""
    rutas: list[str] = field(default_factory=list)


def _leer(db: Session, clave: str) -> dict[str, object]:
    fila = db.get(AjusteSistema, clave)
    return json.loads(fila.valor) if fila and fila.valor else {}


def _guardar(db: Session, clave: str, datos: dict[str, object]) -> None:
    fila = db.get(AjusteSistema, clave)
    valor = json.dumps(datos)
    if fila is None:
        db.add(AjusteSistema(clave=clave, valor=valor))
    else:
        fila.valor = valor


def leer_destino(db: Session) -> Destino:
    datos = _leer(db, _DESTINO)
    conocidos = Destino.__dataclass_fields__
    return Destino(**{k: v for k, v in datos.items() if k in conocidos})  # type: ignore[arg-type]


def guardar_destino(db: Session, destino: Destino) -> None:
    _guardar(db, _DESTINO, asdict(destino))


def leer_ultimo_envio(db: Session) -> UltimoEnvio | None:
    datos = _leer(db, _ULTIMO_ENVIO)
    return UltimoEnvio(**datos) if datos else None  # type: ignore[arg-type]


def carpeta_valida(carpeta: str) -> str:
    """Normaliza la carpeta de destino. No admite «..» ni caracteres de control."""
    if any(ord(c) < 32 for c in carpeta):
        raise ValueError("la carpeta tiene caracteres no válidos")
    partes = [p for p in carpeta.replace("\\", "/").split("/") if p and p != "."]
    if ".." in partes:
        raise ValueError("la carpeta no puede contener «..»")
    absoluta = carpeta.strip().startswith(("/", "\\"))
    return ("/" if absoluta else "") + "/".join(partes)


def nombre_seguro(texto: str) -> str:
    """Un nombre de equipo como nombre de archivo: sin barras, espacios ni rarezas."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", texto).strip("._") or "equipo"


def ruta_de(destino: Destino, equipo: Equipo, cuando: datetime) -> tuple[str, str]:
    """(carpeta, archivo) donde va el respaldo de `equipo`."""
    nombre = nombre_seguro(equipo.nombre)
    extension = _EXTENSION.get(equipo.marca, "cfg")
    base = carpeta_valida(destino.carpeta)

    def unir(*partes: str) -> str:
        return "/".join(p.rstrip("/") for p in (base, *partes) if p) or "/"

    if destino.organizar == "por_dia":
        return unir(cuando.strftime("%Y-%m-%d")), f"{nombre}.{extension}"
    return unir(nombre), f"{nombre}_{cuando.strftime('%Y-%m-%d_%H%M')}.{extension}"


class _Conexion(Protocol):
    huella: str

    def subir(self, carpeta: str, archivo: str, datos: bytes) -> None: ...

    def preparar(self, carpeta: str) -> None: ...


class _SFTP:
    def __init__(self, destino: Destino, password: str, known_hosts: Path) -> None:
        known_hosts.parent.mkdir(parents=True, exist_ok=True)
        known_hosts.touch(exist_ok=True)
        self._cliente = self._conectar(destino, password, known_hosts, sin_sha1=True)
        transporte = self._cliente.get_transport()
        assert transporte is not None
        self.huella = huella_sha256(transporte.get_remote_server_key())
        self._sftp = self._cliente.open_sftp()

    @staticmethod
    def _conectar(
        destino: Destino, password: str, known_hosts: Path, sin_sha1: bool
    ) -> paramiko.SSHClient:
        cliente = paramiko.SSHClient()
        cliente.load_host_keys(str(known_hosts))
        cliente.set_missing_host_key_policy(PoliticaTOFU(known_hosts))
        try:
            cliente.connect(
                destino.host,
                port=destino.puerto,
                username=destino.usuario,
                password=password or None,
                timeout=_ESPERA,
                look_for_keys=False,
                allow_agent=False,
                disabled_algorithms=SHA1 if sin_sha1 else None,
            )
        except paramiko.SSHException as error:
            cliente.close()
            if sin_sha1 and es_incompatible(error):
                return _SFTP._conectar(destino, password, known_hosts, sin_sha1=False)
            raise
        return cliente

    def preparar(self, carpeta: str) -> None:
        actual = "/" if carpeta.startswith("/") else ""
        for parte in [p for p in carpeta.split("/") if p]:
            actual = f"{actual.rstrip('/')}/{parte}" if actual else parte
            try:
                self._sftp.stat(actual)
            except OSError:
                self._sftp.mkdir(actual)

    def subir(self, carpeta: str, archivo: str, datos: bytes) -> None:
        self.preparar(carpeta)
        self._sftp.putfo(io.BytesIO(datos), f"{carpeta.rstrip('/')}/{archivo}")

    def cerrar(self) -> None:
        self._sftp.close()
        self._cliente.close()


class _FTP:
    def __init__(self, destino: Destino, password: str) -> None:
        self.huella = ""
        if destino.protocolo == "ftps":
            contexto = ssl.create_default_context()
            if not destino.verificar_certificado:
                contexto.check_hostname = False
                contexto.verify_mode = ssl.CERT_NONE
            self._ftp: ftplib.FTP = ftplib.FTP_TLS(context=contexto, timeout=_ESPERA)
        else:
            self._ftp = ftplib.FTP(timeout=_ESPERA)
        self._ftp.connect(destino.host, destino.puerto)
        if isinstance(self._ftp, ftplib.FTP_TLS):
            self._ftp.auth()  # cifra antes de mandar el usuario y la contraseña
        self._ftp.login(destino.usuario or "anonymous", password)
        if isinstance(self._ftp, ftplib.FTP_TLS):
            self._ftp.prot_p()  # y también los archivos
        self._inicio = self._ftp.pwd()

    def preparar(self, carpeta: str) -> None:
        self._ftp.cwd("/" if carpeta.startswith("/") else self._inicio)
        for parte in [p for p in carpeta.split("/") if p]:
            try:
                self._ftp.cwd(parte)
            except ftplib.error_perm:
                self._ftp.mkd(parte)
                self._ftp.cwd(parte)

    def subir(self, carpeta: str, archivo: str, datos: bytes) -> None:
        self.preparar(carpeta)
        self._ftp.storbinary(f"STOR {archivo}", io.BytesIO(datos))

    def cerrar(self) -> None:
        try:
            self._ftp.quit()
        except (ftplib.Error, OSError):
            self._ftp.close()


def _explicar(error: BaseException, destino: Destino) -> ErrorDeCopia:
    donde = f"{destino.host}:{destino.puerto}"
    if isinstance(error, paramiko.BadHostKeyException):
        return ErrorDeCopia(
            f"la clave SSH de {destino.host} no coincide con la guardada: posible suplantación. "
            "Si el servidor se reinstaló, borra su línea del archivo known_hosts de mufa."
        )
    if isinstance(error, paramiko.AuthenticationException):
        return ErrorDeCopia("el servidor rechazó el usuario o la contraseña")
    if isinstance(error, ftplib.error_perm) and str(error).startswith("530"):
        return ErrorDeCopia("el servidor rechazó el usuario o la contraseña")
    if isinstance(error, ssl.SSLCertVerificationError):
        return ErrorDeCopia(
            "el certificado del servidor no es válido para ese nombre. Si es un certificado "
            "propio (NAS, servidor interno), desmarca «Verificar el certificado»."
        )
    if isinstance(error, ssl.SSLError):
        return ErrorDeCopia(f"no se pudo cifrar la conexión con {donde}: ¿el servidor acepta FTPS?")
    if isinstance(error, TimeoutError | socket.timeout):
        return ErrorDeCopia(f"{donde} no responde: revisa la IP, el puerto y el firewall")
    if isinstance(error, ConnectionRefusedError):
        return ErrorDeCopia(f"{donde} rechazó la conexión: ¿es el puerto correcto?")
    if isinstance(error, socket.gaierror):
        return ErrorDeCopia(f"no se encontró el servidor {destino.host!r}")
    if isinstance(error, ftplib.error_perm):
        return ErrorDeCopia(f"el servidor no dejó escribir en la carpeta: {error}")
    if isinstance(error, PermissionError):
        return ErrorDeCopia(f"el servidor no dejó escribir en la carpeta: {error}")
    return ErrorDeCopia(f"no se pudo copiar a {donde}: {error or type(error).__name__}")


@contextmanager
def _conectar(destino: Destino, password: str, known_hosts: Path) -> Iterator[_Conexion]:
    if not destino.host:
        raise ErrorDeCopia("falta la IP o el nombre del servidor")
    try:
        conexion: _SFTP | _FTP = (
            _SFTP(destino, password, known_hosts)
            if destino.protocolo == "sftp"
            else _FTP(destino, password)
        )
    except _FALLOS as error:
        raise _explicar(error, destino) from None
    try:
        yield conexion
    except _FALLOS as error:
        raise _explicar(error, destino) from None
    finally:
        conexion.cerrar()


def probar(destino: Destino, password: str, known_hosts: Path) -> str:
    """Entra al servidor y crea la carpeta. Devuelve la huella del servidor (SFTP) o ''."""
    with _conectar(destino, password, known_hosts) as conexion:
        conexion.preparar(carpeta_valida(destino.carpeta) or "/")
        return conexion.huella


def ultimos_respaldos(db: Session) -> list[tuple[Respaldo, Equipo]]:
    ultimos = select(func.max(Respaldo.id)).group_by(Respaldo.equipo_id)
    consulta = (
        select(Respaldo, Equipo)
        .join(Equipo, Equipo.id == Respaldo.equipo_id)
        .where(Respaldo.id.in_(ultimos))
        .order_by(Equipo.nombre)
    )
    return [(r, e) for r, e in db.execute(consulta).tuples()]


def enviar(
    db: Session,
    cifrador: Cifrador,
    known_hosts: Path,
    usuario: Usuario | None,
    cuando: datetime,
) -> ResultadoEnvio:
    """Sube la última versión de cada equipo. Deja el resultado en el registro de eventos."""
    destino = leer_destino(db)
    password = cifrador.descifrar(destino.password_cifrada) if destino.password_cifrada else ""
    objeto = f"{destino.protocolo}://{destino.host}"
    resultado = ResultadoEnvio(archivos=0)
    try:
        with _conectar(destino, password, known_hosts) as conexion:
            resultado.huella = conexion.huella
            for respaldo, equipo in ultimos_respaldos(db):
                carpeta, archivo = ruta_de(destino, equipo, cuando)
                conexion.subir(carpeta, archivo, contenido(respaldo, cifrador).encode("utf-8"))
                resultado.archivos += 1
                resultado.rutas.append(f"{carpeta.rstrip('/')}/{archivo}")
    except ErrorDeCopia as error:
        registrar(db, usuario, "respaldo.copia_error", objeto, {"error": str(error)})
        _guardar(
            db,
            _ULTIMO_ENVIO,
            asdict(UltimoEnvio(cuando.isoformat(), False, resultado.archivos, str(error))),
        )
        raise
    registrar(db, usuario, "respaldo.copia", objeto, {"archivos": resultado.archivos})
    _guardar(db, _ULTIMO_ENVIO, asdict(UltimoEnvio(cuando.isoformat(), True, resultado.archivos)))
    return resultado
