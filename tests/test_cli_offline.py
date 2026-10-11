"""Prueba de punta a punta: CLI en modo --offline (sin router real)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from mufa.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_audit_offline_texto_detecta_dns_abierto() -> None:
    resultado = runner.invoke(app, ["audit", "--offline", str(FIXTURES / "dns_abierto.rsc")])

    assert resultado.exit_code == 0
    assert "MUFA-DNS-001" in resultado.stdout


def test_audit_offline_html_genera_archivo(tmp_path: Path) -> None:
    salida = tmp_path / "informe.html"
    resultado = runner.invoke(
        app,
        [
            "audit",
            "--offline",
            str(FIXTURES / "dns_abierto.rsc"),
            "--format",
            "html",
            "-o",
            str(salida),
        ],
    )

    assert resultado.exit_code == 0
    assert salida.exists()
    assert "MUFA-DNS-001" in salida.read_text(encoding="utf-8")
