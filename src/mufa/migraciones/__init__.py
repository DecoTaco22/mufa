"""Migraciones de la base de datos (Alembic), sin alembic.ini.

El servidor las aplica solo al arrancar: quien instala mufa no tiene que
correr ningún comando de base de datos al actualizar de versión.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_DIRECTORIO = Path(__file__).parent


def configuracion(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_DIRECTORIO))
    # configparser interpreta "%": se escapa para URLs con contraseñas codificadas.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def actualizar_base(url: str) -> None:
    command.upgrade(configuracion(url), "head")
