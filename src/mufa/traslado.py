"""Llevar mufa a otra computadora: todos los datos en un archivo cifrado.

La app de escritorio guarda todo en la computadora donde se instaló: la
cuenta creada en una no existe en otra. Para pasarse, se exporta un archivo
en la vieja y se importa en la nueva, en vez de crear otra cuenta.

El archivo lleva la base (SQLite) y la clave que cifra las credenciales de
los equipos, así que se protege con una frase que elige quien lo exporta
(scrypt + Fernet). Sin la frase no sirve para nada. Solo se importa en una
instalación sin usuarios: nunca pisa datos que ya existen.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import secrets
import sqlite3
import zlib
from pathlib import Path

from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Engine

from mufa import __version__
from mufa.migraciones import actualizar_base, configuracion

ENCABEZADO = "mufa-traslado 1"
EXTENSION = ".mufa"
# Frase de al menos 12 caracteres, como las contraseñas de mufa.
MINIMO_FRASE = 12
# Lo que puede ocupar la base ya descomprimida (un archivo de 1 MB no puede volverse 10 GB).
MAXIMO_BASE = 1024 * 1024 * 1024
# Además de la base: la clave de cifrado, las claves SSH ya verificadas y la licencia.
CLAVE = "secreto.key"
_ARCHIVOS = (CLAVE, "known_hosts", "licencia.txt")
_SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}


class ErrorDeTraslado(ValueError):
    """El archivo no se puede importar: el mensaje se muestra tal cual."""


def ruta_sqlite(motor: Engine) -> Path | None:
    """La ruta del archivo de la base, o None si no es SQLite (un servidor con PostgreSQL)."""
    if motor.url.get_backend_name() != "sqlite" or not motor.url.database:
        return None
    return Path(motor.url.database)


def _fernet(frase: str, sal: bytes) -> Fernet:
    clave = hashlib.scrypt(frase.encode("utf-8"), salt=sal, **_SCRYPT)
    return Fernet(base64.urlsafe_b64encode(clave))


def exportar(base: Path, dir_datos: Path, frase: str) -> str:
    """El contenido del archivo de traslado (texto)."""
    if len(frase) < MINIMO_FRASE:
        raise ErrorDeTraslado(f"la frase tiene que tener al menos {MINIMO_FRASE} caracteres")
    # Copia consistente aunque el servidor siga escribiendo; las sesiones
    # abiertas no viajan (en la otra computadora se entra de nuevo).
    with sqlite3.connect(base) as origen, sqlite3.connect(":memory:") as copia:
        origen.backup(copia)
        copia.execute("DELETE FROM sesiones")
        copia.commit()
        contenido = copia.serialize()
    datos = {
        "version": __version__,
        "base": base64.b64encode(contenido).decode("ascii"),
        "archivos": {
            nombre: (dir_datos / nombre).read_text(encoding="utf-8")
            for nombre in _ARCHIVOS
            if (dir_datos / nombre).is_file()
        },
    }
    sal = secrets.token_bytes(16)
    cifrado = _fernet(frase, sal).encrypt(zlib.compress(json.dumps(datos).encode("utf-8"), 6))
    return "\n".join(
        [ENCABEZADO, base64.b64encode(sal).decode("ascii"), cifrado.decode("ascii"), ""]
    )


def _leer(texto: str, frase: str) -> tuple[bytes, dict[str, str]]:
    lineas = texto.strip().splitlines()
    if len(lineas) != 3 or lineas[0].strip() != ENCABEZADO:
        raise ErrorDeTraslado("no es un archivo de traslado de mufa")
    try:
        sal = base64.b64decode(lineas[1], validate=True)
        comprimido = _fernet(frase, sal).decrypt(lineas[2].strip().encode("ascii"))
    except (InvalidToken, binascii.Error, ValueError):
        raise ErrorDeTraslado("la frase no es correcta o el archivo está dañado") from None
    descompresor = zlib.decompressobj()
    plano = descompresor.decompress(comprimido, MAXIMO_BASE)
    if descompresor.unconsumed_tail:
        raise ErrorDeTraslado("el archivo es demasiado grande")
    try:
        datos = json.loads(plano)
        base = base64.b64decode(datos["base"], validate=True)
        archivos = {n: str(datos["archivos"][n]) for n in _ARCHIVOS if n in datos["archivos"]}
        Fernet(archivos[CLAVE].strip().encode("ascii"))
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise ErrorDeTraslado("el archivo está dañado") from None
    return base, archivos


def _revisar_base(copia: sqlite3.Connection, url: str) -> None:
    tablas = {f for (f,) in copia.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"usuarios", "alembic_version"} <= tablas:
        raise ErrorDeTraslado("el archivo no tiene una base de mufa")
    if not copia.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
        raise ErrorDeTraslado("el archivo no tiene ninguna cuenta")
    fila = copia.execute("SELECT version_num FROM alembic_version").fetchone()
    scripts = ScriptDirectory.from_config(configuracion(url))
    if fila is None or fila[0] not in {r.revision for r in scripts.walk_revisions()}:
        raise ErrorDeTraslado(
            "el archivo viene de una versión más nueva de mufa: actualiza mufa en esta "
            "computadora y vuelve a intentarlo"
        )


def importar(texto: str, frase: str, motor: Engine, dir_datos: Path) -> bytes:
    """Reemplaza la base y la clave por las del archivo. Devuelve la clave nueva.

    Quien llama tiene que comprobar antes que no hay usuarios.
    """
    ruta = ruta_sqlite(motor)
    if ruta is None:
        raise ErrorDeTraslado("solo se puede importar en la app de escritorio o con SQLite")
    base, archivos = _leer(texto, frase)
    url = motor.url.render_as_string(hide_password=False)
    with sqlite3.connect(":memory:") as copia:
        try:
            copia.deserialize(base)
            _revisar_base(copia, url)
        except sqlite3.DatabaseError:
            raise ErrorDeTraslado("el archivo está dañado") from None
        # Las conexiones abiertas verían la base vieja: se cierran antes de copiar.
        motor.dispose()
        with sqlite3.connect(ruta) as destino:
            copia.backup(destino)
    for nombre, contenido in archivos.items():
        # Cada archivo se escribe completo aparte y después se cambia de nombre.
        temporal = dir_datos / f"{nombre}.nuevo"
        descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as salida:
            salida.write(contenido)
        temporal.replace(dir_datos / nombre)
    # Si el archivo viene de una versión anterior, se pone al día.
    actualizar_base(url)
    return archivos[CLAVE].strip().encode("ascii")
