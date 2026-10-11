"""Ajustes del servidor de mufa, leídos de variables de entorno.

mufa es autoalojado: todo lo que guarda (base de datos, clave de cifrado,
claves SSH conocidas) vive en un directorio de datos del propio servidor.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ajustes:
    dir_datos: Path
    url_base_datos: str
    duracion_sesion_horas: int = 8
    # Desactivarlo solo tiene sentido en pruebas: en producción los roles con
    # poder sobre la red no entran sin el segundo paso.
    exigir_dos_pasos: bool = True
    # Tareas automáticas. 0 las desactiva.
    intervalo_sondeo_minutos: int = 5
    intervalo_respaldo_horas: int = 24
    retencion_metricas_dias: int = 7
    enviar_alertas: bool = True
    # Nombres con que se puede llegar al servidor (cabecera Host). Vacío = cualquiera.
    # La app de escritorio lo fija en 127.0.0.1/localhost contra el «DNS rebinding».
    hosts_permitidos: tuple[str, ...] = ()

    @property
    def archivo_clave(self) -> Path:
        return self.dir_datos / "secreto.key"

    @property
    def known_hosts(self) -> Path:
        return self.dir_datos / "known_hosts"


def cargar_ajustes() -> Ajustes:
    """MUFA_DIR_DATOS (por defecto ~/.mufa) y MUFA_BASE_DATOS (por defecto SQLite ahí)."""
    dir_datos = Path(os.environ.get("MUFA_DIR_DATOS", str(Path.home() / ".mufa")))
    url = os.environ.get("MUFA_BASE_DATOS", f"sqlite:///{(dir_datos / 'mufa.db').as_posix()}")
    horas = int(os.environ.get("MUFA_DURACION_SESION_HORAS", "8"))
    exigir = os.environ.get("MUFA_EXIGIR_DOS_PASOS", "1") != "0"
    return Ajustes(
        dir_datos=dir_datos,
        url_base_datos=url,
        duracion_sesion_horas=horas,
        exigir_dos_pasos=exigir,
        intervalo_sondeo_minutos=int(os.environ.get("MUFA_SONDEO_MINUTOS", "5")),
        intervalo_respaldo_horas=int(os.environ.get("MUFA_RESPALDO_HORAS", "24")),
        retencion_metricas_dias=int(os.environ.get("MUFA_RETENCION_DIAS", "7")),
        enviar_alertas=os.environ.get("MUFA_ALERTAS", "1") != "0",
        hosts_permitidos=tuple(
            h.strip() for h in os.environ.get("MUFA_HOSTS_PERMITIDOS", "").split(",") if h.strip()
        ),
    )
