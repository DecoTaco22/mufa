"""Arma la carpeta del paquete MSIX para la Microsoft Store.

    uv run --no-project --with pillow python empaquetado/windows/msix.py 0.1.3
    makeappx pack /d build/msix /p mufa-tienda.msix /o

Usa la app ya compilada (dist/mufa). La identidad del paquete sale de
Partner Center (Producto > Identidad del producto) y llega por variables de
entorno: MSIX_NOMBRE, MSIX_EDITOR (CN=...), MSIX_EDITOR_VISIBLE y
MSIX_NOMBRE_VISIBLE (el nombre reservado). Sin ellas
arma un paquete de prueba que sirve para comprobar que se puede empaquetar.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "build/msix"
LOGOS = {
    "StoreLogo.png": (50, 50),
    "Square44x44Logo.png": (44, 44),
    "Square150x150Logo.png": (150, 150),
    "Wide310x150Logo.png": (310, 150),
}


def _logo(icono: Image.Image, ancho: int, alto: int) -> Image.Image:
    """El ícono centrado, con margen, sobre fondo transparente."""
    lado = round(min(ancho, alto) * 0.8)
    lienzo = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    lienzo.paste(
        icono.resize((lado, lado), Image.Resampling.LANCZOS),
        ((ancho - lado) // 2, (alto - lado) // 2),
    )
    return lienzo


def main() -> None:
    version = sys.argv[1]
    numeros = [int(n) for n in version.split(".")][:3]
    # La tienda exige cuatro números y el último en 0.
    version_msix = ".".join(str(n) for n in [*numeros, 0][:4])
    app = RAIZ / "dist/mufa"
    if not (app / "mufa.exe").exists():
        raise SystemExit("Falta compilar la app: uv run pyinstaller empaquetado/mufa.spec")

    shutil.rmtree(DESTINO, ignore_errors=True)
    shutil.copytree(app, DESTINO / "mufa")
    (DESTINO / "Assets").mkdir()
    icono = Image.open(RAIZ / "empaquetado/mufa.png").convert("RGBA")
    for nombre, (ancho, alto) in LOGOS.items():
        _logo(icono, ancho, alto).save(DESTINO / "Assets" / nombre)

    manifiesto = (RAIZ / "empaquetado/windows/AppxManifest.xml").read_text(encoding="utf-8")
    valores = {
        "{NOMBRE}": os.environ.get("MSIX_NOMBRE") or "mufa.prueba",
        "{EDITOR}": os.environ.get("MSIX_EDITOR") or "CN=mufa-prueba",
        "{EDITOR_VISIBLE}": os.environ.get("MSIX_EDITOR_VISIBLE") or "mufa",
        # Tiene que ser igual al nombre reservado en Partner Center.
        "{NOMBRE_VISIBLE}": os.environ.get("MSIX_NOMBRE_VISIBLE") or "mufa",
        "{VERSION}": version_msix,
    }
    for marca, valor in valores.items():
        manifiesto = manifiesto.replace(marca, escape(valor, {'"': "&quot;"}))
    (DESTINO / "AppxManifest.xml").write_text(manifiesto, encoding="utf-8")
    print(f"{DESTINO} ({valores['{NOMBRE}']} {version_msix})")


if __name__ == "__main__":
    main()
