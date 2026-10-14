"""Licencias firmadas: válidas, vencidas, adulteradas, e instalación por la API."""

from __future__ import annotations

import json
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


def test_pro_y_empresa_no_tienen_las_mismas_funciones(clave: Ed25519PrivateKey) -> None:
    pro = licencia.verificar(emitir(clave, "ISP", "pro", None, None), HOY, _publica(clave))
    empresa = licencia.verificar(emitir(clave, "ISP", "empresa", None, None), HOY, _publica(clave))
    assert pro.permite(licencia.Funcion.INFORMES) and pro.permite(licencia.Funcion.OLT)
    assert not pro.permite(licencia.Funcion.AAA)
    assert empresa.permite(licencia.Funcion.AAA)
    assert not licencia.PLAN_GRATIS.permite(licencia.Funcion.CAPACIDAD)


def _servidor(respuestas: dict[str, str]):  # type: ignore[no-untyped-def]
    pedidos: list[str] = []

    def obtener(url: str) -> bytes:
        pedidos.append(url)
        if "id=" not in url or url.split("id=")[1] not in respuestas:
            raise OSError("404")
        return json.dumps({"licencia": respuestas[url.split("id=")[1]]}).encode()

    return obtener, pedidos


def test_la_suscripcion_trae_sola_la_licencia_del_mes_nuevo(
    clave: Ed25519PrivateKey, tmp_path: Path
) -> None:
    archivo = tmp_path / "licencia.txt"
    archivo.write_text(emitir(clave, "ISP", "pro", None, date(2026, 10, 12), "abc123"))
    nueva = emitir(clave, "ISP", "pro", None, date(2026, 11, 12), "abc123")
    obtener, pedidos = _servidor({"abc123": nueva})

    plan = licencia.renovar(archivo, HOY, obtener, _publica(clave))
    assert plan is not None and plan.vence == date(2026, 11, 12)
    assert archivo.read_text() == nueva
    assert pedidos == [f"{licencia.URL_RENOVAR}?id=abc123"]
    # Ya renovada: falta más de un mes, no vuelve a preguntar.
    assert licencia.renovar(archivo, HOY, obtener, _publica(clave)) is None
    assert len(pedidos) == 1


def test_sin_pago_nuevo_la_licencia_queda_como_estaba(
    clave: Ed25519PrivateKey, tmp_path: Path
) -> None:
    archivo = tmp_path / "licencia.txt"
    actual = emitir(clave, "ISP", "pro", None, date(2026, 10, 12), "abc123")
    archivo.write_text(actual)
    # El sitio devuelve la misma (no se cobró el mes) o una de otro cliente.
    otra = emitir(clave, "Otro", "pro", None, date(2027, 1, 1), "zzz999")
    for respuesta in (actual, otra):
        obtener, _ = _servidor({"abc123": respuesta})
        assert licencia.renovar(archivo, HOY, obtener, _publica(clave)) is None
        assert archivo.read_text() == actual
    # Sin conexión, tampoco pasa nada.
    obtener, _ = _servidor({})
    assert licencia.renovar(archivo, HOY, obtener, _publica(clave)) is None


def test_una_licencia_vencida_se_recupera_si_llega_el_pago(
    clave: Ed25519PrivateKey, tmp_path: Path
) -> None:
    archivo = tmp_path / "licencia.txt"
    archivo.write_text(emitir(clave, "ISP", "pro", None, date(2026, 9, 30), "abc123"))
    nueva = emitir(clave, "ISP", "pro", None, date(2026, 11, 4), "abc123")
    obtener, _ = _servidor({"abc123": nueva})
    plan = licencia.renovar(archivo, HOY, obtener, _publica(clave))
    assert plan is not None and plan.vence == date(2026, 11, 4)


def test_una_licencia_perpetua_no_se_renueva(clave: Ed25519PrivateKey, tmp_path: Path) -> None:
    archivo = tmp_path / "licencia.txt"
    archivo.write_text(emitir(clave, "ISP", "pro", None, None, "abc123"))
    obtener, pedidos = _servidor({})
    assert licencia.renovar(archivo, HOY, obtener, _publica(clave)) is None
    assert pedidos == []
