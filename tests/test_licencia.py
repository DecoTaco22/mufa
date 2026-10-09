"""Licencias firmadas: válidas, vencidas, adulteradas, e instalación por la API."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from mufa import licencia

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from emitir_licencia import emitir

HOY = date(2026, 10, 5)


@pytest.fixture
def clave() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _publica(clave: Ed25519PrivateKey) -> bytes:
    return clave.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def test_licencia_valida(clave: Ed25519PrivateKey) -> None:
    texto = emitir(clave, "ISP Ejemplo", "pro", 200, date(2027, 1, 1))
    plan = licencia.verificar(texto, HOY, _publica(clave))
    assert (plan.nombre, plan.cliente, plan.max_equipos) == ("pro", "ISP Ejemplo", 200)


def test_licencia_pro_con_equipos_ilimitados(clave: Ed25519PrivateKey) -> None:
    plan = licencia.verificar(emitir(clave, "ISP", "pro", None, None), HOY, _publica(clave))
    assert plan.max_equipos is None
    assert plan.admite_otro_equipo(100_000)
    assert not licencia.PLAN_GRATIS.admite_otro_equipo(licencia.MAX_EQUIPOS_GRATIS)


def test_licencia_vencida(clave: Ed25519PrivateKey) -> None:
    texto = emitir(clave, "ISP Ejemplo", "pro", 200, date(2026, 1, 1))
    with pytest.raises(licencia.LicenciaInvalida, match="venció"):
        licencia.verificar(texto, HOY, _publica(clave))


def test_licencia_adulterada_no_pasa(clave: Ed25519PrivateKey) -> None:
    texto = emitir(clave, "ISP Ejemplo", "pro", 200, None)
    _datos, firma = texto.split(".")
    otra = emitir(clave, "ISP Ejemplo", "empresa", 100000, None).split(".")[0]
    with pytest.raises(licencia.LicenciaInvalida, match="firma"):
        licencia.verificar(f"{otra}.{firma}", HOY, _publica(clave))


def test_licencia_de_otro_emisor_no_pasa(clave: Ed25519PrivateKey) -> None:
    texto = emitir(Ed25519PrivateKey.generate(), "Pirata", "empresa", 100000, None)
    with pytest.raises(licencia.LicenciaInvalida):
        licencia.verificar(texto, HOY, _publica(clave))


def test_instalar_licencia_por_la_api_amplia_el_limite(
    cliente: TestClient,
    admin: dict[str, str],
    clave: Ed25519PrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(licencia, "CLAVE_PUBLICA_EMISOR", _publica(clave))
    falsa = emitir(Ed25519PrivateKey.generate(), "Pirata", "empresa", 9999, None)
    assert (
        cliente.put("/api/v1/licencia", json={"licencia": falsa}, headers=admin).status_code == 422
    )

    buena = emitir(clave, "ISP Ejemplo", "pro", 200, None)
    respuesta = cliente.put("/api/v1/licencia", json={"licencia": buena}, headers=admin)
    assert respuesta.status_code == 200
    assert respuesta.json()["plan"] == "pro"
    assert respuesta.json()["max_equipos"] == 200
