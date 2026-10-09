"""Alertas: canales, despachador sobre el registro de eventos y formato de cada envío."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Self

import pytest
from fastapi.testclient import TestClient

from mufa import alertas
from mufa.db import CanalAlerta
from mufa.permisos import Rol
from mufa.servicios import registrar
from tests.conftest import CrearUsuario

API = "/api/v1"
WEBHOOK = {
    "nombre": "NOC",
    "tipo": "webhook",
    "destino": "https://noc.ejemplo.com/hook",
    "secreto": "clave-de-firma",
    "eventos": ["equipo.caido"],
}


class Buzon:
    def __init__(self) -> None:
        self.mensajes: list[tuple[str, str | None, alertas.Mensaje]] = []

    def __call__(self, canal: CanalAlerta, secreto: str | None, mensaje: alertas.Mensaje) -> None:
        self.mensajes.append((canal.nombre, secreto, mensaje))


@pytest.fixture
def buzon(cliente: TestClient) -> Buzon:
    falso = Buzon()
    cliente.app.state.mufa.enviador = falso  # type: ignore[attr-defined]
    return falso


def test_canal_valida_y_no_devuelve_el_secreto(cliente: TestClient, admin: dict[str, str]) -> None:
    sin_token = {**WEBHOOK, "tipo": "telegram", "secreto": None, "destino": "123456"}
    assert cliente.post(f"{API}/alertas/canales", json=sin_token, headers=admin).status_code == 422
    sin_eventos = {**WEBHOOK, "eventos": []}
    assert (
        cliente.post(f"{API}/alertas/canales", json=sin_eventos, headers=admin).status_code == 422
    )

    respuesta = cliente.post(f"{API}/alertas/canales", json=WEBHOOK, headers=admin)
    assert respuesta.status_code == 201
    assert "clave-de-firma" not in respuesta.text
    assert respuesta.json()["tiene_secreto"] is True


def test_tecnico_no_configura_alertas(cliente: TestClient, crear_usuario: CrearUsuario) -> None:
    tecnico = crear_usuario("tecnico", Rol.TECNICO_N2)
    assert cliente.post(f"{API}/alertas/canales", json=WEBHOOK, headers=tecnico).status_code == 403
    assert cliente.get(f"{API}/alertas/tipos", headers=tecnico).status_code == 200


def test_probar_un_canal(cliente: TestClient, admin: dict[str, str], buzon: Buzon) -> None:
    canal = cliente.post(f"{API}/alertas/canales", json=WEBHOOK, headers=admin).json()
    assert (
        cliente.post(f"{API}/alertas/canales/{canal['id']}/probar", headers=admin).status_code
        == 204
    )
    nombre, secreto, mensaje = buzon.mensajes[0]
    assert (nombre, secreto, mensaje.titulo) == ("NOC", "clave-de-firma", "Prueba de alerta")


def test_despachador_avisa_solo_lo_suscrito_y_una_vez(
    cliente: TestClient, admin: dict[str, str], buzon: Buzon
) -> None:
    cliente.post(f"{API}/alertas/canales", json=WEBHOOK, headers=admin)
    estado = cliente.app.state.mufa  # type: ignore[attr-defined]
    with estado.sesiones() as db:
        # Primera pasada: marca el punto de partida, no avisa lo viejo.
        assert alertas.procesar_pendientes(db, estado.cifrador, buzon) == 0
        registrar(db, None, "equipo.caido", "OLT Nodo Sur", {"error": "sin respuesta"})
        registrar(db, None, "equipo.recuperado", "Otro")  # el canal no lo pidió
        registrar(db, None, "auth.login", "admin")  # no es alertable
        db.flush()
        assert alertas.procesar_pendientes(db, estado.cifrador, buzon) == 1
        assert alertas.procesar_pendientes(db, estado.cifrador, buzon) == 0
        db.commit()
    _, _, mensaje = buzon.mensajes[0]
    assert mensaje.texto == "[mufa] Equipo caído: OLT Nodo Sur\nerror: sin respuesta"


def test_un_canal_que_falla_no_frena_a_los_demas(
    cliente: TestClient, admin: dict[str, str], buzon: Buzon
) -> None:
    for nombre in ("Roto", "Bueno"):
        cliente.post(f"{API}/alertas/canales", json={**WEBHOOK, "nombre": nombre}, headers=admin)

    def enviador(canal: CanalAlerta, secreto: str | None, mensaje: alertas.Mensaje) -> None:
        if canal.nombre == "Roto":
            raise ConnectionError("no responde")
        buzon(canal, secreto, mensaje)

    estado = cliente.app.state.mufa  # type: ignore[attr-defined]
    with estado.sesiones() as db:
        alertas.procesar_pendientes(db, estado.cifrador, enviador)
        registrar(db, None, "equipo.caido", "R1")
        db.flush()
        assert alertas.procesar_pendientes(db, estado.cifrador, enviador) == 1
    assert [m[0] for m in buzon.mensajes] == ["Bueno"]


MENSAJE = alertas.Mensaje(
    tipo="equipo.caido",
    titulo="Equipo caído",
    objeto="R1",
    detalle={"error": "timeout"},
    momento=datetime(2026, 10, 5, tzinfo=UTC),
)


class _Respuesta:
    def raise_for_status(self) -> None:
        pass


def test_webhook_firmado(monkeypatch: pytest.MonkeyPatch) -> None:
    enviado: dict[str, Any] = {}

    def post(url: str, **kwargs: Any) -> _Respuesta:
        enviado.update(url=url, **kwargs)
        return _Respuesta()

    monkeypatch.setattr(alertas.httpx, "post", post)
    canal = CanalAlerta(tipo="webhook", destino="https://noc.ejemplo.com/hook", configuracion={})
    alertas.enviar(canal, "clave-de-firma", MENSAJE)

    cuerpo = enviado["content"]
    assert json.loads(cuerpo)["objeto"] == "R1"
    firma = enviado["headers"]["X-Mufa-Firma"]
    assert firma == f"sha256={alertas.firmar('clave-de-firma', cuerpo)}"


def test_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    enviado: dict[str, Any] = {}

    def post(url: str, **kwargs: Any) -> _Respuesta:
        enviado.update(url=url, **kwargs)
        return _Respuesta()

    monkeypatch.setattr(alertas.httpx, "post", post)
    canal = CanalAlerta(tipo="telegram", destino="-100123", configuracion={})
    alertas.enviar(canal, "TOKEN", MENSAJE)
    assert enviado["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert enviado["json"] == {"chat_id": "-100123", "text": MENSAJE.texto}


def test_correo_con_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    acciones: list[str] = []

    class SMTPFalso:
        def __init__(self, host: str, puerto: int, timeout: float) -> None:
            acciones.append(f"conectar {host}:{puerto}")

        def starttls(self, context: object) -> None:
            acciones.append("starttls")

        def login(self, usuario: str, password: str) -> None:
            acciones.append(f"login {usuario}")

        def send_message(self, correo: Any) -> None:
            acciones.append(f"enviar a {correo['To']}: {correo['Subject']}")

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    monkeypatch.setattr(alertas.smtplib, "SMTP", SMTPFalso)
    canal = CanalAlerta(
        tipo="correo",
        destino="noc@empresa.ejemplo",
        configuracion={"servidor": "smtp.ejemplo", "puerto": 587, "usuario": "mufa"},
    )
    alertas.enviar(canal, "clave-smtp", MENSAJE)
    assert acciones == [
        "conectar smtp.ejemplo:587",
        "starttls",
        "login mufa",
        "enviar a noc@empresa.ejemplo: [mufa] Equipo caído: R1",
    ]
