"""Cifrado de secretos guardados en la base de datos (credenciales de equipos).

La clave vive en un archivo del directorio de datos, fuera de la base de
datos: un respaldo o una copia filtrada de la base sola no alcanza para
leer las contraseñas de los equipos.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class ErrorDeCifrado(Exception):
    pass


def cargar_o_crear_clave(archivo: Path) -> bytes:
    if archivo.exists():
        return archivo.read_bytes().strip()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    clave = Fernet.generate_key()
    # O_EXCL: si dos procesos arrancan a la vez, solo uno crea la clave.
    descriptor = os.open(archivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as salida:
        salida.write(clave)
    return clave


class Cifrador:
    def __init__(self, clave: bytes) -> None:
        self._fernet = Fernet(clave)

    def cifrar(self, texto: str) -> str:
        return self._fernet.encrypt(texto.encode("utf-8")).decode("ascii")

    def descifrar(self, cifrado: str) -> str:
        try:
            return self._fernet.decrypt(cifrado.encode("ascii")).decode("utf-8")
        except InvalidToken:
            raise ErrorDeCifrado(
                "no se pudo descifrar: la clave del servidor no coincide con la que cifró el dato"
            ) from None
