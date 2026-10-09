"""Servidor SSH mínimo en 127.0.0.1 para probar la lectura de equipos sin un router real."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable

import paramiko


class _Servidor(paramiko.ServerInterface):
    def __init__(self, responder: Callable[[str], str], comandos: list[str]) -> None:
        self._responder = responder
        self._comandos = comandos

    def check_auth_password(self, username: str, password: str) -> int:
        return paramiko.AUTH_SUCCESSFUL if password == "clave-correcta" else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return paramiko.OPEN_SUCCEEDED

    def check_channel_exec_request(self, channel: paramiko.Channel, command: bytes) -> bool:
        comando = command.decode("utf-8")
        self._comandos.append(comando)
        channel.sendall(self._responder(comando).encode("utf-8"))
        channel.send_exit_status(0)
        threading.Timer(0.1, channel.close).start()
        return True


class ServidorSSHFalso:
    def __init__(self, responder: Callable[[str], str]) -> None:
        self.clave = paramiko.RSAKey.generate(2048)
        self.comandos: list[str] = []
        self._responder = responder
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
            transporte = paramiko.Transport(conexion)
            transporte.add_server_key(self.clave)
            try:
                transporte.start_server(server=_Servidor(self._responder, self.comandos))
            except (paramiko.SSHException, EOFError):
                transporte.close()

    def cerrar(self) -> None:
        self._socket.close()
