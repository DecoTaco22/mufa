"""Sitios, equipos, credenciales cifradas y límites del plan."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from mufa.db import Equipo, Evento

API = "/api/v1"
EQUIPO = {
    "nombre": "CCR Nodo Norte",
    "marca": "mikrotik",
    "ip_gestion": "10.20.4.1",
    "usuario_ssh": "mufa",
    "password_ssh": "secreto-del-router",
}


def test_crear_equipo_no_devuelve_ni_guarda_la_password_en_claro(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    respuesta = cliente.post(f"{API}/equipos", json=EQUIPO, headers=admin)
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["tiene_credenciales"] is True
    assert "secreto-del-router" not in respuesta.text
    assert "password" not in " ".join(cuerpo)

    with cliente.app.state.mufa.sesiones() as db:  # type: ignore[attr-defined]
        equipo = db.scalar(select(Equipo))
        assert equipo is not None and equipo.password_cifrada is not None
        assert "secreto-del-router" not in equipo.password_cifrada
        eventos = " ".join(str(e.detalle) for e in db.scalars(select(Evento)))
        assert "secreto-del-router" not in eventos


def test_ip_y_marca_se_validan(cliente: TestClient, admin: dict[str, str]) -> None:
    ip_mala = {**EQUIPO, "ip_gestion": "no-es-una-ip"}
    assert cliente.post(f"{API}/equipos", json=ip_mala, headers=admin).status_code == 422
    marca_mala = {**EQUIPO, "marca": "inventada"}
    assert cliente.post(f"{API}/equipos", json=marca_mala, headers=admin).status_code == 422


def test_nombre_duplicado(cliente: TestClient, admin: dict[str, str]) -> None:
    assert cliente.post(f"{API}/equipos", json=EQUIPO, headers=admin).status_code == 201
    assert cliente.post(f"{API}/equipos", json=EQUIPO, headers=admin).status_code == 409


def test_actualizar_y_borrar_equipo(cliente: TestClient, admin: dict[str, str]) -> None:
    sitio = cliente.post(f"{API}/sitios", json={"nombre": "Nodo Norte"}, headers=admin).json()
    equipo = cliente.post(f"{API}/equipos", json=EQUIPO, headers=admin).json()

    cambios = {"modelo": "CCR2004", "sitio_id": sitio["id"], "password_ssh": None}
    actualizado = cliente.patch(f"{API}/equipos/{equipo['id']}", json=cambios, headers=admin)
    assert actualizado.status_code == 200
    assert actualizado.json()["modelo"] == "CCR2004"
    assert actualizado.json()["sitio_id"] == sitio["id"]
    assert actualizado.json()["tiene_credenciales"] is False

    sin_sitio = cliente.patch(
        f"{API}/equipos/{equipo['id']}", json={"sitio_id": 999}, headers=admin
    )
    assert sin_sitio.status_code == 422

    assert cliente.delete(f"{API}/equipos/{equipo['id']}", headers=admin).status_code == 204
    assert cliente.get(f"{API}/equipos/{equipo['id']}", headers=admin).status_code == 404


def test_plan_gratuito_limita_la_cantidad_de_equipos(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    limite = cliente.get(f"{API}/licencia", headers=admin).json()["max_equipos"]
    for numero in range(limite):
        equipo = {"nombre": f"R{numero}", "marca": "mikrotik", "ip_gestion": f"10.0.0.{numero + 1}"}
        assert cliente.post(f"{API}/equipos", json=equipo, headers=admin).status_code == 201
    extra = {"nombre": "uno-mas", "marca": "mikrotik", "ip_gestion": "10.0.1.1"}
    assert cliente.post(f"{API}/equipos", json=extra, headers=admin).status_code == 402


def test_listar_marcas(cliente: TestClient, admin: dict[str, str]) -> None:
    marcas = cliente.get(f"{API}/marcas", headers=admin).json()
    por_marca = {m["marca"]: m for m in marcas}
    assert por_marca["mikrotik"] == {
        "marca": "mikrotik",
        "nombre": "MikroTik",
        "con_adaptador": True,
        "con_respaldo": True,
    }
    # Huawei todavía no se audita, pero sí se respalda.
    assert por_marca["huawei"]["con_adaptador"] is False
    assert por_marca["huawei"]["con_respaldo"] is True
    assert por_marca["otra"]["con_respaldo"] is False
