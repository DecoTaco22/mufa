"""Entorno de Alembic: aplica las migraciones sobre la URL de la configuración."""

from __future__ import annotations

from alembic import context

from mufa.db import Base, crear_motor

url = context.config.get_main_option("sqlalchemy.url")
if url is None:
    raise RuntimeError("falta sqlalchemy.url en la configuración de Alembic")

motor = crear_motor(url)
with motor.connect() as conexion:
    context.configure(
        connection=conexion,
        target_metadata=Base.metadata,
        # SQLite no soporta ALTER TABLE completo: batch recrea la tabla.
        render_as_batch=conexion.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()
motor.dispose()
