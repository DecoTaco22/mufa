"""Caja de herramientas de red: ping, traceroute, DNS y puertos desde el servidor de mufa.

Corren desde el servidor, que suele estar dentro de la red de gestión: es
lo que un técnico haría con una terminal, sin tener que entrar al servidor.
El destino se valida antes de pasarlo a un programa (sin shell), así que no
se puede inyectar ninguna opción ni comando.
"""

from __future__ import annotations

import ipaddress
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Self

_NOMBRE_DE_HOST = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*\.?$"
)
# Varias herramientas a la vez pueden saturar el servidor: se limita.
_EN_CURSO = threading.BoundedSemaphore(4)
# En Windows, sin esto cada ping abre una ventana de consola encima de la app.
SIN_VENTANA: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # solo existe en Windows
# ping y tracert de Windows escriben en la página de códigos de la consola (OEM).
CODIFICACION = "oem" if sys.platform == "win32" else "utf-8"
# Un ping continuo no puede quedar corriendo para siempre si se olvida abierto.
MAXIMO_EN_VIVO = 600.0


class DestinoInvalido(ValueError):
    pass


class Ocupado(RuntimeError):
    pass


@dataclass(frozen=True)
class Salida:
    ok: bool
    texto: str
    segundos: float


def validar_destino(destino: str) -> str:
    destino = destino.strip()
    try:
        return str(ipaddress.ip_address(destino))
    except ValueError:
        pass
    if not _NOMBRE_DE_HOST.match(destino):
        raise DestinoInvalido("el destino tiene que ser una IP o un nombre de host")
    return destino


def _correr(comando: list[str], tiempo_maximo: float) -> Salida:
    if not _EN_CURSO.acquire(blocking=False):
        raise Ocupado("hay varias herramientas corriendo; prueba en unos segundos")
    inicio = time.monotonic()
    try:
        resultado = subprocess.run(  # destino validado, sin shell
            comando,
            capture_output=True,
            text=True,
            encoding=CODIFICACION,
            errors="replace",
            timeout=tiempo_maximo,
            check=False,
            creationflags=SIN_VENTANA,
        )
        texto = (resultado.stdout + resultado.stderr).strip()
        return Salida(resultado.returncode == 0, texto, time.monotonic() - inicio)
    except subprocess.TimeoutExpired as error:
        parcial = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        return Salida(
            False, f"{parcial}\n(se cortó a los {tiempo_maximo:.0f} s)".strip(), tiempo_maximo
        )
    except OSError as error:
        return Salida(False, f"no se pudo ejecutar {comando[0]}: {error}", 0.0)
    finally:
        _EN_CURSO.release()


def _programa(*nombres: str) -> str | None:
    return next((ruta for nombre in nombres if (ruta := shutil.which(nombre))), None)


def comando_ping(destino: str, cantidad: int | None = 4) -> list[str]:
    """El comando de ping del sistema. cantidad=None: continuo (hasta que se corta)."""
    destino = validar_destino(destino)
    programa = _programa("ping")
    if programa is None:
        raise DestinoInvalido("este servidor no tiene el programa ping")
    if sys.platform == "win32":
        veces = ["-t"] if cantidad is None else ["-n", str(cantidad)]
        return [programa, *veces, "-w", "1000", destino]
    veces = [] if cantidad is None else ["-c", str(cantidad)]
    # -W: en Linux son segundos; en macOS, milisegundos.
    espera = "2000" if sys.platform == "darwin" else "2"
    return [programa, *veces, "-W", espera, destino]


def comando_traceroute(destino: str, saltos: int = 20) -> list[str]:
    destino = validar_destino(destino)
    if sys.platform == "win32":
        if programa := _programa("tracert"):
            return [programa, "-d", "-h", str(saltos), "-w", "1000", destino]
    else:
        if programa := _programa("traceroute"):
            return [programa, "-n", "-m", str(saltos), "-w", "2", destino]
        if programa := _programa("tracepath"):
            return [programa, "-n", "-m", str(saltos), destino]
    raise DestinoInvalido("este servidor no tiene traceroute instalado")


def ping(destino: str, cantidad: int = 4) -> Salida:
    try:
        comando = comando_ping(destino, cantidad)
    except DestinoInvalido as error:
        if "programa" in str(error):
            return Salida(False, str(error), 0.0)
        raise
    return _correr(comando, 30)


def traceroute(destino: str, saltos: int = 20) -> Salida:
    try:
        comando = comando_traceroute(destino, saltos)
    except DestinoInvalido as error:
        if "instalado" in str(error):
            return Salida(False, str(error), 0.0)
        raise
    return _correr(comando, 90)


class EnVivo:
    """Un programa cuya salida se lee línea por línea mientras corre (para la terminal de la app).

    Se usa con `with`: al salir, si sigue corriendo, se corta. Ocupa uno de los
    lugares de `_EN_CURSO` mientras vive.
    """

    def __init__(self, comando: list[str]) -> None:
        if not _EN_CURSO.acquire(blocking=False):
            raise Ocupado("hay varias herramientas corriendo; prueba en unos segundos")
        try:
            self._proceso = subprocess.Popen(  # destino validado, sin shell
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding=CODIFICACION,
                errors="replace",
                bufsize=1,
                creationflags=SIN_VENTANA,
            )
        except OSError:
            _EN_CURSO.release()
            raise

    def lineas(self) -> Iterator[str]:
        assert self._proceso.stdout is not None
        yield from self._proceso.stdout

    @property
    def codigo(self) -> int | None:
        return self._proceso.poll()

    def cortar(self) -> None:
        if self._proceso.poll() is None:
            self._proceso.kill()
        self._proceso.wait(5)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        try:
            self.cortar()
        finally:
            _EN_CURSO.release()


def dns(nombre: str) -> Salida:
    """Resuelve un nombre (A y AAAA) o, si es una IP, su nombre inverso."""
    nombre = validar_destino(nombre)
    inicio = time.monotonic()
    try:
        ipaddress.ip_address(nombre)
        es_ip = True
    except ValueError:
        es_ip = False
    try:
        if es_ip:
            inverso, alias, _ = socket.gethostbyaddr(nombre)
            texto = "\n".join([f"{nombre} → {inverso}", *(f"alias: {a}" for a in alias)])
        else:
            direcciones = sorted(
                {str(info[4][0]) for info in socket.getaddrinfo(nombre, None)},
                key=lambda d: (":" in d, d),
            )
            texto = "\n".join(f"{nombre} → {d}" for d in direcciones)
        return Salida(True, texto, time.monotonic() - inicio)
    except (socket.gaierror, socket.herror) as error:
        return Salida(False, f"no se pudo resolver: {error}", time.monotonic() - inicio)


def puerto(destino: str, numero: int, tiempo_maximo: float = 3.0) -> Salida:
    destino = validar_destino(destino)
    if not 1 <= numero <= 65535:
        raise DestinoInvalido("el puerto va de 1 a 65535")
    inicio = time.monotonic()
    try:
        with socket.create_connection((destino, numero), timeout=tiempo_maximo):
            pass
        segundos = time.monotonic() - inicio
        return Salida(True, f"{destino}:{numero} abierto ({segundos * 1000:.0f} ms)", segundos)
    except ConnectionRefusedError:
        return Salida(
            False, f"{destino}:{numero} cerrado (rechazó la conexión)", time.monotonic() - inicio
        )
    except TimeoutError:
        return Salida(
            False, f"{destino}:{numero} sin respuesta (filtrado o apagado)", tiempo_maximo
        )
    except OSError as error:
        return Salida(False, f"{destino}:{numero}: {error}", time.monotonic() - inicio)


# --- MTR: traceroute + ping a cada salto, varias rondas --------------------------

_TIEMPO_PING = re.compile(r"(?:time|tiempo)\s*([=<])\s*([\d.,]+)\s*ms", re.IGNORECASE)


@dataclass
class Salto:
    numero: int
    ip: str | None  # None: el salto no respondió al traceroute («* * *»)
    enviados: int = 0
    recibidos: int = 0
    ultimo: float | None = None
    mejor: float | None = None
    peor: float | None = None
    suma: float = 0.0

    @property
    def perdida(self) -> float:
        return 100.0 * (1 - self.recibidos / self.enviados) if self.enviados else 100.0

    @property
    def promedio(self) -> float | None:
        return self.suma / self.recibidos if self.recibidos else None

    def anotar(self, rtt: float | None) -> None:
        self.enviados += 1
        if rtt is None:
            return
        self.recibidos += 1
        self.ultimo = rtt
        self.suma += rtt
        self.mejor = rtt if self.mejor is None else min(self.mejor, rtt)
        self.peor = rtt if self.peor is None else max(self.peor, rtt)


def saltos_de_traceroute(texto: str) -> list[Salto]:
    """Los saltos de la salida de traceroute (Linux, macOS) o tracert (Windows)."""
    saltos: list[Salto] = []
    for linea in texto.splitlines():
        partes = linea.split()
        if not partes or not partes[0].isdigit():
            continue
        ip = None
        for parte in partes[1:]:
            try:
                ip = str(ipaddress.ip_address(parte.strip("()[]")))
                break
            except ValueError:
                continue
        saltos.append(Salto(int(partes[0]), ip))
    return saltos


def rtt_de_ping(texto: str) -> float | None:
    """Milisegundos de la respuesta de un ping («time=12.3 ms», «tiempo<1m», …)."""
    if encontrado := _TIEMPO_PING.search(texto):
        valor = float(encontrado.group(2).replace(",", "."))
        return valor / 2 if encontrado.group(1) == "<" else valor
    return None


def _un_ping(ip: str) -> float | None:
    try:
        resultado = subprocess.run(  # IP validada, sin shell
            comando_ping(ip, 1),
            capture_output=True,
            text=True,
            encoding=CODIFICACION,
            errors="replace",
            timeout=5,
            check=False,
            creationflags=SIN_VENTANA,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return rtt_de_ping(resultado.stdout) if resultado.returncode == 0 else None


def informe_mtr(destino: str, saltos: list[Salto]) -> str:
    def ms(valor: float | None) -> str:
        return "—" if valor is None else f"{valor:.1f}"

    lineas = [
        f"MTR a {destino}: {saltos[0].enviados if saltos else 0} rondas",
        f"{'#':>3}  {'Salto':<40} {'Pérd%':>6} {'Env':>4} {'Últ':>7} {'Prom':>7} {'Mejor':>7} {'Peor':>7}",
    ]
    for s in saltos:
        lineas.append(
            f"{s.numero:>3}  {(s.ip or '???'):<40} {s.perdida:>6.1f} {s.enviados:>4} "
            f"{ms(s.ultimo):>7} {ms(s.promedio):>7} {ms(s.mejor):>7} {ms(s.peor):>7}"
        )
    return "\n".join(lineas)


def mtr(destino: str, rondas: int = 10, saltos_max: int = 20) -> Salida:
    """Como mtr --report: dónde se pierden paquetes o sube la latencia en el camino."""
    traza = traceroute(destino, saltos_max)
    saltos = saltos_de_traceroute(traza.texto)
    if not saltos:
        return Salida(False, traza.texto or "traceroute no devolvió saltos", traza.segundos)
    if not _EN_CURSO.acquire(blocking=False):
        raise Ocupado("hay varias herramientas corriendo; prueba en unos segundos")
    inicio = time.monotonic()
    try:
        con_ip = [s for s in saltos if s.ip]
        with ThreadPoolExecutor(max_workers=8) as grupo:
            for _ in range(rondas):
                for salto, rtt in zip(
                    con_ip, grupo.map(lambda s: _un_ping(s.ip), con_ip), strict=True
                ):
                    salto.anotar(rtt)
                for salto in saltos:
                    if salto.ip is None:
                        salto.anotar(None)
    finally:
        _EN_CURSO.release()
    ultimo = saltos[-1]
    return Salida(
        ultimo.recibidos > 0,
        informe_mtr(destino, saltos),
        traza.segundos + time.monotonic() - inicio,
    )
