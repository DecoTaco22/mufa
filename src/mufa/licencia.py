"""Licencias de los planes de pago.

Una licencia es un JSON firmado con Ed25519 por el emisor (quien vende
mufa). El servidor solo tiene la clave pública: puede verificar una
licencia sin conexión a internet, pero no puede fabricar una. Sin
licencia, mufa funciona en el plan gratuito.

Formato: base64url(json) + "." + base64url(firma).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

# Clave pública del emisor de licencias. La privada correspondiente nunca
# está en este repositorio.
CLAVE_PUBLICA_EMISOR = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA3TiH3XZ0zQap9t91WuHNgrIrrol2ohCE1WSXdeB+DW4=
-----END PUBLIC KEY-----
"""

MAX_EQUIPOS_GRATIS = 10
MAX_USUARIOS_GRATIS = 3
MAX_INTERFACES_VIGILADAS_GRATIS = 5
DIAS_HISTORIAL_GRATIS = 7


class LimiteDelPlan(Exception):
    """Algo que el plan gratis no permite. El mensaje invita a Pro."""


def hoy() -> date:
    return datetime.now(UTC).date()


class LicenciaInvalida(ValueError):
    pass


class Funcion(str, Enum):
    """Módulos de mufa. Los de pago viven fuera del repositorio público."""

    MONITOREO = "monitoreo"
    AUDITORIA = "auditoria"
    INVENTARIO = "inventario"
    RESPALDOS = "respaldos"
    IPAM = "ipam"
    VLANS = "vlans"
    FIBRA = "fibra"
    AAA = "aaa"
    AUTOMATIZACION = "automatizacion"
    MESA_DE_AYUDA = "mesa_de_ayuda"
    MULTICLIENTE = "multicliente"
    RESTAURACION = "restauracion"


FUNCIONES_GRATIS = frozenset(
    {
        Funcion.MONITOREO,
        Funcion.AUDITORIA,
        Funcion.INVENTARIO,
        Funcion.RESPALDOS,
        Funcion.IPAM,
        Funcion.VLANS,
        Funcion.FIBRA,
    }
)


@dataclass(frozen=True)
class Plan:
    nombre: str
    cliente: str
    max_equipos: int | None  # None = ilimitados (Pro y superiores)
    vence: date | None

    def admite_otro_equipo(self, registrados: int) -> bool:
        return self.max_equipos is None or registrados < self.max_equipos

    @property
    def es_gratis(self) -> bool:
        return self.nombre == "gratis"

    @property
    def max_usuarios(self) -> int | None:
        return MAX_USUARIOS_GRATIS if self.es_gratis else None

    @property
    def max_interfaces_vigiladas(self) -> int | None:
        return MAX_INTERFACES_VIGILADAS_GRATIS if self.es_gratis else None

    def dias_historial(self, configurados: int) -> int:
        return min(configurados, DIAS_HISTORIAL_GRATIS) if self.es_gratis else configurados

    def exigir_lugar(self, que: str, usados: int, maximo: int | None) -> None:
        """Lanza LimiteDelPlan si ya se usó todo lo que el plan permite."""
        if maximo is not None and usados >= maximo:
            raise LimiteDelPlan(
                f"El plan {self.nombre} incluye hasta {maximo} {que}. Con mufa Pro son ilimitados."
            )

    def permite(self, funcion: Funcion) -> bool:
        return not self.es_gratis or funcion in FUNCIONES_GRATIS

    @property
    def funciones(self) -> list[Funcion]:
        return [f for f in Funcion if self.permite(f)]


PLAN_GRATIS = Plan(nombre="gratis", cliente="", max_equipos=MAX_EQUIPOS_GRATIS, vence=None)


def _b64decode(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def verificar(texto: str, hoy: date, clave_publica: bytes | None = None) -> Plan:
    try:
        datos_b64, firma_b64 = texto.strip().split(".")
        datos, firma = _b64decode(datos_b64), _b64decode(firma_b64)
    except ValueError:
        raise LicenciaInvalida("formato de licencia inválido") from None

    clave = load_pem_public_key(clave_publica or CLAVE_PUBLICA_EMISOR)
    if not isinstance(clave, Ed25519PublicKey):
        raise LicenciaInvalida("la clave pública del emisor no es Ed25519")
    try:
        clave.verify(firma, datos)
    except InvalidSignature:
        raise LicenciaInvalida("la firma de la licencia no es válida") from None

    contenido = json.loads(datos)
    vence = date.fromisoformat(contenido["vence"]) if contenido.get("vence") else None
    if vence is not None and vence < hoy:
        raise LicenciaInvalida(f"la licencia venció el {vence.isoformat()}")
    return Plan(
        nombre=str(contenido["plan"]),
        cliente=str(contenido["cliente"]),
        max_equipos=(
            int(contenido["max_equipos"]) if contenido.get("max_equipos") is not None else None
        ),
        vence=vence,
    )


def plan_vigente(archivo: Path, hoy: date) -> tuple[Plan, str]:
    """El plan de la licencia instalada, o el gratuito con el motivo si no hay una válida."""
    if not archivo.exists():
        return PLAN_GRATIS, ""
    try:
        return verificar(archivo.read_text(encoding="utf-8"), hoy), ""
    except LicenciaInvalida as error:
        return PLAN_GRATIS, str(error)
