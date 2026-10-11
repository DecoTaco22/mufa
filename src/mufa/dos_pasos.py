"""Verificación en dos pasos con códigos TOTP (Google Authenticator, Authy, 1Password...)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

import pyotp

from mufa.permisos import Rol

EMISOR = "mufa"
PERIODO_SEGUNDOS = 30

# Los roles que pueden cambiar la red o administrar la app no pueden usarla
# solo con contraseña.
# Todo rol que puede usar las credenciales de los equipos (terminal, respaldos,
# herramientas) entra con dos pasos: una contraseña robada no alcanza para llegar a la red.
ROLES_OBLIGADOS = frozenset(
    {Rol.TECNICO_N2.value, Rol.INGENIERO_N3.value, Rol.SENIOR.value, Rol.ADMIN.value}
)


CANTIDAD_CODIGOS_RECUPERACION = 10
_ALFABETO = "abcdefghjkmnpqrstuvwxyz23456789"  # sin 0/o ni 1/l/i, que se confunden


def nuevos_codigos_recuperacion() -> list[str]:
    """Diez códigos con forma "xxxxx-xxxxx" (unos 50 bits de azar cada uno)."""
    return [
        "-".join("".join(secrets.choice(_ALFABETO) for _ in range(5)) for _ in range(2))
        for _ in range(CANTIDAD_CODIGOS_RECUPERACION)
    ]


def hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().lower().encode("utf-8")).hexdigest()


def nuevo_secreto() -> str:
    return pyotp.random_base32()


def uri_de_configuracion(secreto: str, cuenta: str) -> str:
    """El otpauth:// que se muestra como código QR en la app del teléfono."""
    return pyotp.TOTP(secreto, interval=PERIODO_SEGUNDOS).provisioning_uri(
        name=cuenta, issuer_name=EMISOR
    )


def verificar(secreto: str, codigo: str, ultimo_paso: int, ahora_segundos: float) -> int | None:
    """Devuelve el paso de tiempo del código si es válido y no se usó antes, o None.

    Acepta el paso anterior y el siguiente para tolerar relojes desfasados
    unos segundos. Un código ya usado (paso <= ultimo_paso) se rechaza: así
    no sirve repetir un código interceptado.
    """
    totp = pyotp.TOTP(secreto, interval=PERIODO_SEGUNDOS)
    actual = int(ahora_segundos // PERIODO_SEGUNDOS)
    for paso in (actual - 1, actual, actual + 1):
        if paso <= ultimo_paso:
            continue
        if hmac.compare_digest(totp.at(paso * PERIODO_SEGUNDOS), codigo):
            return paso
    return None
