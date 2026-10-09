"""¿El equipo está encendido? Ping y conexión TCP, para cuando SNMP no responde.

Sirve para distinguir "caído" de "encendido pero SNMP mal configurado":
son problemas muy distintos y el técnico tiene que saber cuál es.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from collections.abc import Iterable

from mufa.herramientas import CODIFICACION, SIN_VENTANA


def responde_ping(host: str, timeout: float = 1.5) -> bool:
    ping = shutil.which("ping")
    if ping is None:
        return False
    if sys.platform == "win32":
        comando = [ping, "-n", "1", "-w", str(int(timeout * 1000)), host]
    elif sys.platform == "darwin":
        # En macOS -W va en milisegundos.
        comando = [ping, "-c", "1", "-W", str(int(timeout * 1000)), host]
    else:
        comando = [ping, "-c", "1", "-W", str(max(1, round(timeout))), host]
    try:
        resultado = subprocess.run(  # host es una IP validada, sin shell
            comando,
            capture_output=True,
            text=True,
            encoding=CODIFICACION,
            errors="replace",
            timeout=timeout + 2,
            check=False,
            creationflags=SIN_VENTANA,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    # Windows devuelve 0 también con "host de destino inaccesible": solo
    # cuenta como respuesta si llegó un eco (las respuestas traen TTL).
    return resultado.returncode == 0 and "ttl=" in resultado.stdout.lower()


def responde_tcp(host: str, puerto: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, puerto), timeout=timeout):
            return True
    except OSError:
        return False


def verificar(host: str, puertos: Iterable[int] = ()) -> str:
    """Cómo respondió el equipo ("ping" o "TCP 8728"), o "" si no respondió a nada."""
    if responde_ping(host):
        return "ping"
    for puerto in puertos:
        if responde_tcp(host, puerto):
            return f"TCP {puerto}"
    return ""
