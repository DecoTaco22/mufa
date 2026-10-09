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
import secrets
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

CLAVE_POR_DEFECTO = Path.home() / ".mufa-emisor" / "emisor_privada.pem"


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def emitir(
    clave: Ed25519PrivateKey,
    cliente: str,
    plan: str,
    max_equipos: int | None,
    vence: date | None,
) -> str:
    contenido = {
        "id": secrets.token_hex(8),
        "cliente": cliente,
        "plan": plan,
        "max_equipos": max_equipos,
        "emitida": datetime.now(UTC).date().isoformat(),
        "vence": vence.isoformat() if vence else None,
    }
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
    args = parser.parse_args(argv)

    clave = load_pem_private_key(args.clave.read_bytes(), password=None)
    if not isinstance(clave, Ed25519PrivateKey):
        print("La clave del emisor no es Ed25519.", file=sys.stderr)
        return 1
    print(emitir(clave, args.cliente, args.plan, args.max_equipos, args.vence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
