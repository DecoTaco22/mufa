#!/usr/bin/env python3
"""Cifra los módulos de mufa Pro para publicarlos (ver mufa/modulos_pro.py).

Necesita las llaves de Pro, que NUNCA van en el repositorio (en
~/.mufa-emisor: pro.key y, si se rotó, pro-2.key, pro-3.key...). Cifra con
la más nueva. Todas van dentro de cada licencia Pro.

    uv run python scripts/cifrar_pro.py                # escribe src/mufa/pro/modulos.cifrado
    uv run python scripts/cifrar_pro.py --nueva-llave  # solo la primera vez
    uv run python scripts/cifrar_pro.py --rotar        # llave nueva para la próxima versión

Al rotar, ANTES de publicar la versión: sumar la llave nueva a PRO_LLAVES en
Cloudflare y desplegar el sitio (ver docs/SITIO.md). Así las licencias que
emite o renueva el sitio ya la traen cuando sale la versión.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet
from emitir_licencia import CARPETA_EMISOR, archivos_de_llaves, numero_de_llave

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from mufa.modulos_pro import cifrar, descifrar

CARPETA = RAIZ / "src" / "mufa" / "pro"


def _crear_llave(archivo: Path) -> None:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(archivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as salida:
        salida.write(Fernet.generate_key())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llaves", type=Path, default=CARPETA_EMISOR)
    parser.add_argument("--carpeta", type=Path, default=CARPETA)
    parser.add_argument("--salida", type=Path, default=CARPETA / "modulos.cifrado")
    accion = parser.add_mutually_exclusive_group()
    accion.add_argument("--nueva-llave", action="store_true")
    accion.add_argument("--rotar", action="store_true")
    args = parser.parse_args(argv)

    archivos = archivos_de_llaves(args.llaves)
    if args.nueva_llave:
        if archivos:
            print(f"Ya hay llaves en {args.llaves}: para cambiarla usa --rotar.", file=sys.stderr)
            return 1
        _crear_llave(args.llaves / "pro.key")
        print(f"Llave nueva en {args.llaves / 'pro.key'}. Guárdala (respaldar_emisor.py).")
        return 0
    if args.rotar:
        if not archivos:
            print("Todavía no hay llave: usa --nueva-llave.", file=sys.stderr)
            return 1
        nueva = args.llaves / f"pro-{numero_de_llave(archivos[-1]) + 1}.key"
        _crear_llave(nueva)
        print(
            f"Llave nueva en {nueva}. Antes de publicar la versión:\n"
            "  1. Súmala al final de PRO_LLAVES en Cloudflare (ver docs/SITIO.md).\n"
            "  2. Despliega el sitio.\n"
            "  3. Respalda la carpeta del emisor (respaldar_emisor.py).\n"
            "Después vuelve a correr este script sin opciones para cifrar con ella."
        )
        return 0

    if not archivos:
        print(f"No hay llaves de Pro en {args.llaves}.", file=sys.stderr)
        return 1
    llave = archivos[-1].read_text(encoding="ascii").strip()
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
    print(
        f"{len(fuentes)} módulos cifrados con {archivos[-1].name} en {args.salida}: "
        f"{', '.join(fuentes)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
