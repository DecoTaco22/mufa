"""Versiones del sistema operativo con vulnerabilidades conocidas y explotadas.

La tabla es curada a mano: solo CVE con impacto real en redes de ISP y con
la versión que las corrige confirmada en los avisos del fabricante. No es
un escáner completo de vulnerabilidades; una versión que no aparece acá no
está garantizada como segura.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mufa.engine import check
from mufa.models import Contexto, Hallazgo, Severidad

Version = tuple[int, ...]


@dataclass(frozen=True)
class Vulnerabilidad:
    cve: str
    severidad: Severidad
    descripcion: str
    # Rangos afectados [desde, hasta) — "hasta" es la primera versión corregida.
    afectadas: tuple[tuple[Version, Version], ...]
    corregida_en: str


_ROUTEROS = (
    Vulnerabilidad(
        cve="CVE-2018-14847",
        severidad=Severidad.CRITICO,
        descripcion=(
            "Winbox deja leer archivos del router sin autenticarse, incluida la base de "
            "usuarios con sus contraseñas. Fue explotada en masa por botnets"
        ),
        afectadas=(((6, 29), (6, 40, 8)), ((6, 41), (6, 42, 1))),
        corregida_en="6.42.1 (o 6.40.8 en bugfix)",
    ),
    Vulnerabilidad(
        cve="CVE-2023-30799",
        severidad=Severidad.ALTO,
        descripcion=(
            "Un usuario del grupo full puede escalar a super-admin y ejecutar código en el "
            "sistema. Con la contraseña por defecto o una débil, es control total del equipo"
        ),
        afectadas=(((6,), (6, 48, 7)), ((6, 49), (6, 49, 7))),
        corregida_en="6.48.7 (long-term), 6.49.7 (stable) o RouterOS 7",
    ),
    Vulnerabilidad(
        cve="CVE-2019-3978",
        severidad=Severidad.MEDIO,
        descripcion=(
            "Un atacante sin autenticarse puede envenenar la caché DNS del router y "
            "redirigir a los clientes que lo usan como DNS"
        ),
        afectadas=(((6,), (6, 44, 6)), ((6, 45), (6, 45, 7))),
        corregida_en="6.44.6 (long-term) o 6.45.7 (stable)",
    ),
    Vulnerabilidad(
        cve="CVE-2023-41570",
        severidad=Severidad.MEDIO,
        descripcion=(
            "La API REST no respeta la lista 'Available From' de www/www-ssl: queda "
            "accesible desde redes que se creían bloqueadas"
        ),
        afectadas=(((7, 1), (7, 12)),),
        corregida_en="7.12",
    ),
)

_ORDEN = [Severidad.CRITICO, Severidad.ALTO, Severidad.MEDIO, Severidad.INFO]


def version_numerica(texto: str) -> Version | None:
    """ "6.48.6" -> (6, 48, 6); "7.15rc2 (testing)" -> (7, 15). None si no empieza con números."""
    coincidencia = re.match(r"(\d+(?:\.\d+)*)", texto.strip())
    if coincidencia is None:
        return None
    return tuple(int(parte) for parte in coincidencia.group(1).split("."))


def afectada(version: Version, vulnerabilidad: Vulnerabilidad) -> bool:
    return any(desde <= version < hasta for desde, hasta in vulnerabilidad.afectadas)


@check(
    id="MUFA-VER-001",
    severidad=Severidad.ALTO,
    titulo="Versión de RouterOS con vulnerabilidades conocidas",
    marcas=["mikrotik"],
)
def routeros_vulnerable(ctx: Contexto) -> Hallazgo | None:
    version = version_numerica(ctx.version)
    if version is None:
        return None
    encontradas = [v for v in _ROUTEROS if afectada(version, v)]
    if not encontradas:
        return None
    encontradas.sort(key=lambda v: _ORDEN.index(v.severidad))
    return Hallazgo(
        id="MUFA-VER-001",
        severidad=encontradas[0].severidad,
        titulo="Versión de RouterOS con vulnerabilidades conocidas",
        evidencia=f"RouterOS {ctx.version}: "
        + "; ".join(f"{v.cve} ({v.severidad.value})" for v in encontradas),
        impacto=". ".join(f"{v.cve}: {v.descripcion}" for v in encontradas) + ".",
        remediacion=[
            "# Sacar un respaldo antes de actualizar.",
            "# Versión mínima: " + "; ".join(f"{v.cve} → {v.corregida_en}" for v in encontradas),
            "/system package update set channel=long-term",
            "/system package update check-for-updates",
            "/system package update install",
            "# Después, actualizar también el firmware de la RouterBOARD:",
            "/system routerboard upgrade",
        ],
        referencia="https://mikrotik.com/supportsec",
    )
