"""Migraciones de la base de datos (Alembic), sin alembic.ini.

El servidor las aplica solo al arrancar: quien instala mufa no tiene que
correr ningún comando de base de datos al actualizar de versión.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

_DIRECTORIO = Path(__file__).parent


class BaseMasNueva(RuntimeError):
    """La base la dejó una versión más nueva de mufa: esta no sabe leerla."""


def configuracion(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_DIRECTORIO))
    # configparser interpreta "%": se escapa para URLs con contraseñas codificadas.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _revision_guardada(url: str) -> str | None:
    motor = create_engine(url)
    try:
        with motor.connect() as conexion:
            return conexion.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except SQLAlchemyError:
        return None  # base nueva o sin migrar todavía
    finally:
        motor.dispose()


def actualizar_base(url: str) -> None:
    cfg = configuracion(url)
    guardada = _revision_guardada(url)
    if guardada is not None:
        try:
            ScriptDirectory.from_config(cfg).get_revision(guardada)
        except CommandError:
            # Pasa si la misma carpeta de datos la usó una versión más nueva (por ejemplo,
            # la del instalador) y después se abre una más vieja (la de la tienda).
            raise BaseMasNueva(
                "tus datos los guardó una versión más nueva de mufa. Actualiza esta app "
                "(Microsoft Store › Biblioteca › Obtener actualizaciones) o abre la versión "
                "más nueva que ya tienes instalada. Tus datos están intactos."
            ) from None
    command.upgrade(cfg, "head")
