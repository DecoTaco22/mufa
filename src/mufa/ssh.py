"""Sesión SSH de solo lectura, común a todas las marcas."""

from __future__ import annotations

import re
import time
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

import paramiko

from mufa.security import assert_allowed

# Claves de host conocidas, propias de mufa. La primera conexión a un router
# guarda su clave (trust on first use); si en una conexión posterior la clave
# cambia, paramiko aborta con BadHostKeyException antes de mandar la
# contraseña: así no se le entregan credenciales a un equipo que se hace
# pasar por el router.
KNOWN_HOSTS = Path.home() / ".mufa" / "known_hosts"

# Algoritmos con SHA-1. Apagados por defecto (CVE-2026-44405): solo se habilitan si
# el equipo no sabe negociar nada moderno, como muchos IOS, VRP y JunOS viejos.
SHA1: dict[str, list[str]] = {
    "kex": [
        "diffie-hellman-group1-sha1",
        "diffie-hellman-group14-sha1",
        "diffie-hellman-group-exchange-sha1",
    ],
    "keys": ["ssh-rsa"],
    "pubkeys": ["ssh-rsa"],
}


def es_incompatible(error: BaseException) -> bool:
    """El equipo y mufa no tienen ningún algoritmo en común."""
    return "incompatible" in str(error).lower()


# Pausas de paginación de cada marca: «---- More ----» (Huawei, HPE Comware),
# «--More--» (Cisco, ZTE), «<--- More --->», «Press any key to continue» (ProCurve),
# con el borrado que mandan después (retrocesos o ESC[nD) para quitarse de la línea.
_PAUSA = re.compile(
    r"[ \t]*(?:-{2,} ?more ?-{2,}|--more--|<-+ more -+>|\(more\)|press any key to continue[^\r\n]*?)"
    r"[ \t]*(?:(?:\x1b\[\d*D|\x08+)[ \t]*(?:\x1b\[\d*D|\x08+))?",
    re.IGNORECASE,
)
_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PROMPT = re.compile(r"[>#\]$%:]\s*$")
_CALMA = 1.5  # segundos sin datos para dar por terminada una respuesta
# Marcas que siempre contestan comandos sueltos: una salida vacía es una sección vacía.
_SIEMPRE_POR_COMANDO = frozenset({"mikrotik", "cisco", "juniper"})
_SIN_RESPUESTA = 20.0


def limpiar_consola(texto: str) -> str:
    """Quita de una salida de consola las pausas de paginación y los códigos de terminal."""
    texto = _PAUSA.sub("", texto.replace("\r\n", "\n"))
    return _ESCAPES.sub("", texto).replace("\r", "")


class ClaveDeHostCambiada(paramiko.BadHostKeyException):
    """El equipo presentó una clave distinta, o de otro tipo, que la guardada."""


class PoliticaTOFU(paramiko.MissingHostKeyPolicy):
    """La primera vez guarda la clave del equipo. Si ya hay una guardada de otro tipo,
    no la acepta: un intermediario podría ofrecer un tipo distinto (por ejemplo ssh-rsa
    en lugar de ed25519) justamente para que no se compare con la conocida."""

    def __init__(self, archivo: Path) -> None:
        self._archivo = archivo

    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey
    ) -> None:
        conocidas = client.get_host_keys().lookup(hostname)
        if conocidas:
            otra = next(iter(conocidas.values()))
            raise ClaveDeHostCambiada(hostname, key, otra)
        client.get_host_keys().add(hostname, key.get_name(), key)
        client.save_host_keys(str(self._archivo))


class SesionDeLectura(Protocol):
    """Lo que necesita un adaptador: SSH o, en MikroTik, la API de RouterOS."""

    def run_readonly(self, command: str) -> str: ...


class SesionSoloLectura:
    """Conexión SSH a un equipo que solo puede ejecutar comandos de la lista blanca de su marca."""

    def __init__(
        self,
        host: str,
        user: str,
        marca: str,
        password: str | None = None,
        port: int = 22,
        timeout: float = 10.0,
        known_hosts: Path = KNOWN_HOSTS,
    ) -> None:
        self._host = host
        self._marca = marca
        self._user = user
        self._password = password
        self._port = port
        self._timeout = timeout
        self._known_hosts = known_hosts
        self._client = paramiko.SSHClient()

    def __enter__(self) -> Self:
        self._known_hosts.parent.mkdir(parents=True, exist_ok=True)
        self._known_hosts.touch(exist_ok=True)
        try:
            self._conectar(sin_sha1=True)
        except paramiko.SSHException as error:
            if not es_incompatible(error):
                raise
            # Equipo viejo: solo habla SHA-1. La clave del equipo se sigue verificando.
            self._client.close()
            self._client = paramiko.SSHClient()
            self._conectar(sin_sha1=False)
        return self

    def _conectar(self, sin_sha1: bool) -> None:
        self._client.load_host_keys(str(self._known_hosts))
        self._client.set_missing_host_key_policy(PoliticaTOFU(self._known_hosts))
        self._client.connect(
            self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            timeout=self._timeout,
            look_for_keys=False,
            allow_agent=False,
            disabled_algorithms=SHA1 if sin_sha1 else None,
        )

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        self._client.close()

    def run_readonly(self, command: str) -> str:
        """Ejecuta un comando de la lista blanca y devuelve la salida."""
        assert_allowed(command, self._marca)
        try:
            _, stdout, stderr = self._client.exec_command(command, timeout=self._timeout)
            salida: str = stdout.read().decode("utf-8", errors="replace")
            error: str = stderr.read().decode("utf-8", errors="replace")
        except paramiko.SSHException:
            # OLTs ZTE, HPE ProCurve y algunos VRP no aceptan comandos sueltos: por consola.
            return self._por_consola(command)
        if error.strip():
            raise RuntimeError(error.strip())
        if not salida.strip() and self._marca not in _SIEMPRE_POR_COMANDO:
            # Puede ser una sección vacía de verdad, o un equipo que ignora los comandos
            # sueltos sin cerrar el canal. Si no hay consola, la respuesta era vacía.
            try:
                return self._por_consola(command)
            except paramiko.SSHException:
                return salida
        return salida

    def _por_consola(self, command: str) -> str:
        """Escribe el comando (ya verificado) en una consola y lee la respuesta completa.

        Lo único que se manda además del comando es un espacio en cada pausa de
        paginación, que solo pide la página siguiente.
        """
        assert_allowed(command, self._marca)
        canal = self._client.invoke_shell(width=511, height=1000)
        canal.settimeout(0.3)
        limite = time.monotonic() + max(self._timeout, 30) * 4
        try:
            bienvenida = limpiar_consola(self._leer(canal, limite, prompt=None))
            prompt = next((x.strip() for x in reversed(bienvenida.split("\n")) if x.strip()), "")
            canal.send((command + "\n").encode())
            lineas = limpiar_consola(self._leer(canal, limite, prompt)).split("\n")
        finally:
            canal.close()
        # Fuera el eco del comando (y lo anterior) y el prompt del final.
        for i, linea in enumerate(lineas[:5]):
            if command in linea:
                lineas = lineas[i + 1 :]
                break
        while lineas and (not lineas[-1].strip() or lineas[-1].strip() == prompt):
            lineas.pop()
        return "\n".join(lineas)

    @staticmethod
    def _leer(canal: paramiko.Channel, limite: float, prompt: str | None) -> str:
        """Lee hasta que el equipo se calla; con `prompt`, hasta que lo vuelve a mostrar."""
        datos = ""
        atendido = 0  # hasta dónde ya se respondió una pausa
        ultimo = time.monotonic()
        while time.monotonic() < limite:
            try:
                trozo: bytes | None = canal.recv(65536)
            except TimeoutError:
                trozo = None
            ahora = time.monotonic()
            if trozo:
                datos += trozo.decode("utf-8", errors="replace")
                ultimo = ahora
                if _PAUSA.search(datos, max(atendido, len(datos) - 160)):
                    canal.send(b" ")
                    atendido = len(datos)
                continue
            if trozo == b"":
                break  # el equipo cerró la consola
            quieto = ahora - ultimo
            cola = limpiar_consola(datos[-200:]).rstrip("\n").rsplit("\n", 1)[-1].strip()
            listo = prompt is None or (cola == prompt if prompt else bool(_PROMPT.search(cola)))
            if datos and quieto >= _CALMA and listo:
                break
            if quieto >= (_SIN_RESPUESTA if datos or prompt is not None else _CALMA * 3):
                break
        return datos
