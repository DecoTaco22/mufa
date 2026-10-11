"""Inicio de sesión, permisos, usuarios y cabeceras de seguridad."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mufa.permisos import Rol
from tests.conftest import PASSWORD, CrearUsuario

API = "/api/v1"


def test_salud_no_pide_sesion(cliente: TestClient) -> None:
    respuesta = cliente.get(f"{API}/salud")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


def test_respuestas_llevan_cabeceras_de_seguridad(cliente: TestClient) -> None:
    cabeceras = cliente.get(f"{API}/salud").headers
    assert cabeceras["x-content-type-options"] == "nosniff"
    assert cabeceras["x-frame-options"] == "DENY"
    assert cabeceras["cache-control"] == "no-store"
    assert "default-src 'none'" in cabeceras["content-security-policy"]


def test_rutas_protegidas_piden_sesion(cliente: TestClient) -> None:
    assert cliente.get(f"{API}/equipos").status_code == 401
    malo = {"Authorization": "Bearer token-inventado"}
    assert cliente.get(f"{API}/equipos", headers=malo).status_code == 401


def test_login_y_yo(cliente: TestClient, admin: dict[str, str]) -> None:
    yo = cliente.get(f"{API}/auth/yo", headers=admin).json()
    assert yo["usuario"] == "admin"
    assert yo["rol"] == "admin"
    assert "hash_password" not in yo


def test_usuario_inexistente_y_password_incorrecta_dan_el_mismo_error(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    inexistente = cliente.post(f"{API}/auth/login", json={"usuario": "nadie", "password": "x"})
    incorrecta = cliente.post(f"{API}/auth/login", json={"usuario": "admin", "password": "x"})
    assert inexistente.status_code == incorrecta.status_code == 401
    assert inexistente.json() == incorrecta.json()


def test_bloqueo_tras_cinco_intentos_fallidos(cliente: TestClient, admin: dict[str, str]) -> None:
    for _ in range(5):
        respuesta = cliente.post(f"{API}/auth/login", json={"usuario": "admin", "password": "mala"})
        assert respuesta.status_code == 401
    # Ni siquiera la contraseña correcta entra mientras dura el bloqueo.
    bloqueado = cliente.post(f"{API}/auth/login", json={"usuario": "admin", "password": PASSWORD})
    assert bloqueado.status_code == 429


def test_logout_invalida_el_token(cliente: TestClient, admin: dict[str, str]) -> None:
    assert cliente.post(f"{API}/auth/logout", headers=admin).status_code == 204
    assert cliente.get(f"{API}/auth/yo", headers=admin).status_code == 401


def test_cambiar_password_cierra_las_sesiones(cliente: TestClient, admin: dict[str, str]) -> None:
    nueva = {"actual": PASSWORD, "nueva": "otra-clave-bien-larga"}
    assert cliente.post(f"{API}/auth/password", json=nueva, headers=admin).status_code == 204
    assert cliente.get(f"{API}/auth/yo", headers=admin).status_code == 401
    login = cliente.post(
        f"{API}/auth/login",
        json={"usuario": "admin", "password": "otra-clave-bien-larga"},
    )
    assert login.status_code == 200


def test_rol_sin_permiso_recibe_403(crear_usuario: CrearUsuario, cliente: TestClient) -> None:
    lector = crear_usuario("lector", Rol.LECTURA)
    assert cliente.get(f"{API}/equipos", headers=lector).status_code == 200
    assert cliente.get(f"{API}/usuarios", headers=lector).status_code == 403
    equipo = {"nombre": "R1", "marca": "mikrotik", "ip_gestion": "10.0.0.1"}
    assert cliente.post(f"{API}/equipos", json=equipo, headers=lector).status_code == 403


def test_admin_crea_usuarios_con_password_fuerte(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    debil = {"usuario": "tecnico2", "nombre": "N2", "rol": "tecnico_n2", "password": "corta"}
    assert cliente.post(f"{API}/usuarios", json=debil, headers=admin).status_code == 422

    bueno = {**debil, "password": "una-clave-de-tecnico"}
    creado = cliente.post(f"{API}/usuarios", json=bueno, headers=admin)
    assert creado.status_code == 201
    assert cliente.post(f"{API}/usuarios", json=bueno, headers=admin).status_code == 409


def test_no_se_puede_quitar_al_ultimo_admin(cliente: TestClient, admin: dict[str, str]) -> None:
    yo = cliente.get(f"{API}/auth/yo", headers=admin).json()
    respuesta = cliente.patch(f"{API}/usuarios/{yo['id']}", json={"rol": "lectura"}, headers=admin)
    assert respuesta.status_code == 409


def test_desactivar_usuario_cierra_sus_sesiones(
    cliente: TestClient, admin: dict[str, str], crear_usuario: CrearUsuario
) -> None:
    tecnico = crear_usuario("tec", Rol.TECNICO_N2)
    tecnico_id = cliente.get(f"{API}/auth/yo", headers=tecnico).json()["id"]
    cliente.patch(f"{API}/usuarios/{tecnico_id}", json={"activo": False}, headers=admin)
    assert cliente.get(f"{API}/auth/yo", headers=tecnico).status_code == 401


def test_registro_de_eventos_solo_para_senior_y_admin(
    cliente: TestClient, admin: dict[str, str], crear_usuario: CrearUsuario
) -> None:
    tecnico = crear_usuario("tec", Rol.TECNICO_N2)
    assert cliente.get(f"{API}/eventos", headers=tecnico).status_code == 403
    eventos = cliente.get(f"{API}/eventos", headers=admin).json()
    assert any(e["accion"] == "auth.login" for e in eventos)


def test_se_puede_entrar_con_el_email(cliente: TestClient, admin: dict[str, str]) -> None:
    respuesta = cliente.post(
        f"{API}/auth/login", json={"usuario": "Admin@Ejemplo.com", "password": PASSWORD}
    )
    assert respuesta.status_code == 200


def test_nombre_de_usuario_valido(cliente: TestClient, admin: dict[str, str]) -> None:
    malo = {"usuario": "Con Espacios", "nombre": "X", "rol": "lectura", "password": PASSWORD}
    assert cliente.post(f"{API}/usuarios", json=malo, headers=admin).status_code == 422
