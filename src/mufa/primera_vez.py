"""Primera vez: crear la cuenta de administrador desde la app web.

Mientras no exista ningún usuario, cualquiera que llegue al servidor podría
reclamarlo. Para evitarlo, el servidor genera un token al arrancar y lo
muestra solo a quien tiene acceso a la máquina: en la consola (o en los
logs de Docker) y en un archivo del directorio de datos. Sin ese token no
se puede crear el administrador. Cuando ya hay usuarios, el token se borra.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mufa.db import Usuario

NOMBRE_ARCHIVO = "token-primera-vez.txt"


def archivo_token(dir_datos: Path) -> Path:
    return dir_datos / NOMBRE_ARCHIVO


def hay_usuarios(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(Usuario)) or 0) > 0


def preparar(sesiones: sessionmaker[Session], dir_datos: Path) -> str | None:
    """El token para crear el primer administrador, o None si ya hay usuarios."""
    archivo = archivo_token(dir_datos)
    with sesiones() as db:
        if hay_usuarios(db):
            archivo.unlink(missing_ok=True)
            return None
    if archivo.exists():
        token = archivo.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    archivo.write_text(token + "\n", encoding="utf-8")
    if os.name == "posix":
        archivo.chmod(0o600)
    return token


def token_valido(esperado: str | None, recibido: str) -> bool:
    return esperado is not None and secrets.compare_digest(esperado, recibido.strip())


def descartar(dir_datos: Path) -> None:
    archivo_token(dir_datos).unlink(missing_ok=True)
