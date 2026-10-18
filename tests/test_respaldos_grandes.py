"""Respaldos de configuraciones grandes y lentas: completos, o un error claro (nunca cortados)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

import paramiko
import pytest

from mufa import marcas, ssh
from mufa.marcas.mikrotik import MikroTik
from mufa.ssh import SesionSoloLectura
from tests.ssh_falso import ServidorSSHFalso

CLAVE = paramiko.RSAKey.generate(2048)


class _Equipo(paramiko.ServerInterface):
    """Responde cada comando en un hilo aparte (como un equipo real): puede tardar y mandar mucho."""

    def __init__(self, responder: Callable[[str], str], demora: float, comandos: list[str]) -> None:
        self._responder = responder
        self._demora = demora
        self.comandos = comandos

    def check_auth_password(self, username: str, password: str) -> int:
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return paramiko.OPEN_SUCCEEDED

    def check_channel_exec_request(self, channel: paramiko.Channel, command: bytes) -> bool:
        comando = command.decode()
        self.comandos.append(comando)

        def responder() -> None:
            time.sleep(self._demora)
            try:
                channel.sendall(self._responder(comando).encode())
                channel.send_exit_status(0)
                channel.close()
            except (OSError, EOFError):
                pass

        threading.Thread(target=responder, daemon=True).start()
        return True


def _servidor(
    responder: Callable[[str], str], demora: float = 0.0
) -> tuple[int, list[str], socket.socket]:
    escucha = socket.socket()
    escucha.bind(("127.0.0.1", 0))
    escucha.listen(5)
    comandos: list[str] = []

    def aceptar() -> None:
        while True:
            try:
                conexion, _ = escucha.accept()
            except OSError:
                return
            transporte = paramiko.Transport(conexion)
            transporte.add_server_key(CLAVE)
            transporte.start_server(server=_Equipo(responder, demora, comandos))

    threading.Thread(target=aceptar, daemon=True).start()
    return escucha.getsockname()[1], comandos, escucha


def _bgp(lineas: int) -> str:
    """Un export de MikroTik con muchísimo BGP (filtros y listas de prefijos)."""
    cuerpo = "\n".join(
        f'add chain=bgp-in rule="if (dst in 10.{i // 65536 % 256}.{i // 256 % 256}.{i % 256}/32) '
        f'{{ set bgp-local-pref 200; accept }}"'
        for i in range(lineas)
    )
    return f"# 2026-10-18 by RouterOS 7.16\n/routing filter rule\n{cuerpo}\n"


def test_una_configuracion_enorme_llega_entera(tmp_path: Path) -> None:
    export = _bgp(120_000)  # unos 12 MB
    puerto, comandos, escucha = _servidor(lambda c: export if c.startswith("/export") else "")
    try:
        with SesionSoloLectura(
            "127.0.0.1", "mufa", "mikrotik", "x", puerto, 5.0, tmp_path / "kh", timeout_lectura=60
        ) as sesion:
            texto = MikroTik().leer_respaldo_con_secretos(sesion)
    finally:
        escucha.close()
    assert texto == export
    assert comandos == ["/export show-sensitive"]


def test_un_equipo_que_tarda_en_empezar_se_espera(tmp_path: Path) -> None:
    # 3 segundos callado antes de mandar el export: con el tiempo corto de antes fallaba.
    puerto, _, escucha = _servidor(lambda c: "/system identity\nset name=r1\n", demora=3.0)
    try:
        with SesionSoloLectura(
            "127.0.0.1", "mufa", "mikrotik", "x", puerto, 2.0, tmp_path / "kh", timeout_lectura=10
        ) as sesion:
            assert "set name=r1" in sesion.run_readonly("/export")
    finally:
        escucha.close()


def test_si_tarda_demasiado_el_error_lo_dice_claro(tmp_path: Path) -> None:
    puerto, _, escucha = _servidor(lambda c: "tarde", demora=5.0)
    try:
        with (
            SesionSoloLectura(
                "127.0.0.1",
                "mufa",
                "mikrotik",
                "x",
                puerto,
                2.0,
                tmp_path / "kh",
                timeout_lectura=1,
            ) as sesion,
            pytest.raises(RuntimeError, match="no terminó de mandar la respuesta"),
        ):
            sesion.run_readonly("/export")
    finally:
        escucha.close()


def test_routeros_6_usa_el_export_normal(tmp_path: Path) -> None:
    def ros6(comando: str) -> str:
        if comando == "/export show-sensitive":
            return "expected end of command (line 1 column 9)\n"
        return "# oct/18/2026 by RouterOS 6.49\n/ppp secret\nadd name=cliente password=x\n"

    router = ServidorSSHFalso(ros6)
    try:
        with SesionSoloLectura(
            "127.0.0.1", "mufa", "mikrotik", "clave-correcta", router.puerto, 5.0, tmp_path / "kh"
        ) as sesion:
            texto = MikroTik().leer_respaldo_con_secretos(sesion)
    finally:
        router.cerrar()
    assert "add name=cliente password=x" in texto
    assert router.comandos == ["/export show-sensitive", "/export"]


def test_como_termina_una_configuracion_completa() -> None:
    assert marcas.falta_en_respaldo("cisco", "hostname r1\n!\nend\n") is None
    assert marcas.falta_en_respaldo("cisco", "hostname r1\nrouter bgp 65000\n neighbor") == (
        "falta el «end» del final"
    )
    assert marcas.falta_en_respaldo("huawei", "#\nsysname CORE\n#\nreturn\n") is None
    assert marcas.falta_en_respaldo("huawei", "#\nsysname CORE\nbgp 65000\n") is not None
    assert marcas.falta_en_respaldo("juniper", "system {\n host-name r1;\n}\n") is None
    assert marcas.falta_en_respaldo("juniper", "system {\n host-name r1;\n") is not None
    # MikroTik y el resto no tienen un final fijo: no se rechazan.
    assert marcas.falta_en_respaldo("mikrotik", "/system identity\nset name=r1") is None


class _ConsolaQueSeCorta(paramiko.ServerInterface):
    """Un VRP que manda media configuración y se queda callado (se cayó el enlace)."""

    def check_auth_password(self, username: str, password: str) -> int:
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return paramiko.OPEN_SUCCEEDED

    def check_channel_exec_request(self, channel: paramiko.Channel, command: bytes) -> bool:
        return False

    def check_channel_pty_request(self, *args: object) -> bool:
        return True

    def check_channel_shell_request(self, channel: paramiko.Channel) -> bool:
        threading.Thread(target=self._consola, args=(channel,), daemon=True).start()
        return True

    def _consola(self, canal: paramiko.Channel) -> None:
        canal.sendall(b"<CORE-HW>")
        for respuesta in (
            b"\r\n<CORE-HW>",
            b"\r\n#\r\nsysname CORE-HW\r\nbgp 65000\r\n peer 10.0.0.1",
        ):
            recibido = b""
            while b"\n" not in recibido:
                recibido += canal.recv(100)
            canal.sendall(respuesta)
        time.sleep(30)


def test_por_consola_una_respuesta_cortada_es_un_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ssh, "_SIN_RESPUESTA", 1.0)
    escucha = socket.socket()
    escucha.bind(("127.0.0.1", 0))
    escucha.listen(1)

    def aceptar() -> None:
        conexion, _ = escucha.accept()
        transporte = paramiko.Transport(conexion)
        transporte.add_server_key(CLAVE)
        transporte.start_server(server=_ConsolaQueSeCorta())

    threading.Thread(target=aceptar, daemon=True).start()
    try:
        with (
            SesionSoloLectura(
                "127.0.0.1",
                "mufa",
                "huawei",
                "x",
                escucha.getsockname()[1],
                5.0,
                tmp_path / "kh",
                timeout_lectura=2,
            ) as sesion,
            pytest.raises(RuntimeError, match="llegó incompleta"),
        ):
            sesion.run_readonly("display current-configuration")
    finally:
        escucha.close()


def test_un_respaldo_cortado_no_reemplaza_al_bueno(cliente, admin) -> None:  # type: ignore[no-untyped-def]
    config = {
        "texto": "hostname CORE\nrouter bgp 65000\n neighbor 10.0.0.1 remote-as 65001\n!\nend\n"
    }
    router = ServidorSSHFalso(lambda c: config["texto"] if c == "show running-config" else "")
    try:
        equipo = cliente.post(
            "/api/v1/equipos",
            json={
                "nombre": "CORE",
                "marca": "cisco",
                "ip_gestion": "127.0.0.1",
                "puerto_ssh": router.puerto,
                "usuario_ssh": "mufa",
                "password_ssh": "clave-correcta",
            },
            headers=admin,
        ).json()["id"]
        bueno = cliente.post(f"/api/v1/equipos/{equipo}/respaldar", headers=admin)
        assert bueno.status_code == 200, bueno.text

        config["texto"] = "hostname CORE\nrouter bgp 65000\n neighbor 10.0.0.1 remote-as 650"
        cortado = cliente.post(f"/api/v1/equipos/{equipo}/respaldar", headers=admin)
        assert cortado.status_code == 502
        assert "llegó incompleta" in cortado.json()["detail"]
        versiones = cliente.get(f"/api/v1/equipos/{equipo}/respaldos", headers=admin).json()
        assert len(versiones) == 1
    finally:
        router.cerrar()
