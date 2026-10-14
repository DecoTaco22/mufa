#!/usr/bin/env python3
"""Arma y firma el manifiesto de una versión (ver mufa/actualizacion.py).

Lo corre .github/workflows/publicar.yml al publicar una versión, con la clave
privada de actualizaciones en la variable MUFA_FIRMA_ACTUALIZACIONES (PEM). La
clave también está en ~/.mufa-emisor/actualizaciones.pem para probarlo a mano:

    uv run python scripts/firmar_actualizacion.py 0.1.5 descargas/ > actualizacion.firmada
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

RAIZ = Path(__file__).resolve().parent.parent
CLAVE_LOCAL = Path.home() / ".mufa-emisor" / "actualizaciones.pem"
REPOSITORIO = "DecoTaco22/mufa"
# Lo que se instala solo desde la app: la clave es la que usa mufa/actualizacion.py.
INSTALADORES = {"windows": "mufa-instalador-windows.exe", "macos": "mufa-macos.dmg"}


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def notas_de(version: str, cambios: str) -> str:
    """La sección «## v<versión>» de CHANGELOG.md."""
    seccion = re.search(
        rf"^## v{re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", cambios, re.MULTILINE | re.DOTALL
    )
    return seccion.group(1).strip() if seccion else ""


def manifiesto(version: str, carpeta: Path, repositorio: str, cambios: str) -> dict[str, object]:
    archivos = {}
    for clave, nombre in INSTALADORES.items():
        archivo = carpeta / nombre
        if not archivo.exists():
            raise FileNotFoundError(archivo)
        archivos[clave] = {
            "nombre": nombre,
            "url": f"https://github.com/{repositorio}/releases/download/v{version}/{nombre}",
            "sha256": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            "tamano": archivo.stat().st_size,
        }
    return {
        "version": version,
        "publicada": datetime.now(UTC).date().isoformat(),
        "notas": notas_de(version, cambios),
        "archivos": archivos,
    }


def firmar(clave: Ed25519PrivateKey, contenido: dict[str, object]) -> str:
    datos = json.dumps(contenido, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"{_b64(datos)}.{_b64(clave.sign(datos))}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("carpeta", type=Path, help="Donde están los instaladores.")
    parser.add_argument("--repositorio", default=os.environ.get("GITHUB_REPOSITORY", REPOSITORIO))
    args = parser.parse_args(argv)

    pem = os.environ.get("MUFA_FIRMA_ACTUALIZACIONES", "").encode()
    if not pem and CLAVE_LOCAL.exists():
        pem = CLAVE_LOCAL.read_bytes()
    if not pem:
        print("Falta la clave de actualizaciones (MUFA_FIRMA_ACTUALIZACIONES).", file=sys.stderr)
        return 1
    clave = load_pem_private_key(pem, password=None)
    if not isinstance(clave, Ed25519PrivateKey):
        print("La clave de actualizaciones no es Ed25519.", file=sys.stderr)
        return 1
    cambios = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    print(firmar(clave, manifiesto(args.version, args.carpeta, args.repositorio, cambios)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
