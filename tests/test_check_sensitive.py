"""Pruebas del hook de pre-commit que bloquea datos sensibles."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_sensitive import es_ip_publica, revisar_archivo


def test_dns_publicos_conocidos_no_se_marcan() -> None:
    assert not es_ip_publica("8.8.8.8")
    assert not es_ip_publica("1.1.1.1")


def test_ip_privada_no_se_marca() -> None:
    assert not es_ip_publica("10.0.0.1")
    assert not es_ip_publica("192.168.1.1")


def test_ip_de_cgnat_no_se_marca() -> None:
    assert not es_ip_publica("100.64.0.1")
    assert not es_ip_publica("100.127.255.254")


def test_ip_publica_se_marca() -> None:
    # Los rangos de documentación de RFC 5737 (192.0.2.0/24, etc.) los
    # trata Python como privados/especiales, así que no sirven para este
    # caso. Se usa en cambio un placeholder de red genérico, sin dueño
    # relevante (ver el marcador en la línea de abajo).
    assert es_ip_publica("1.2.3.4")  # mufa: permitir


def test_el_marcador_permite_una_ip_publica_en_un_archivo(tmp_path: Path) -> None:
    archivo = tmp_path / "ejemplo.txt"
    archivo.write_text("servidor de prueba en 1.2.3.4  # mufa: permitir\n", encoding="utf-8")

    assert revisar_archivo(archivo, palabras_sensibles=[]) == []


def test_sin_marcador_la_misma_ip_se_bloquea(tmp_path: Path) -> None:
    archivo = tmp_path / "ejemplo.txt"
    archivo.write_text("servidor de prueba en 1.2.3.4\n", encoding="utf-8")  # mufa: permitir

    assert revisar_archivo(archivo, palabras_sensibles=[]) != []


def test_un_oid_de_snmp_no_es_una_ip(tmp_path: Path) -> None:
    archivo = tmp_path / "snmp.py"
    archivo.write_text('SYS_DESCR = "1.3.6.1.2.1.1.1.0"\n', encoding="utf-8")

    assert revisar_archivo(archivo, palabras_sensibles=[]) == []


def test_una_ip_al_final_de_una_oracion_se_detecta(tmp_path: Path) -> None:
    archivo = tmp_path / "nota.txt"
    archivo.write_text("el servidor es 1.2.3.4.\n", encoding="utf-8")  # mufa: permitir

    assert revisar_archivo(archivo, palabras_sensibles=[]) != []
