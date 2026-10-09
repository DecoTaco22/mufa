"""Verificación en dos pasos: obligatoria por rol, activación, login, códigos reusados."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace

import pyotp
import pytest
from fastapi.testclient import TestClient

from mufa import dos_pasos
from mufa.api import crear_app
from mufa.config import Ajustes
from mufa.permisos import Rol
from tests.conftest import PASSWORD, CrearUsuario

API = "/api/v1"


@pytest.fixture
def cliente(ajustes: Ajustes) -> Iterator[TestClient]:
    with TestClient(crear_app(replace(ajustes, exigir_dos_pasos=True))) as cliente:
        yield cliente


def _codigo(secreto: str, desfase_pasos: int = 0) -> str:
    return pyotp.TOTP(secreto).at(time.time() + desfase_pasos * dos_pasos.PERIODO_SEGUNDOS)


def _activar(cliente: TestClient, cabeceras: dict[str, str]) -> str:
    inicio = cliente.post(f"{API}/auth/2fa/iniciar", headers=cabeceras).json()
    assert inicio["uri"].startswith("otpauth://totp/mufa:")
    confirmado = cliente.post(
        f"{API}/auth/2fa/confirmar", json={"codigo": _codigo(inicio["secreto"])}, headers=cabeceras
    )
    assert confirmado.status_code == 200
    assert len(confirmado.json()["codigos_recuperacion"]) == 10
    return str(inicio["secreto"])


def test_admin_sin_dos_pasos_no_puede_usar_la_app(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    admin = crear_usuario("admin", Rol.ADMIN)
    assert cliente.get(f"{API}/equipos", headers=admin).status_code == 403
    yo = cliente.get(f"{API}/auth/yo", headers=admin).json()
    assert yo["dos_pasos_requerido"] is True

    _activar(cliente, admin)
    assert cliente.get(f"{API}/equipos", headers=admin).status_code == 200


def test_agente_puede_trabajar_sin_dos_pasos(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    agente = crear_usuario("agente", Rol.AGENTE_N1)
    assert cliente.get(f"{API}/equipos", headers=agente).status_code == 200


def test_tecnico_tiene_que_activar_dos_pasos(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    # Puede usar las credenciales de los equipos y la terminal: sin segundo paso, no entra.
    tecnico = crear_usuario("tecnico", Rol.TECNICO_N2)
    assert cliente.get(f"{API}/equipos", headers=tecnico).status_code == 403


def test_login_con_dos_pasos(cliente: TestClient, crear_usuario: CrearUsuario) -> None:
    secreto = _activar(cliente, crear_usuario("admin", Rol.ADMIN))

    sin_codigo = cliente.post(f"{API}/auth/login", json={"usuario": "admin", "password": PASSWORD})
    assert sin_codigo.status_code == 401
    assert sin_codigo.headers["x-mufa-dos-pasos"] == "requerido"

    malo = cliente.post(
        f"{API}/auth/login", json={"usuario": "admin", "password": PASSWORD, "codigo": "000000"}
    )
    assert malo.status_code == 401

    # El código de confirmación ya se usó: el siguiente paso de tiempo sí sirve.
    bueno = cliente.post(
        f"{API}/auth/login",
        json={"usuario": "admin", "password": PASSWORD, "codigo": _codigo(secreto, 1)},
    )
    assert bueno.status_code == 200


def test_un_codigo_no_se_puede_reusar(cliente: TestClient, crear_usuario: CrearUsuario) -> None:
    secreto = _activar(cliente, crear_usuario("admin", Rol.ADMIN))
    codigo = _codigo(secreto, 1)
    entrada = {"usuario": "admin", "password": PASSWORD, "codigo": codigo}
    assert cliente.post(f"{API}/auth/login", json=entrada).status_code == 200
    assert cliente.post(f"{API}/auth/login", json=entrada).status_code == 401


def test_admin_restablece_los_dos_pasos_de_otro(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    admin = crear_usuario("admin", Rol.ADMIN)
    _activar(cliente, admin)
    senior = crear_usuario("senior", Rol.SENIOR)
    _activar(cliente, senior)
    senior_id = cliente.get(f"{API}/auth/yo", headers=senior).json()["id"]

    assert (
        cliente.post(f"{API}/usuarios/{senior_id}/2fa/restablecer", headers=admin).status_code
        == 204
    )
    # Sus sesiones se cerraron y al volver tiene que configurarla otra vez.
    assert cliente.get(f"{API}/auth/yo", headers=senior).status_code == 401
    login = cliente.post(f"{API}/auth/login", json={"usuario": "senior", "password": PASSWORD})
    assert login.status_code == 200
    nuevo = {"Authorization": f"Bearer {login.json()['token']}"}
    assert cliente.get(f"{API}/auth/yo", headers=nuevo).json()["dos_pasos_requerido"] is True


def test_verificar_rechaza_pasos_viejos() -> None:
    secreto = dos_pasos.nuevo_secreto()
    ahora = time.time()
    paso = int(ahora // dos_pasos.PERIODO_SEGUNDOS)
    codigo = pyotp.TOTP(secreto).at(ahora)
    assert dos_pasos.verificar(secreto, codigo, ultimo_paso=0, ahora_segundos=ahora) == paso
    assert dos_pasos.verificar(secreto, codigo, ultimo_paso=paso, ahora_segundos=ahora) is None


def test_codigo_de_recuperacion_sirve_una_sola_vez(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    admin = crear_usuario("admin", Rol.ADMIN)
    inicio = cliente.post(f"{API}/auth/2fa/iniciar", headers=admin).json()
    confirmado = cliente.post(
        f"{API}/auth/2fa/confirmar", json={"codigo": _codigo(inicio["secreto"])}, headers=admin
    ).json()
    codigo = confirmado["codigos_recuperacion"][0]

    entrada = {"usuario": "admin", "password": PASSWORD, "codigo": codigo.upper()}
    assert cliente.post(f"{API}/auth/login", json=entrada).status_code == 200
    assert cliente.post(f"{API}/auth/login", json=entrada).status_code == 401
    eventos = cliente.get(f"{API}/eventos", headers=admin).json()
    assert any(e["accion"] == "auth.codigo_recuperacion_usado" for e in eventos)


def test_regenerar_codigos_invalida_los_anteriores(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    admin = crear_usuario("admin", Rol.ADMIN)
    inicio = cliente.post(f"{API}/auth/2fa/iniciar", headers=admin).json()
    viejos = cliente.post(
        f"{API}/auth/2fa/confirmar", json={"codigo": _codigo(inicio["secreto"])}, headers=admin
    ).json()["codigos_recuperacion"]
    nuevos = cliente.post(
        f"{API}/auth/2fa/codigos-recuperacion",
        json={"password": PASSWORD, "codigo": _codigo(inicio["secreto"], 1)},
        headers=admin,
    ).json()["codigos_recuperacion"]
    assert set(viejos).isdisjoint(nuevos)
    viejo = {"usuario": "admin", "password": PASSWORD, "codigo": viejos[1]}
    assert cliente.post(f"{API}/auth/login", json=viejo).status_code == 401
