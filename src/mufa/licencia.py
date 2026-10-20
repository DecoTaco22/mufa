"""Licencias de los planes de pago.

Una licencia es un JSON firmado con Ed25519 por el emisor (quien vende
mufa). El servidor solo tiene la clave pública: puede verificar una
licencia sin conexión a internet, pero no puede fabricar una. Sin
licencia, mufa funciona en el plan gratuito.

Formato: base64url(json) + "." + base64url(firma).

Las licencias mensuales (suscripción) vencen a los 35 días. Mientras la
suscripción siga pagada, mufa trae sola la licencia nueva del sitio unos
días antes de que venza: solo manda el identificador de la licencia.

Las licencias Pro traen las llaves de los módulos cifrados (mufa.modulos_pro):
"pro" es la primera llave y "llaves" las que se sumaron después, una por
cada vez que se rotó. Si una versión nueva trae módulos cifrados con una
llave que la licencia instalada no tiene, mufa pide al sitio la licencia
actualizada sin esperar a que venza.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
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

log = logging.getLogger("mufa.licencia")

# De donde se trae la licencia nueva de una suscripción.
URL_RENOVAR = os.environ.get("MUFA_URL_LICENCIAS", "https://mufa.pages.dev/api/licencia/renovar")
# De donde se pide la prueba gratis de Pro (14 días, una por instalación y por correo).
URL_PRUEBA = os.environ.get("MUFA_URL_PRUEBA", "https://mufa.pages.dev/api/prueba")
# Se empieza a buscar la licencia nueva cuando faltan estos días.
DIAS_ANTES_DE_RENOVAR = 10

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
    AVISOS = "avisos"
    INFORMES = "informes"
    CAPACIDAD = "capacidad"
    OLT = "olt"


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
FUNCIONES_PRO = FUNCIONES_GRATIS | {
    Funcion.AVISOS,
    Funcion.INFORMES,
    Funcion.CAPACIDAD,
    Funcion.OLT,
    Funcion.RESTAURACION,
    Funcion.AUTOMATIZACION,
}
# Empresa: todo, también AAA, mesa de ayuda y varios clientes.
FUNCIONES_POR_PLAN: dict[str, frozenset[Funcion]] = {
    "gratis": FUNCIONES_GRATIS,
    "pro": FUNCIONES_PRO,
    "consultor": FUNCIONES_PRO,
    "empresa": frozenset(Funcion),
}


@dataclass(frozen=True)
class Plan:
    nombre: str
    cliente: str
    max_equipos: int | None  # None = ilimitados (Pro y superiores)
    vence: date | None
    # Identificador de la licencia: con él se trae la renovación de una suscripción.
    id: str = ""
    # Llaves que abren los módulos Pro cifrados (mufa.modulos_pro). Solo en planes de pago.
    llaves_pro: tuple[str, ...] = ()
    # La prueba gratis de 14 días: Pro completo, sin renovación.
    prueba: bool = False

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
        return funcion in FUNCIONES_POR_PLAN.get(self.nombre, FUNCIONES_GRATIS)

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
        id=str(contenido.get("id") or ""),
        llaves_pro=_llaves(contenido),
        prueba=bool(contenido.get("prueba", False)),
    )


def _llaves(contenido: dict[str, object]) -> tuple[str, ...]:
    # "pro" es la primera llave (la que leen las versiones 0.1.4 y anteriores).
    primera = [contenido["pro"]] if contenido.get("pro") else []
    otras = contenido.get("llaves")
    todas = primera + (list(otras) if isinstance(otras, list) else [])
    return tuple(dict.fromkeys(str(llave) for llave in todas if llave))


def plan_vigente(archivo: Path, hoy: date) -> tuple[Plan, str]:
    """El plan de la licencia instalada, o el gratuito con el motivo si no hay una válida."""
    if not archivo.exists():
        return PLAN_GRATIS, ""
    try:
        return verificar(archivo.read_text(encoding="utf-8"), hoy), ""
    except LicenciaInvalida as error:
        return PLAN_GRATIS, str(error)


Obtener = Callable[[str], bytes]


def _obtener(url: str) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": "mufa"})
    with urllib.request.urlopen(pedido, timeout=20) as respuesta:
        datos: bytes = respuesta.read(64 * 1024)
        return datos


def renovar(
    archivo: Path,
    hoy: date,
    obtener: Obtener = _obtener,
    clave_publica: bytes | None = None,
    llaves_viejas: bool = False,
) -> Plan | None:
    """Trae la licencia nueva de una suscripción si la instalada está por vencer.

    Con llaves_viejas=True (los módulos Pro de esta versión no abren con las
    llaves de la licencia) la pide aunque falte mucho para que venza, y la
    acepta si vence el mismo día pero trae llaves nuevas.

    Devuelve el plan nuevo si la reemplazó; None si no hacía falta o no hay
    una más nueva (la suscripción se canceló, o todavía no se cobró el mes).
    """
    if not archivo.exists():
        return None
    texto = archivo.read_text(encoding="utf-8").strip()
    actual: Plan | None
    try:
        actual = verificar(texto, hoy, clave_publica)
    except LicenciaInvalida:
        # Vencida: igual se intenta, por si el pago del mes llegó tarde.
        actual = None
    if actual is not None:
        if actual.vence is None:
            return None
        if not llaves_viejas and actual.vence - hoy > timedelta(days=DIAS_ANTES_DE_RENOVAR):
            return None
        identificador = actual.id
    else:
        try:
            contenido = json.loads(_b64decode(texto.split(".")[0]))
            identificador = str(contenido.get("id") or "")
        except (ValueError, AttributeError):
            return None
    if not identificador:
        return None
    try:
        respuesta = json.loads(
            obtener(f"{URL_RENOVAR}?{urllib.parse.urlencode({'id': identificador})}")
        )
        nueva = verificar(str(respuesta["licencia"]), hoy, clave_publica)
    except (OSError, ValueError, KeyError, TypeError, LicenciaInvalida) as error:
        log.info("no hay licencia nueva todavía: %s", error)
        return None
    if nueva.id != identificador or nueva.vence is None:
        return None
    if actual is not None and actual.vence is not None:
        llaves_nuevas = not set(nueva.llaves_pro) <= set(actual.llaves_pro)
        if nueva.vence < actual.vence or (nueva.vence == actual.vence and not llaves_nuevas):
            return None
    temporal = archivo.with_name(archivo.name + ".nueva")
    temporal.write_text(str(respuesta["licencia"]).strip(), encoding="utf-8")
    temporal.replace(archivo)
    return nueva


class PruebaNoDisponible(Exception):
    """El sitio no dio la prueba (ya se usó, correo inválido, sin conexión...)."""


Pedir = Callable[[str, bytes], tuple[int, bytes]]


def _pedir(url: str, cuerpo: bytes) -> tuple[int, bytes]:
    pedido = urllib.request.Request(
        url,
        data=cuerpo,
        headers={"User-Agent": "mufa", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=20) as respuesta:
            return respuesta.status, respuesta.read(64 * 1024)
    except urllib.error.HTTPError as error:
        return error.code, error.read(64 * 1024)


def pedir_prueba(
    email: str,
    instalacion: str,
    hoy: date,
    pedir: Pedir | None = None,
    clave_publica: bytes | None = None,
) -> tuple[str, Plan]:
    """Pide al sitio la licencia de prueba de Pro. Devuelve (texto, plan)."""
    cuerpo = json.dumps({"email": email, "instalacion": instalacion}).encode()
    try:
        estado, datos = (pedir or _pedir)(URL_PRUEBA, cuerpo)
    except OSError as error:
        raise PruebaNoDisponible(f"no se pudo conectar con el sitio de mufa: {error}") from None
    try:
        respuesta = json.loads(datos)
    except ValueError:
        respuesta = {}
    if estado != 200 or "licencia" not in respuesta:
        motivo = respuesta.get("error") if isinstance(respuesta, dict) else None
        raise PruebaNoDisponible(motivo or f"el sitio respondió {estado}")
    texto = str(respuesta["licencia"]).strip()
    try:
        plan = verificar(texto, hoy, clave_publica)
    except LicenciaInvalida as error:
        raise PruebaNoDisponible(f"la licencia de prueba no es válida: {error}") from None
    return texto, plan
