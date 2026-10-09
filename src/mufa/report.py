"""Formateador HTML del informe."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from mufa.models import Hallazgo

_DIR_PLANTILLAS = Path(__file__).parent / "templates"


def generar_html(hallazgos: list[Hallazgo], host: str = "") -> str:
    entorno = Environment(
        loader=FileSystemLoader(_DIR_PLANTILLAS),
        autoescape=select_autoescape(["html"]),
    )
    plantilla = entorno.get_template("informe.html.j2")
    return plantilla.render(hallazgos=hallazgos, host=host)
