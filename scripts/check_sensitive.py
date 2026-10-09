#!/usr/bin/env python3
"""Bloquea commits con IPs públicas, ASNs o palabras marcadas como sensibles.

Se ejecuta como hook de pre-commit sobre los archivos en stage. Para agregar
nombres de nodo u otras palabras propias del empleador, creá un archivo local
`.mufa-sensitive` (una palabra o fragmento por línea). Ese archivo nunca se
versiona: está en .gitignore a propósito.

Si una línea necesita legítimamente una IP o ASN público (datos de prueba,
ejemplos en documentación), agregá el comentario `mufa: permitir` en esa
misma línea para que el hook la ignore. Es una decisión explícita de quien
escribe el código, no una lista global de excepciones que crece para siempre.
"""

from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path

# Exactamente cuatro números: un OID de SNMP (1.3.6.1.2.1.1.1.0) también
# tiene tramos de "a.b.c.d" y no es una IP.
IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?!\d|\.\d)")
ASN_RE = re.compile(r"\bAS\d{2,10}\b", re.IGNORECASE)

WORDLIST_FILE = Path(".mufa-sensitive")
MARCADOR_PERMITIR = "mufa: permitir"

# Resolutores DNS públicos y conocidos: no son infraestructura de nadie en
# particular, aparecen en cualquier tutorial de redes y hacen falta en los
# fixtures de prueba (ej. MUFA-DNS-001). No son el dato que esta regla
# busca proteger.
IPS_PUBLICAS_PERMITIDAS = {
    "8.8.8.8",
    "8.8.4.4",  # Google Public DNS
    "1.1.1.1",
    "1.0.0.1",  # Cloudflare
    "9.9.9.9",  # Quad9
    "208.67.222.222",
    "208.67.220.220",  # OpenDNS
}


# Espacio compartido de CGNAT (RFC 6598). Python no lo considera privado,
# pero no es enrutable en internet y los ISP chicos lo usan para clientes.
CGNAT = ipaddress.ip_network("100.64.0.0/10")


def es_ip_publica(ip: str) -> bool:
    if ip in IPS_PUBLICAS_PERMITIDAS:
        return False
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        direccion in CGNAT
        or direccion.is_private
        or direccion.is_loopback
        or direccion.is_link_local
        or direccion.is_multicast
        or direccion.is_reserved
        or direccion.is_unspecified
    )


def cargar_palabras_sensibles() -> list[str]:
    if not WORDLIST_FILE.exists():
        return []
    palabras = []
    for linea in WORDLIST_FILE.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            palabras.append(linea)
    return palabras


def revisar_archivo(ruta: Path, palabras_sensibles: list[str]) -> list[str]:
    problemas = []
    try:
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return problemas

    for numero, linea in enumerate(texto.splitlines(), start=1):
        if MARCADOR_PERMITIR in linea:
            continue
        for ip in IP_RE.findall(linea):
            if es_ip_publica(ip):
                problemas.append(f"{ruta}:{numero}: IP pública detectada ({ip})")
        for asn in ASN_RE.findall(linea):
            problemas.append(f"{ruta}:{numero}: ASN detectado ({asn})")
        for palabra in palabras_sensibles:
            if palabra.lower() in linea.lower():
                problemas.append(f"{ruta}:{numero}: palabra sensible detectada ({palabra})")

    return problemas


def main(argv: list[str]) -> int:
    palabras_sensibles = cargar_palabras_sensibles()
    problemas: list[str] = []

    for nombre in argv:
        ruta = Path(nombre)
        if ruta.is_file():
            problemas.extend(revisar_archivo(ruta, palabras_sensibles))

    if problemas:
        print("Commit bloqueado: datos sensibles detectados.\n")
        for problema in problemas:
            print(f"  - {problema}")
        print("\nSi es un falso positivo, revisá scripts/check_sensitive.py.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
