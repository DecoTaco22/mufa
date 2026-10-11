"""Pruebas del formateador HTML."""

from __future__ import annotations

from mufa.models import Hallazgo, Severidad
from mufa.report import generar_html


def test_generar_html_incluye_los_datos_del_hallazgo() -> None:
    hallazgo = Hallazgo(
        id="MUFA-DNS-001",
        severidad=Severidad.CRITICO,
        titulo="Resolutor DNS abierto a internet",
        evidencia="allow-remote-requests=yes",
        impacto="Riesgo de amplificación DDoS.",
        remediacion=["/ip firewall filter add chain=input protocol=udp dst-port=53"],
        referencia="https://mufa.dev/checks/MUFA-DNS-001",
    )

    html = generar_html([hallazgo], host="10.0.0.1")

    assert "MUFA-DNS-001" in html
    assert "Resolutor DNS abierto a internet" in html
    assert "Riesgo de amplificación DDoS." in html
    assert "10.0.0.1" in html


def test_generar_html_sin_hallazgos() -> None:
    html = generar_html([], host="10.0.0.1")

    assert "No se detectaron hallazgos" in html
