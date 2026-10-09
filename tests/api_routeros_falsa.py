"""Servidor mínimo de la API de RouterOS en 127.0.0.1, para probar la lectura sin un router.

Habla el protocolo de verdad (palabras con largo, oraciones, !re/!done/!trap)
y guarda cada comando recibido, para verificar que mufa solo consulta.
"""

from __future__ import annotations

import socket
import threading

from mufa.routeros_api import codificar_oracion

PASSWORD = "clave-correcta"

# Lo que devuelve cada print, como lo manda RouterOS 7 (booleanos true/false,
# contadores y .id incluidos).
MENUS: dict[str, list[dict[str, str]]] = {
    "/ip/dns/print": [{"allow-remote-requests": "true", "servers": "1.1.1.1", "cache-used": "40"}],
    "/ip/firewall/filter/print": [
        {
            ".id": "*1",
            "chain": "input",
            "action": "accept",
            "connection-state": "established,related",
            "bytes": "123456",
            "packets": "789",
            "invalid": "false",
            "dynamic": "false",
            "disabled": "false",
        },
        {".id": "*2", "chain": "forward", "action": "fasttrack-connection", "dynamic": "true"},
    ],
    "/ip/service/print": [
        {".id": "*1", "name": "telnet", "port": "23", "disabled": "false", "address": ""},
        {".id": "*2", "name": "api", "port": "8728", "disabled": "false", "address": ""},
        {".id": "*3", "name": "ssh", "port": "22", "disabled": "true", "address": ""},
    ],
    "/snmp/print": [{"enabled": "true", "contact": "soporte de prueba"}],
    "/snmp/community/print": [
        {
            ".id": "*0",
            "name": "public",
            "default": "true",
            "security": "none",
            "disabled": "false",
            "authentication-password": "no-debe-aparecer",
        }
    ],
    "/system/identity/print": [{"name": "router-de-prueba"}],
}


def _codificar_largo_leido(datos: bytes) -> tuple[int, int]:
    primero = datos[0]
    if primero < 0x80:
        return primero, 1
    if primero < 0xC0:
        return ((primero & 0x3F) << 8) | datos[1], 2
    raise ValueError("largo no esperado en el servidor de prueba")


class ApiRouterOSFalsa:
    def __init__(self, menus: dict[str, list[dict[str, str]]] | None = None) -> None:
        self.menus = MENUS if menus is None else menus
        self.comandos: list[str] = []
        self._socket = socket.socket()
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(5)
        self.puerto: int = self._socket.getsockname()[1]
        threading.Thread(target=self._aceptar, daemon=True).start()

    def _aceptar(self) -> None:
        while True:
            try:
                conexion, _ = self._socket.accept()
            except OSError:
                return
            threading.Thread(target=self._atender, args=(conexion,), daemon=True).start()

    def _leer_oracion(self, conexion: socket.socket, pendiente: bytearray) -> list[str] | None:
        palabras = []
        while True:
            while not pendiente or (pendiente[0] >= 0x80 and len(pendiente) < 2):
                bloque = conexion.recv(4096)
                if not bloque:
                    return None
                pendiente += bloque
            largo, usados = _codificar_largo_leido(bytes(pendiente))
            if largo == 0:
                del pendiente[:1]
                return palabras
            while len(pendiente) < usados + largo:
                bloque = conexion.recv(4096)
                if not bloque:
                    return None
                pendiente += bloque
            palabras.append(bytes(pendiente[usados : usados + largo]).decode("utf-8"))
            del pendiente[: usados + largo]

    def _atender(self, conexion: socket.socket) -> None:
        pendiente = bytearray()
        with conexion:
            while (oracion := self._leer_oracion(conexion, pendiente)) is not None:
                comando, *atributos = oracion
                self.comandos.append(comando)
                conexion.sendall(self._responder(comando, atributos))

    def _responder(self, comando: str, atributos: list[str]) -> bytes:
        if comando == "/login":
            if f"=password={PASSWORD}" in atributos:
                return codificar_oracion(["!done"])
            return codificar_oracion(
                ["!trap", "=message=invalid user name or password (6)"]
            ) + codificar_oracion(["!done"])
        if comando in self.menus:
            salida = b"".join(
                codificar_oracion(["!re", *(f"={k}={v}" for k, v in objeto.items())])
                for objeto in self.menus[comando]
            )
            return salida + codificar_oracion(["!done"])
        return codificar_oracion(["!trap", "=message=no such command"]) + codificar_oracion(
            ["!done"]
        )

    def cerrar(self) -> None:
        self._socket.close()
