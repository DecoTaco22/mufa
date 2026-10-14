"""Actualizaciones: avisa cuando sale una versión nueva y, en Windows y Mac, la instala.

Cada versión publica un manifiesto firmado con Ed25519 (actualizacion.firmada,
junto a las descargas de GitHub) con el número de versión, las novedades y el
SHA-256 de cada instalador. mufa solo instala un archivo cuyo SHA-256 coincide
con el de un manifiesto firmado por la clave de actualizaciones: alguien que se
haga pasar por GitHub no puede meter otro programa.

- Windows con instalador y Mac: se instala con un clic (lo pide un administrador
  de mufa). Windows pide el permiso de administrador como cualquier instalador;
  al terminar, mufa se vuelve a abrir.
- Servidor (Docker), Windows portátil y el código fuente: solo avisa, con los
  pasos para actualizar.
- Microsoft Store: la actualiza la tienda; mufa no busca.

Para buscar, mufa descarga el manifiesto de GitHub una vez al día. No manda
nada propio (ni la versión ni datos de la red). Se apaga en Ajustes o con
MUFA_BUSCAR_ACTUALIZACIONES=0.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from sqlalchemy.orm import Session

from mufa import __version__
from mufa.db import AjusteSistema

log = logging.getLogger("mufa.actualizacion")

# Clave pública que firma los manifiestos. La privada está solo en los secretos
# del repositorio público (la usa .github/workflows/publicar.yml).
CLAVE_PUBLICA_ACTUALIZACIONES = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAfQ1kbJ6isYDZi7LCLP3tV7ewdxb235wvRNuEM90C2f8=
-----END PUBLIC KEY-----
"""

URL_MANIFIESTO = os.environ.get(
    "MUFA_URL_ACTUALIZACIONES",
    "https://github.com/DecoTaco22/mufa/releases/latest/download/actualizacion.firmada",
)
URL_VERSIONES = "https://github.com/DecoTaco22/mufa/releases/latest"
# Un instalador de mufa pesa unos 60 MB: esto sobra.
TAMANO_MAXIMO_INSTALADOR = 400 * 1024 * 1024


class Modo(str, Enum):
    """Cómo está instalada esta copia de mufa: decide si se puede actualizar sola."""

    INSTALADOR = "instalador"  # Windows, con el instalador
    MACOS = "macos"
    PORTATIL = "portatil"  # Windows, el .zip sin instalar
    TIENDA = "tienda"  # Microsoft Store
    SERVIDOR = "servidor"  # Docker
    CODIGO = "codigo"  # desde el código fuente (uv, pip)


# Qué archivo del manifiesto instala cada modo.
ARCHIVO_DEL_MODO = {Modo.INSTALADOR: "windows", Modo.MACOS: "macos"}

PASOS = {
    Modo.SERVIDOR: (
        "En el servidor, en la carpeta donde instalaste mufa:\n"
        "  curl -fsSLO https://github.com/DecoTaco22/mufa/releases/latest/download/"
        "mufa-servidor.zip\n"
        "  unzip -o mufa-servidor.zip\n"
        "  cd mufa-servidor && sudo sh instalar.sh\n"
        "Tus datos y tu configuración se conservan."
    ),
    Modo.PORTATIL: (
        "Descarga mufa-windows.zip de la versión nueva y descomprímelo encima de esta "
        "carpeta, con mufa cerrada. Tus datos se conservan."
    ),
    Modo.CODIGO: "git pull && uv sync, y vuelve a iniciar mufa.",
    Modo.TIENDA: "La Microsoft Store la instala sola.",
}


def modo_actual() -> Modo:
    elegido = os.environ.get("MUFA_MODO", "")
    if elegido in Modo._value2member_map_:
        return Modo(elegido)
    if not getattr(sys, "frozen", False):
        return Modo.CODIGO
    if sys.platform == "darwin":
        return Modo.MACOS
    ejecutable = Path(sys.executable)
    if "WindowsApps" in ejecutable.parts:
        return Modo.TIENDA
    # El instalador (Inno Setup) deja su desinstalador junto a mufa.exe.
    if (ejecutable.parent / "unins000.exe").exists():
        return Modo.INSTALADOR
    return Modo.PORTATIL


def numero_de_version(texto: str) -> tuple[int, ...]:
    try:
        return tuple(int(parte) for parte in texto.strip().lstrip("v").split("."))
    except ValueError:
        return ()


class ManifiestoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Archivo:
    nombre: str
    url: str
    sha256: str
    tamano: int


@dataclass(frozen=True)
class Novedad:
    version: str
    publicada: date | None
    notas: str
    archivos: dict[str, Archivo]


def _b64decode(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def verificar_manifiesto(texto: str, clave_publica: bytes | None = None) -> Novedad:
    """Mismo formato que las licencias: base64url(json) + "." + base64url(firma)."""
    try:
        datos_b64, firma_b64 = texto.strip().split(".")
        datos, firma = _b64decode(datos_b64), _b64decode(firma_b64)
    except ValueError:
        raise ManifiestoInvalido("formato inválido") from None
    clave = load_pem_public_key(clave_publica or CLAVE_PUBLICA_ACTUALIZACIONES)
    if not isinstance(clave, Ed25519PublicKey):
        raise ManifiestoInvalido("la clave de actualizaciones no es Ed25519")
    try:
        clave.verify(firma, datos)
    except InvalidSignature:
        raise ManifiestoInvalido("la firma del manifiesto no es válida") from None
    try:
        contenido = json.loads(datos)
        version = str(contenido["version"])
        if not numero_de_version(version):
            raise ValueError(version)
        archivos = {
            str(clave_archivo): Archivo(
                nombre=str(a["nombre"]),
                url=str(a["url"]),
                sha256=str(a["sha256"]).lower(),
                tamano=int(a.get("tamano") or 0),
            )
            for clave_archivo, a in (contenido.get("archivos") or {}).items()
        }
        publicada = contenido.get("publicada")
        return Novedad(
            version=version,
            publicada=date.fromisoformat(publicada) if publicada else None,
            notas=str(contenido.get("notas") or "")[:20000],
            archivos=archivos,
        )
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise ManifiestoInvalido(f"manifiesto incompleto: {error}") from None


Obtener = Callable[[str], bytes]
Descargar = Callable[[str, Path, int], None]
Ejecutar = Callable[[Path, "Modo"], None]


def _obtener(url: str) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": "mufa"})
    with urllib.request.urlopen(pedido, timeout=20) as respuesta:
        datos: bytes = respuesta.read(256 * 1024)
        return datos


def _descargar(url: str, destino: Path, maximo: int) -> None:
    pedido = urllib.request.Request(url, headers={"User-Agent": "mufa"})
    leidos = 0
    with urllib.request.urlopen(pedido, timeout=60) as respuesta, destino.open("wb") as salida:
        while bloque := respuesta.read(1024 * 1024):
            leidos += len(bloque)
            if leidos > maximo:
                raise ValueError("el archivo es más grande de lo esperado")
            salida.write(bloque)


def _sha256(archivo: Path) -> str:
    resumen = hashlib.sha256()
    with archivo.open("rb") as entrada:
        while bloque := entrada.read(1024 * 1024):
            resumen.update(bloque)
    return resumen.hexdigest()


def _bundle_de_mac() -> Path:
    """La carpeta mufa.app que está corriendo (sys.executable vive en Contents/MacOS)."""
    bundle = Path(sys.executable).resolve().parents[2]
    if bundle.suffix != ".app":
        raise RuntimeError(f"no se encontró la app de mufa ({bundle})")
    return bundle


def _ejecutar(instalador: Path, modo: Modo) -> None:
    """Arranca el instalador por fuera de mufa. Si vuelve sin error, mufa debe cerrarse."""
    if modo is Modo.INSTALADOR:
        # El instalador pide permiso de administrador: hace falta ShellExecute con
        # "runas" (subprocess no puede elevar). Si la persona dice que no, lanza OSError.
        # /REABRIR=1 hace que el instalador vuelva a abrir mufa al terminar.
        argumentos = "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /REABRIR=1"
        os.startfile(str(instalador), "runas", argumentos)  # type: ignore[attr-defined,call-arg,unused-ignore]
        return
    if modo is Modo.MACOS:
        bundle = _bundle_de_mac()
        if not os.access(bundle.parent, os.W_OK) or not os.access(bundle, os.W_OK):
            raise PermissionError(
                f"no hay permiso para reemplazar {bundle}: abre {instalador} y arrastra mufa a "
                "Aplicaciones"
            )
        montaje = Path(tempfile.mkdtemp(prefix="mufa-actualizacion-"))
        subprocess.run(  # sin shell: rutas propias
            [
                "hdiutil",
                "attach",
                "-nobrowse",
                "-readonly",
                "-mountpoint",
                str(montaje),
                str(instalador),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        nueva = montaje / "mufa.app"
        if not nueva.is_dir():
            subprocess.run(["hdiutil", "detach", str(montaje), "-quiet"], check=False)
            raise RuntimeError("la imagen de disco no trae mufa.app")
        # Cuando mufa se cierra, reemplaza la app, deja la vieja si algo falla y la vuelve a abrir.
        b, v, n, m = (shlex.quote(str(x)) for x in (bundle, f"{bundle}.vieja", nueva, montaje))
        guion = (
            f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.5; done\n"
            f"rm -rf {v}\n"
            f"if mv {b} {v} && ditto {n} {b}; then rm -rf {v}; else rm -rf {b}; mv {v} {b}; fi\n"
            f"hdiutil detach {m} -quiet\n"
            f"open {b}\n"
        )
        subprocess.Popen(  # sin shell del lado de Python: el guion va como argumento
            ["/bin/sh", "-c", guion],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    raise RuntimeError(f"esta instalación ({modo.value}) no se actualiza sola")


class Actualizador:
    """Lo que esta instalación sabe de la última versión publicada."""

    def __init__(
        self,
        dir_datos: Path,
        modo: Modo | None = None,
        obtener: Obtener = _obtener,
        descargar: Descargar = _descargar,
        ejecutar: Ejecutar = _ejecutar,
        clave_publica: bytes | None = None,
        version_actual: str = __version__,
    ) -> None:
        self.modo = modo or modo_actual()
        self.version_actual = version_actual
        self._carpeta = dir_datos / "actualizaciones"
        self._obtener = obtener
        self._descargar = descargar
        self._ejecutar = ejecutar
        self._clave_publica = clave_publica
        self._candado = threading.Lock()
        self.novedad: Novedad | None = None
        self.revisada: datetime | None = None
        self.error = ""
        # "" | "descargando" | "instalando"
        self.estado = ""
        # La app de escritorio pone aquí cómo cerrarse para dejar pasar al instalador.
        self.al_cerrar: Callable[[], None] | None = None

    @property
    def busca(self) -> bool:
        """La Microsoft Store actualiza sola; el resto busca salvo que se apague."""
        return self.modo is not Modo.TIENDA and os.environ.get("MUFA_BUSCAR_ACTUALIZACIONES") != "0"

    @property
    def nueva(self) -> Novedad | None:
        """La novedad, solo si es más nueva que esta versión."""
        novedad = self.novedad
        if novedad and numero_de_version(novedad.version) > numero_de_version(self.version_actual):
            return novedad
        return None

    @property
    def archivo(self) -> Archivo | None:
        """El instalador que corresponde a esta instalación, si se puede instalar sola."""
        novedad = self.nueva
        clave = ARCHIVO_DEL_MODO.get(self.modo)
        return novedad.archivos.get(clave) if novedad and clave else None

    @property
    def pasos(self) -> str:
        return PASOS.get(self.modo, "")

    def buscar(self) -> Novedad | None:
        """Trae el manifiesto. Devuelve la versión nueva, o None si esta es la última."""
        try:
            novedad = verificar_manifiesto(
                self._obtener(URL_MANIFIESTO).decode("ascii", errors="replace"),
                self._clave_publica,
            )
        except (OSError, ManifiestoInvalido) as error:
            self.error = f"no se pudo revisar si hay una versión nueva: {error}"
            log.info("%s", self.error)
            return None
        with self._candado:
            self.novedad, self.revisada, self.error = novedad, datetime.now(UTC), ""
        return self.nueva

    def instalar(self) -> None:
        """Descarga, verifica y arranca el instalador; después cierra mufa. Bloquea."""
        archivo = self.archivo
        if archivo is None:
            raise RuntimeError("no hay una versión nueva para instalar en esta computadora")
        with self._candado:
            if self.estado:
                raise RuntimeError("ya se está instalando")
            self.estado, self.error = "descargando", ""
        try:
            self._carpeta.mkdir(parents=True, exist_ok=True)
            destino = self._carpeta / Path(archivo.nombre).name
            try:
                self._descargar(archivo.url, destino, archivo.tamano or TAMANO_MAXIMO_INSTALADOR)
            except OSError as error:
                raise RuntimeError(f"no se pudo descargar {archivo.nombre} ({error})") from error
            if _sha256(destino) != archivo.sha256:
                destino.unlink(missing_ok=True)
                raise RuntimeError("el archivo descargado no coincide con el publicado")
            self.estado = "instalando"
            self._ejecutar(destino, self.modo)
        except Exception as error:
            self.estado, self.error = "", f"no se pudo actualizar: {error}"
            log.warning("%s", self.error)
            raise
        log.info("instalando mufa %s: se cierra para dejar pasar al instalador", archivo.nombre)
        if self.al_cerrar is not None:
            self.al_cerrar()

    def instalar_en_segundo_plano(self) -> None:
        if self.archivo is None:
            raise RuntimeError("no hay una versión nueva para instalar en esta computadora")
        if self.estado:
            raise RuntimeError("ya se está instalando")

        def tarea() -> None:
            # instalar() ya deja el motivo en self.error (lo muestra la app) y en el registro.
            with contextlib.suppress(Exception):
                self.instalar()

        threading.Thread(target=tarea, name="mufa-actualizacion", daemon=True).start()


_CLAVE_AJUSTE = "actualizaciones.buscar"


def buscar_activado(db: Session) -> bool:
    """Lo que eligió el administrador en Ajustes (por defecto, buscar)."""
    fila = db.get(AjusteSistema, _CLAVE_AJUSTE)
    return fila is None or fila.valor != "0"


def cambiar_buscar(db: Session, activado: bool) -> None:
    fila = db.get(AjusteSistema, _CLAVE_AJUSTE)
    if fila is None:
        db.add(AjusteSistema(clave=_CLAVE_AJUSTE, valor="1" if activado else "0"))
    else:
        fila.valor = "1" if activado else "0"
