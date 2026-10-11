"""Migraciones al día con los modelos, y cifrado de secretos."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from mufa.cifrado import Cifrador, ErrorDeCifrado, cargar_o_crear_clave
from mufa.db import Base, crear_motor
from mufa.migraciones import actualizar_base


def test_las_migraciones_crean_exactamente_los_modelos(tmp_path: Path) -> None:
    # Si alguien cambia un modelo y se olvida de generar la migración, esto falla.
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    actualizar_base(url)
    motor = crear_motor(url)
    with motor.connect() as conexion:
        diferencias = compare_metadata(MigrationContext.configure(conexion), Base.metadata)
    motor.dispose()
    assert diferencias == []


def test_cifrado_ida_y_vuelta(tmp_path: Path) -> None:
    cifrador = Cifrador(cargar_o_crear_clave(tmp_path / "secreto.key"))
    cifrado = cifrador.cifrar("password del router")
    assert "password" not in cifrado
    assert cifrador.descifrar(cifrado) == "password del router"


def test_la_clave_se_reusa_entre_arranques(tmp_path: Path) -> None:
    archivo = tmp_path / "secreto.key"
    assert cargar_o_crear_clave(archivo) == cargar_o_crear_clave(archivo)


def test_otra_clave_no_puede_descifrar(tmp_path: Path) -> None:
    cifrado = Cifrador(cargar_o_crear_clave(tmp_path / "a.key")).cifrar("secreto")
    with pytest.raises(ErrorDeCifrado):
        Cifrador(cargar_o_crear_clave(tmp_path / "b.key")).descifrar(cifrado)


def test_migracion_0002_conserva_usuarios_existentes(tmp_path: Path) -> None:
    from alembic import command
    from sqlalchemy import text

    from mufa.migraciones import configuracion

    url = f"sqlite:///{(tmp_path / 'vieja.db').as_posix()}"
    command.upgrade(configuracion(url), "0001")
    motor = crear_motor(url)
    with motor.begin() as conexion:
        for email in ("ana@a.com", "ana@b.com"):
            conexion.execute(
                text(
                    "INSERT INTO usuarios (email, nombre, hash_password, rol, activo, creado) "
                    "VALUES (:email, 'Ana', 'x', 'admin', 1, '2026-01-01')"
                ),
                {"email": email},
            )
    actualizar_base(url)
    with motor.connect() as conexion:
        usuarios = conexion.execute(text("SELECT usuario FROM usuarios ORDER BY id")).scalars()
        assert list(usuarios) == ["ana", "ana2"]
    motor.dispose()
