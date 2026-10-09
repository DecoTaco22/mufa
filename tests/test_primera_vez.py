"""Crear el primer administrador desde la app web, con el token del servidor."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mufa import primera_vez
from mufa.config import Ajustes

API = "/api/v1"


def _admin(token: str) -> dict[str, str]:
    return {
        "token": token,
        "usuario": "duena",
        "nombre": "Dueña del ISP",
        "password": "una-clave-bien-larga",
    }


def test_primer_admin_con_token(cliente: TestClient, ajustes: Ajustes) -> None:
    assert cliente.get(f"{API}/sistema/inicial").json() == {"necesita_admin": True}
    archivo = primera_vez.archivo_token(ajustes.dir_datos)
    token = archivo.read_text(encoding="utf-8").strip()
    assert token == cliente.app.state.mufa.token_inicial  # type: ignore[attr-defined]

    assert cliente.post(f"{API}/sistema/inicial", json=_admin("otro")).status_code == 403
    creado = cliente.post(f"{API}/sistema/inicial", json=_admin(token))
    assert creado.status_code == 201, creado.text
    assert not archivo.exists()
    assert cliente.get(f"{API}/sistema/inicial").json() == {"necesita_admin": False}

    # Ya hay administrador: el mismo token no sirve para crear otro.
    assert cliente.post(f"{API}/sistema/inicial", json=_admin(token)).status_code == 409
    login = cliente.post(
        f"{API}/auth/login", json={"usuario": "duena", "password": "una-clave-bien-larga"}
    )
    assert login.status_code == 200


def test_contraseña_corta(cliente: TestClient, ajustes: Ajustes) -> None:
    token = primera_vez.archivo_token(ajustes.dir_datos).read_text(encoding="utf-8").strip()
    corta = {**_admin(token), "password": "corta"}
    assert cliente.post(f"{API}/sistema/inicial", json=corta).status_code == 422


def test_con_usuarios_no_hay_token(cliente: TestClient, admin: dict[str, str]) -> None:
    estado = cliente.app.state.mufa  # type: ignore[attr-defined]
    assert primera_vez.preparar(estado.sesiones, estado.ajustes.dir_datos) is None
    assert not primera_vez.archivo_token(estado.ajustes.dir_datos).exists()
