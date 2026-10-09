"""Sesión de la app web por cookie, anti-CSRF, servicio de la app y panel."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import mufa.api
from mufa.api import crear_app
from mufa.config import Ajustes
from tests.conftest import PASSWORD, CrearUsuario

API = "/api/v1"
WEB = {"X-Mufa-Cliente": "web"}
CSRF = {"X-Mufa-Csrf": "1"}


def test_login_web_usa_cookie_httponly_y_no_devuelve_token(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    respuesta = cliente.post(
        f"{API}/auth/login", json={"usuario": "admin", "password": PASSWORD}, headers=WEB
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["token"] is None
    cookie = respuesta.headers["set-cookie"]
    assert "mufa_sesion=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie.replace("Strict", "strict")
    assert "Path=/api" in cookie

    # El cliente de pruebas guarda la cookie: ya hay sesión sin cabecera Authorization.
    assert cliente.get(f"{API}/auth/yo").json()["usuario"] == "admin"


def test_con_cookie_los_cambios_exigen_la_cabecera_anti_csrf(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    cliente.post(f"{API}/auth/login", json={"usuario": "admin", "password": PASSWORD}, headers=WEB)
    sitio = {"nombre": "Nodo Norte"}
    assert cliente.post(f"{API}/sitios", json=sitio).status_code == 403
    assert cliente.post(f"{API}/sitios", json=sitio, headers=CSRF).status_code == 201


def test_logout_borra_la_cookie(cliente: TestClient, admin: dict[str, str]) -> None:
    cliente.post(f"{API}/auth/login", json={"usuario": "admin", "password": PASSWORD}, headers=WEB)
    assert cliente.post(f"{API}/auth/logout", headers=CSRF).status_code == 204
    cliente.cookies.clear()
    assert cliente.get(f"{API}/auth/yo").status_code == 401


@pytest.fixture
def cliente_con_web(
    ajustes: Ajustes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>mufa</title>", encoding="utf-8")
    (web / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no debería salir", encoding="utf-8")
    monkeypatch.setattr(mufa.api, "DIRECTORIO_WEB", web)
    with TestClient(crear_app(ajustes)) as cliente:
        yield cliente


def test_la_app_web_se_sirve_con_su_politica_de_seguridad(cliente_con_web: TestClient) -> None:
    for ruta in ("/", "/equipos", "/equipos/3"):
        respuesta = cliente_con_web.get(ruta)
        assert respuesta.status_code == 200
        assert "<title>mufa</title>" in respuesta.text
        politica = respuesta.headers["content-security-policy"]
        # Los scripts nunca pueden ser inline; los estilos sí (la terminal los necesita).
    scripts = next(d for d in politica.split(";") if d.strip().startswith("script-src"))
    assert scripts.strip() == "script-src 'self'"

    asset = cliente_con_web.get("/assets/app-abc123.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
    # La API conserva su política estricta.
    assert (
        cliente_con_web.get(f"{API}/salud")
        .headers["content-security-policy"]
        .startswith("default-src 'none'")
    )
    assert cliente_con_web.get(f"{API}/no-existe").status_code == 404


def test_no_se_puede_salir_del_directorio_web(cliente_con_web: TestClient) -> None:
    for ruta in ("/../secreto.txt", "/%2e%2e/secreto.txt", "/assets/../../secreto.txt"):
        assert "no debería salir" not in cliente_con_web.get(ruta).text


def test_panel(cliente: TestClient, admin: dict[str, str], crear_usuario: CrearUsuario) -> None:
    cliente.post(
        f"{API}/auditorias/archivo",
        files={"archivo": ("r.rsc", b"/ip dns\nset allow-remote-requests=yes\n")},
        headers=admin,
    )
    lector = crear_usuario("lector", mufa.permisos.Rol.LECTURA)
    panel = cliente.get(f"{API}/panel", headers=lector).json()
    assert panel["plan"] == "gratis"
    assert panel["equipos"] == 0
    # Las auditorías de archivo no son de un equipo del inventario: no cuentan como abiertas.
    assert panel["hallazgos_principales"] == []
