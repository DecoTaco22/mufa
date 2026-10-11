"""Prueba de punta a punta de MUFA-DNS-001: parser -> contexto -> motor."""

from __future__ import annotations

from pathlib import Path

from mufa.engine import evaluar
from mufa.marcas import contexto_desde_archivo

FIXTURES = Path(__file__).parent / "fixtures"


def test_detecta_dns_abierto_sin_filtro() -> None:
    ctx = contexto_desde_archivo(FIXTURES / "dns_abierto.rsc")
    ids = [h.id for h in evaluar(ctx)]

    assert "MUFA-DNS-001" in ids


def test_no_marca_dns_abierto_si_esta_filtrado_en_el_borde() -> None:
    ctx = contexto_desde_archivo(FIXTURES / "dns_cerrado.rsc")
    ids = [h.id for h in evaluar(ctx)]

    assert "MUFA-DNS-001" not in ids
