"""Respaldos de las marcas que todavía no tienen auditoría.

Para Huawei, Juniper, HPE, Ubiquiti, Nokia y ZTE mufa sabe sacar la
configuración completa (solo lectura) y compararla entre versiones, pero
todavía no la traduce al Contexto de las verificaciones.

Algunas familias usan comandos distintos según el sistema (Comware o
ArubaOS en HPE, EdgeOS o airOS en Ubiquiti): se prueba cada comando en
orden y se usa el primero que el equipo entiende. Todos están en la lista
blanca de su marca.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mufa.ssh import SesionDeLectura

# Respuestas de un equipo que no entendió el comando.
_RECHAZO = re.compile(
    r"^\s*(%|\^|error\b|unrecognized|invalid|unknown command|syntax error|"
    r"command not found|.*: not found|.*no such file)",
    re.IGNORECASE,
)


def _rechazado(texto: str) -> bool:
    lineas = [linea for linea in texto.replace("\r", "").split("\n") if linea.strip()]
    if not lineas:
        return True
    # Una configuración real es larga: un error ocupa una o dos líneas.
    return len(lineas) <= 4 and any(_RECHAZO.match(linea) for linea in lineas)


@dataclass(frozen=True)
class SoloRespaldo:
    marca: str
    nombre: str
    comandos: tuple[str, ...]
    # Líneas que cambian solas (fechas de guardado, encabezados con hora).
    volatiles: re.Pattern[str] | None = field(default=None)

    def leer_respaldo(self, sesion: SesionDeLectura) -> str:
        ultimo = ""
        for comando in self.comandos:
            try:
                texto = sesion.run_readonly(comando)
            except RuntimeError as error:
                ultimo = str(error)
                continue
            if _rechazado(texto):
                ultimo = texto.strip().split("\n")[0] or "respuesta vacía"
                continue
            return texto
        probados = ", ".join(f"«{c}»" for c in self.comandos)
        raise RuntimeError(
            f"el equipo no aceptó {probados}: {ultimo[:160]}. "
            "Revisa que el usuario tenga permiso para ver la configuración."
        )

    def normalizar_respaldo(self, texto: str) -> str:
        lineas = [linea.rstrip() for linea in texto.replace("\r\n", "\n").split("\n")]
        if self.volatiles is not None:
            lineas = [linea for linea in lineas if not self.volatiles.match(linea)]
        return "\n".join(lineas)


OTRAS: tuple[SoloRespaldo, ...] = (
    SoloRespaldo(
        "huawei",
        "Huawei VRP",
        ("display current-configuration",),
        re.compile(r"^\s*!(Software Version|Last configuration was|Time:|\s*Last )"),
    ),
    SoloRespaldo(
        "juniper",
        "Juniper Junos",
        ("show configuration",),
        re.compile(r"^## Last (commit|changed)"),
    ),
    SoloRespaldo(
        "hpe",
        "HPE / Aruba",
        ("display current-configuration", "show running-config"),
        re.compile(
            r"^(Running configuration:|Current configuration|Building configuration|!Last )"
        ),
    ),
    SoloRespaldo(
        "ubiquiti",
        "Ubiquiti EdgeOS / airOS",
        ("cat /config/config.boot", "cat /tmp/system.cfg", "show running-config"),
    ),
    SoloRespaldo(
        "nokia",
        "Nokia SR OS",
        ("admin display-config", "admin show configuration"),
        re.compile(r"^# (Generated|Finished) "),
    ),
    SoloRespaldo(
        "zte",
        "ZTE ZXROS",
        ("show running-config",),
        re.compile(r"^(Building configuration|Current configuration|!\s*(Last|Time))"),
    ),
)
