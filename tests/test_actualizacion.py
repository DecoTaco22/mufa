"""Actualizaciones: manifiesto firmado, qué instalación se actualiza sola y la API."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from mufa import actualizacion
from mufa.actualizacion import Actualizador, Modo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from firmar_actualizacion import firmar, manifiesto, notas_de

API = "/api/v1"
INSTALADOR = b"instalador de mufa 9.9.9"


@pytest.fixture
def clave() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _publica(clave: Ed25519PrivateKey) -> bytes:
    return clave.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _manifiesto(
    clave: Ed25519PrivateKey, version: str = "9.9.9", contenido: bytes = INSTALADOR
) -> str:
    archivo = {
        "nombre": "mufa-instalador-windows.exe",
        "url": "https://ejemplo/mufa-instalador-windows.exe",
        "sha256": hashlib.sha256(contenido).hexdigest(),
        "tamano": len(contenido),
    }
    return firmar(
        clave,
        {
            "version": version,
            "publicada": "2026-10-20",
            "notas": "- Algo nuevo.",
            "archivos": {"windows": archivo, "macos": {**archivo, "nombre": "mufa-macos.dmg"}},
        },
    )


class Instalacion:
    """Un Actualizador con internet, descarga e instalador simulados."""

    def __init__(self, clave: Ed25519PrivateKey, tmp_path: Path, modo: Modo, **kw: object) -> None:
        self.manifiesto = _manifiesto(clave, **kw)  # type: ignore[arg-type]
        self.descargado = INSTALADOR
        self.ejecutados: list[tuple[Path, Modo]] = []
        self.cerrada = False
        self.actualizador = Actualizador(
            tmp_path,
            modo,
            obtener=lambda _url: self.manifiesto.encode(),
            descargar=lambda _url, destino, _max: destino.write_bytes(self.descargado),
            ejecutar=lambda archivo, modo: self.ejecutados.append((archivo, modo)),
            clave_publica=_publica(clave),
            version_actual="0.1.4",
        )
        self.actualizador.al_cerrar = self._cerrar

    def _cerrar(self) -> None:
        self.cerrada = True


def test_el_manifiesto_firmado_se_verifica(clave: Ed25519PrivateKey) -> None:
    novedad = actualizacion.verificar_manifiesto(_manifiesto(clave), _publica(clave))
    assert novedad.version == "9.9.9"
    assert novedad.archivos["windows"].sha256 == hashlib.sha256(INSTALADOR).hexdigest()


def test_un_manifiesto_adulterado_o_de_otra_clave_no_pasa(clave: Ed25519PrivateKey) -> None:
    datos, firma = _manifiesto(clave).split(".")
    otro, _ = _manifiesto(clave, version="10.0.0").split(".")
    with pytest.raises(actualizacion.ManifiestoInvalido, match="firma"):
        actualizacion.verificar_manifiesto(f"{otro}.{firma}", _publica(clave))
    with pytest.raises(actualizacion.ManifiestoInvalido, match="firma"):
        actualizacion.verificar_manifiesto(
            f"{datos}.{firma}", _publica(Ed25519PrivateKey.generate())
        )
    # El de verdad, con la clave pública incluida en mufa: nadie más puede firmar.
    with pytest.raises(actualizacion.ManifiestoInvalido):
        actualizacion.verificar_manifiesto(_manifiesto(clave))


def test_avisa_solo_si_la_version_es_mas_nueva(clave: Ed25519PrivateKey, tmp_path: Path) -> None:
    misma = Instalacion(clave, tmp_path, Modo.INSTALADOR, version="0.1.4")
    assert misma.actualizador.buscar() is None
    assert misma.actualizador.archivo is None
    nueva = Instalacion(clave, tmp_path, Modo.INSTALADOR, version="0.1.10")
    assert nueva.actualizador.buscar() is not None
    assert nueva.actualizador.archivo is not None


def test_windows_descarga_verifica_instala_y_se_cierra(
    clave: Ed25519PrivateKey, tmp_path: Path
) -> None:
    inst = Instalacion(clave, tmp_path, Modo.INSTALADOR)
    inst.actualizador.buscar()
    inst.actualizador.instalar()
    archivo, modo = inst.ejecutados[0]
    assert (archivo.name, modo) == ("mufa-instalador-windows.exe", Modo.INSTALADOR)
    assert archivo.read_bytes() == INSTALADOR
    assert inst.cerrada
    assert inst.actualizador.estado == "instalando"


def test_mac_usa_la_imagen_de_disco(clave: Ed25519PrivateKey, tmp_path: Path) -> None:
    inst = Instalacion(clave, tmp_path, Modo.MACOS)
    inst.actualizador.buscar()
    inst.actualizador.instalar()
    assert inst.ejecutados[0][0].name == "mufa-macos.dmg"


def test_un_archivo_cambiado_no_se_instala(clave: Ed25519PrivateKey, tmp_path: Path) -> None:
    inst = Instalacion(clave, tmp_path, Modo.INSTALADOR)
    inst.descargado = b"otro programa"
    inst.actualizador.buscar()
    with pytest.raises(RuntimeError, match="no coincide"):
        inst.actualizador.instalar()
    assert inst.ejecutados == []
    assert not inst.cerrada
    assert inst.actualizador.estado == ""
    assert "no coincide" in inst.actualizador.error
    assert not (tmp_path / "actualizaciones" / "mufa-instalador-windows.exe").exists()


@pytest.mark.parametrize("modo", [Modo.SERVIDOR, Modo.PORTATIL, Modo.CODIGO])
def test_servidor_portatil_y_codigo_solo_avisan(
    clave: Ed25519PrivateKey, tmp_path: Path, modo: Modo
) -> None:
    inst = Instalacion(clave, tmp_path, modo)
    assert inst.actualizador.buscar() is not None
    assert inst.actualizador.archivo is None
    assert inst.actualizador.pasos
    with pytest.raises(RuntimeError):
        inst.actualizador.instalar()


def test_la_tienda_no_busca(clave: Ed25519PrivateKey, tmp_path: Path) -> None:
    assert not Instalacion(clave, tmp_path, Modo.TIENDA).actualizador.busca


def test_sin_internet_queda_el_motivo(tmp_path: Path) -> None:
    def sin_red(_url: str) -> bytes:
        raise OSError("sin conexión")

    a = Actualizador(tmp_path, Modo.INSTALADOR, obtener=sin_red)
    assert a.buscar() is None
    assert "sin conexión" in a.error


def test_modo_desde_el_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUFA_MODO", "servidor")
    assert actualizacion.modo_actual() is Modo.SERVIDOR
    monkeypatch.delenv("MUFA_MODO")
    assert actualizacion.modo_actual() is Modo.CODIGO


def test_el_manifiesto_de_una_version_trae_sus_notas(
    clave: Ed25519PrivateKey, tmp_path: Path
) -> None:
    (tmp_path / "mufa-instalador-windows.exe").write_bytes(INSTALADOR)
    (tmp_path / "mufa-macos.dmg").write_bytes(b"dmg")
    cambios = "# Cambios\n\n## v0.2.0\n\n- Lo nuevo.\n\n## v0.1.4\n\n- Lo viejo.\n"
    assert notas_de("0.2.0", cambios) == "- Lo nuevo."
    texto = firmar(clave, manifiesto("0.2.0", tmp_path, "DecoTaco22/mufa", cambios))
    novedad = actualizacion.verificar_manifiesto(texto, _publica(clave))
    assert novedad.notas == "- Lo nuevo."
    assert novedad.archivos["macos"].url.endswith("/releases/download/v0.2.0/mufa-macos.dmg")
    assert novedad.archivos["macos"].sha256 == hashlib.sha256(b"dmg").hexdigest()


def test_la_api_muestra_la_version_y_se_puede_apagar(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    datos = cliente.get(f"{API}/sistema/actualizacion", headers=admin).json()
    assert datos["version_actual"]
    assert datos["nueva"] is None
    assert not datos["puede_instalar"]
    # En las pruebas MUFA_BUSCAR_ACTUALIZACIONES=0: no busca.
    assert datos["buscar"] is False

    r = cliente.put(f"{API}/sistema/actualizacion", headers=admin, json={"buscar": False})
    assert r.status_code == 200
    estado = cliente.app.state.mufa  # type: ignore[attr-defined]
    with estado.sesiones() as db:
        assert not actualizacion.buscar_activado(db)

    r = cliente.post(f"{API}/sistema/actualizacion/instalar", headers=admin)
    assert r.status_code == 409


def test_solo_el_admin_instala(cliente: TestClient, crear_usuario) -> None:  # type: ignore[no-untyped-def]
    from mufa.permisos import Rol

    lector = crear_usuario("lector1", Rol.LECTURA)
    assert cliente.get(f"{API}/sistema/actualizacion", headers=lector).status_code == 200
    assert cliente.post(f"{API}/sistema/actualizacion/instalar", headers=lector).status_code == 403
