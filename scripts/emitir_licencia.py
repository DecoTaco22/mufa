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
LLAVE_PRO_POR_DEFECTO = Path.home() / ".mufa-emisor" / "pro.key"


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def emitir(
    clave: Ed25519PrivateKey,
    cliente: str,
    plan: str,
    max_equipos: int | None,
    vence: date | None,
    identificador: str | None = None,
    llave_pro: str | None = None,
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
    if llave_pro:
        # Abre los módulos Pro cifrados (mufa.modulos_pro).
        contenido["pro"] = llave_pro
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
    parser.add_argument("--llave-pro", type=Path, default=LLAVE_PRO_POR_DEFECTO)
    args = parser.parse_args(argv)

    clave = load_pem_private_key(args.clave.read_bytes(), password=None)
    if not isinstance(clave, Ed25519PrivateKey):
        print("La clave del emisor no es Ed25519.", file=sys.stderr)
        return 1
    if not args.llave_pro.exists():
        print(f"Falta la llave de Pro ({args.llave_pro}).", file=sys.stderr)
        return 1
    llave_pro = args.llave_pro.read_text(encoding="ascii").strip()
    print(emitir(clave, args.cliente, args.plan, args.max_equipos, args.vence, args.id, llave_pro))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
