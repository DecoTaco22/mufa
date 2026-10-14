#!/usr/bin/env python3
"""Emite una licencia firmada para un cliente de un plan de pago.

Necesita la clave privada del emisor, que NUNCA va en el repositorio
(por defecto ~/.mufa-emisor/emisor_privada.pem). Uso:

    uv run python scripts/emitir_licencia.py --cliente "ISP Ejemplo" \
        --plan pro --max-equipos 200 --vence 2027-10-31 > licencia.txt
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import secrets
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

CARPETA_EMISOR = Path.home() / ".mufa-emisor"
CLAVE_POR_DEFECTO = CARPETA_EMISOR / "emisor_privada.pem"


def numero_de_llave(archivo: Path) -> int:
    """pro.key es la 1; cada rotación suma pro-2.key, pro-3.key..."""
    encontrado = re.fullmatch(r"pro(?:-(\d+))?\.key", archivo.name)
    return int(encontrado.group(1) or 1) if encontrado else 0


def archivos_de_llaves(carpeta: Path) -> list[Path]:
    """Las llaves de Pro de la carpeta del emisor, de la primera a la más nueva."""
    return sorted((a for a in carpeta.glob("pro*.key") if numero_de_llave(a)), key=numero_de_llave)


def llaves_pro(carpeta: Path) -> list[str]:
    return [a.read_text(encoding="ascii").strip() for a in archivos_de_llaves(carpeta)]


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def emitir(
    clave: Ed25519PrivateKey,
    cliente: str,
    plan: str,
    max_equipos: int | None,
    vence: date | None,
    identificador: str | None = None,
    llaves: Sequence[str] = (),
) -> str:
    contenido = {
        # El mismo id en cada mes de una suscripción: así la app encuentra la renovación.
        "id": identificador or secrets.token_hex(8),
        "cliente": cliente,
        "plan": plan,
        "max_equipos": max_equipos,
        "emitida": datetime.now(UTC).date().isoformat(),
        "vence": vence.isoformat() if vence else None,
    }
    if llaves:
        # Abren los módulos Pro cifrados (mufa.modulos_pro). "pro" es la primera
        # (la que leen las versiones 0.1.4 y anteriores); "llaves", las rotadas.
        contenido["pro"] = llaves[0]
        if len(llaves) > 1:
            contenido["llaves"] = list(llaves[1:])
    datos = json.dumps(contenido, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"{_b64(datos)}.{_b64(clave.sign(datos))}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--plan", required=True, choices=["pro", "consultor", "empresa"])
    parser.add_argument(
        "--max-equipos", type=int, default=None, help="Sin indicar: equipos ilimitados."
    )
    parser.add_argument("--vence", type=date.fromisoformat, default=None)
    parser.add_argument("--clave", type=Path, default=CLAVE_POR_DEFECTO)
    parser.add_argument("--id", default=None, help="Para renovar: el id de la licencia anterior.")
    parser.add_argument(
        "--llaves", type=Path, default=CARPETA_EMISOR, help="Carpeta con pro.key, pro-2.key..."
    )
    args = parser.parse_args(argv)

    clave = load_pem_private_key(args.clave.read_bytes(), password=None)
    if not isinstance(clave, Ed25519PrivateKey):
        print("La clave del emisor no es Ed25519.", file=sys.stderr)
        return 1
    llaves = llaves_pro(args.llaves)
    if not llaves:
        print(f"Faltan las llaves de Pro (pro.key en {args.llaves}).", file=sys.stderr)
        return 1
    print(emitir(clave, args.cliente, args.plan, args.max_equipos, args.vence, args.id, llaves))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
