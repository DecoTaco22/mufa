"""Fixtures del backend: una app con base de datos y directorio de datos propios por test."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mufa.api import crear_app
from mufa.auth import hashear_password
from mufa.config import Ajustes
from mufa.db import Usuario
from mufa.permisos import Rol

PASSWORD = "una-clave-bien-larga"


@pytest.fixture
def ajustes(tmp_path: Path) -> Ajustes:
    datos = tmp_path / "datos"
    # La verificación en dos pasos obligatoria se prueba aparte (test_dos_pasos).
    return Ajustes(
        dir_datos=datos,
        url_base_datos=f"sqlite:///{(tmp_path / 'mufa.db').as_posix()}",
        exigir_dos_pasos=False,
        # Las tareas automáticas se prueban aparte (test_tareas): acá no corren solas.
        intervalo_sondeo_minutos=0,
        intervalo_respaldo_horas=0,
        enviar_alertas=False,
    )


@pytest.fixture
def cliente(ajustes: Ajustes) -> Iterator[TestClient]:
    with TestClient(crear_app(ajustes)) as cliente:
        yield cliente


CrearUsuario = Callable[[str, Rol], dict[str, str]]


@pytest.fixture
def crear_usuario(cliente: TestClient) -> CrearUsuario:
    """Crea un usuario directo en la base y devuelve las cabeceras con su token."""

    def crear(usuario: str, rol: Rol) -> dict[str, str]:
        sesiones = cliente.app.state.mufa.sesiones  # type: ignore[attr-defined]
        with sesiones() as db:
            db.add(
                Usuario(
                    usuario=usuario,
                    email=f"{usuario}@ejemplo.com",
                    nombre=usuario,
                    rol=rol.value,
                    hash_password=hashear_password(PASSWORD),
                )
            )
            db.commit()
        respuesta = cliente.post(
            "/api/v1/auth/login", json={"usuario": usuario, "password": PASSWORD}
        )
        assert respuesta.status_code == 200, respuesta.text
        return {"Authorization": f"Bearer {respuesta.json()['token']}"}

    return crear


@pytest.fixture
def admin(crear_usuario: CrearUsuario) -> dict[str, str]:
    return crear_usuario("admin", Rol.ADMIN)
