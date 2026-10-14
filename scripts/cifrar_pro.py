#!/usr/bin/env python3
"""Cifra los módulos de mufa Pro para publicarlos (ver mufa/modulos_pro.py).

Necesita la llave de Pro, que NUNCA va en el repositorio (por defecto
~/.mufa-emisor/pro.key). La misma llave va dentro de cada licencia Pro.

    uv run python scripts/cifrar_pro.py              # escribe src/mufa/pro/modulos.cifrado
    uv run python scripts/cifrar_pro.py --nueva-llave  # solo la primera vez
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from mufa.modulos_pro import cifrar, descifrar

LLAVE_POR_DEFECTO = Path.home() / ".mufa-emisor" / "pro.key"
CARPETA = RAIZ / "src" / "mufa" / "pro"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llave", type=Path, default=LLAVE_POR_DEFECTO)
    parser.add_argument("--carpeta", type=Path, default=CARPETA)
    parser.add_argument("--salida", type=Path, default=CARPETA / "modulos.cifrado")
    parser.add_argument("--nueva-llave", action="store_true")
    args = parser.parse_args(argv)

    if args.nueva_llave:
        if args.llave.exists():
            print(f"Ya existe {args.llave}: no se reemplaza.", file=sys.stderr)
            return 1
        args.llave.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.llave, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as salida:
            salida.write(Fernet.generate_key())
        print(
            f"Llave nueva en {args.llave}. Guárdala: sin ella no se pueden publicar versiones de Pro."
        )
        return 0

    llave = args.llave.read_text(encoding="ascii").strip()
    fuentes = {
        archivo.stem: archivo.read_text(encoding="utf-8")
        for archivo in sorted(args.carpeta.glob("*.py"))
        if archivo.name != "__init__.py"
    }
    if "registro" not in fuentes:
        print("Falta mufa/pro/registro.py", file=sys.stderr)
        return 1
    args.salida.write_bytes(cifrar(fuentes, llave))
    # Comprobar que se abre con la misma llave antes de darlo por bueno.
    assert descifrar(args.salida, llave) == fuentes
    print(f"{len(fuentes)} módulos cifrados en {args.salida}: {', '.join(fuentes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
