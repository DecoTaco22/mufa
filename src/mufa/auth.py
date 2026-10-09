"""Contraseñas, sesiones y protección contra fuerza bruta."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mufa.db import Sesion, Usuario, ahora, como_utc

_hasher = PasswordHasher()

# Hash de una contraseña cualquiera: cuando el email no existe se verifica
# contra este, para que la respuesta tarde lo mismo y no delate qué emails
# están registrados.
_HASH_SEÑUELO = _hasher.hash(secrets.token_urlsafe(16))

LARGO_MINIMO_PASSWORD = 12


class PasswordDebil(ValueError):
    pass


def validar_password(password: str) -> None:
    if len(password) < LARGO_MINIMO_PASSWORD:
        raise PasswordDebil(f"la contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres")


def hashear_password(password: str) -> str:
    validar_password(password)
    return _hasher.hash(password)


def verificar_password(hash_guardado: str | None, password: str) -> bool:
    try:
        return (
            _hasher.verify(hash_guardado or _HASH_SEÑUELO, password) and hash_guardado is not None
        )
    except (VerificationError, InvalidHashError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def crear_sesion(db: Session, usuario: Usuario, duracion: timedelta) -> tuple[str, Sesion]:
    token = secrets.token_urlsafe(32)
    sesion = Sesion(hash_token=_hash_token(token), usuario_id=usuario.id, expira=ahora() + duracion)
    db.add(sesion)
    db.flush()
    return token, sesion


def usuario_de_token(db: Session, token: str) -> Usuario | None:
    sesion = db.scalar(select(Sesion).where(Sesion.hash_token == _hash_token(token)))
    if sesion is None or como_utc(sesion.expira) <= ahora():
        return None
    if not sesion.usuario.activo:
        return None
    return sesion.usuario


def cerrar_sesion(db: Session, token: str) -> None:
    db.execute(delete(Sesion).where(Sesion.hash_token == _hash_token(token)))


def cerrar_todas_las_sesiones(db: Session, usuario_id: int) -> None:
    db.execute(delete(Sesion).where(Sesion.usuario_id == usuario_id))


class LimitadorDeIntentos:
    """Bloquea un email o una IP tras varios inicios de sesión fallidos seguidos.

    En memoria: alcanza para un servidor autoalojado con un proceso. Si se
    corre con varios procesos, cada uno lleva su cuenta (el límite efectivo
    se multiplica, pero sigue frenando la fuerza bruta).
    """

    def __init__(self, maximo: int = 5, ventana_segundos: float = 900) -> None:
        self._maximo = maximo
        self._ventana = ventana_segundos
        self._fallos: dict[str, list[float]] = {}
        self._candado = threading.Lock()

    def _recientes(self, clave: str, ahora_s: float) -> list[float]:
        fallos = [t for t in self._fallos.get(clave, []) if ahora_s - t < self._ventana]
        self._fallos[clave] = fallos
        return fallos

    def bloqueado(self, *claves: str) -> bool:
        ahora_s = time.monotonic()
        with self._candado:
            return any(len(self._recientes(c, ahora_s)) >= self._maximo for c in claves)

    def registrar_fallo(self, *claves: str) -> None:
        ahora_s = time.monotonic()
        with self._candado:
            for clave in claves:
                self._recientes(clave, ahora_s).append(ahora_s)

    def limpiar(self, *claves: str) -> None:
        with self._candado:
            for clave in claves:
                self._fallos.pop(clave, None)
