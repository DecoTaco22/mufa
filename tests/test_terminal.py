"""Terminal hacia los equipos: protocolo Telnet, permisos y una sesión de punta a punta."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import paramiko
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mufa import terminal
from mufa.config import Ajustes
from mufa.permisos import Rol
from tests.conftest import PASSWORD, CrearUsuario

IAC, DO, WILL, SB, SE = 255, 253, 251, 250, 240


def _con_cookie(cliente: TestClient, crear_usuario: CrearUsuario, usuario: str, rol: Rol) -> None:
    crear_usuario(usuario, rol)
    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={"usuario": usuario, "password": PASSWORD},
        headers={"X-Mufa-Cliente": "web"},
    )
    assert respuesta.status_code == 200, respuesta.text


class _ServidorTelnet:
    """Un "router" Telnet mínimo: negocia eco y tamaño, saluda y repite lo que recibe."""

    def __init__(self) -> None:
        self.socket = socket.create_server(("127.0.0.1", 0))
        self.puerto = self.socket.getsockname()[1]
        self.recibido = b""
        self.hilo = threading.Thread(target=self._atender, daemon=True)
        self.hilo.start()

    def _atender(self) -> None:
        try:
            conexion, _ = self.socket.accept()
        except OSError:  # la prueba terminó sin conectarse
            return
        with conexion:
            conexion.sendall(bytes([IAC, WILL, 1, IAC, DO, 31]) + b"RouterOS login: ")
            while datos := conexion.recv(1024):
                self.recibido += datos
                if b"admin\r" in self.recibido:
                    conexion.sendall(b"\r\nhola admin\r\n")
                    return

    def cerrar(self) -> None:
        self.socket.close()


@pytest.fixture
def servidor_telnet() -> Iterator[_ServidorTelnet]:
    servidor = _ServidorTelnet()
    yield servidor
    servidor.cerrar()


def test_telnet_filtra_y_contesta_la_negociacion() -> None:
    conexion = object.__new__(terminal.ConexionTelnet)
    enviados: list[bytes] = []
    conexion._pendiente = b""  # type: ignore[attr-defined]
    conexion._naws = False  # type: ignore[attr-defined]
    conexion._tamano = (100, 30)  # type: ignore[attr-defined]
    conexion._envio = threading.Lock()  # type: ignore[attr-defined]
    conexion._socket = type("S", (), {"sendall": lambda self, b: enviados.append(b)})()  # type: ignore[attr-defined]

    # Una negociación cortada a la mitad se completa con el siguiente pedazo.
    assert conexion.filtrar(b"hola" + bytes([IAC, WILL])) == b"hola"
    assert conexion.filtrar(bytes([1]) + b" mundo" + bytes([IAC, IAC])) == b" mundo\xff"
    assert bytes([IAC, DO, 1]) in enviados  # acepta el eco del equipo

    conexion.filtrar(bytes([IAC, DO, 31]))  # pide el tamaño de la ventana
    assert any(b.startswith(bytes([IAC, SB, 31, 0, 100, 0, 30])) for b in enviados)


def test_sin_sesion_o_desde_otro_sitio_no_abre(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as sin_sesion,
        cliente.websocket_connect("/api/v1/terminal") as ws,
    ):
        ws.receive_text()
    assert sin_sesion.value.code == 4401

    _con_cookie(cliente, crear_usuario, "tecnico1", Rol.TECNICO_N2)
    with (
        pytest.raises(WebSocketDisconnect) as otro_sitio,
        cliente.websocket_connect(
            "/api/v1/terminal", headers={"origin": "https://malo.example"}
        ) as ws,
    ):
        ws.receive_text()
    assert otro_sitio.value.code == 4401


def test_lectura_no_usa_la_terminal(cliente: TestClient, crear_usuario: CrearUsuario) -> None:
    _con_cookie(cliente, crear_usuario, "lector1", Rol.LECTURA)
    with (
        pytest.raises(WebSocketDisconnect) as rechazo,
        cliente.websocket_connect("/api/v1/terminal") as ws,
    ):
        ws.receive_text()
    assert rechazo.value.code == 4401


def test_sesion_telnet_de_punta_a_punta(
    cliente: TestClient, crear_usuario: CrearUsuario, servidor_telnet: _ServidorTelnet
) -> None:
    _con_cookie(cliente, crear_usuario, "ingeniero1", Rol.INGENIERO_N3)
    with cliente.websocket_connect("/api/v1/terminal") as ws:
        ws.send_text(
            json.dumps({"modo": "telnet", "host": "127.0.0.1", "puerto": servidor_telnet.puerto})
        )
        assert json.loads(ws.receive_text())["estado"] == "abierta"
        salida = b""
        while b"login:" not in salida:
            salida += ws.receive_bytes()
        assert bytes([IAC]) not in salida  # la negociación no llega a la pantalla
        ws.send_bytes(b"admin\r")
        while b"hola admin" not in salida:
            salida += ws.receive_bytes()

    eventos = cliente.get("/api/v1/eventos", headers=crear_usuario("admin", Rol.ADMIN)).json()
    acciones = [e["accion"] for e in eventos]
    assert "terminal.abrir" in acciones


def test_destino_invalido_avisa(cliente: TestClient, crear_usuario: CrearUsuario) -> None:
    _con_cookie(cliente, crear_usuario, "ingeniero1", Rol.INGENIERO_N3)
    with cliente.websocket_connect("/api/v1/terminal") as ws:
        ws.send_text(json.dumps({"modo": "ssh", "host": "1.1.1.1; rm -rf /", "usuario": "x"}))
        assert "destino" in json.loads(ws.receive_text())["error"]


def test_otro_usuario_no_usa_la_contrasena_guardada(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    admin = crear_usuario("admin", Rol.ADMIN)
    equipo = cliente.post(
        "/api/v1/equipos",
        json={
            "nombre": "CCR",
            "marca": "mikrotik",
            "ip_gestion": "127.0.0.1",
            "usuario_ssh": "mufa",
            "password_ssh": "la-de-mufa",
            "snmp": None,
        },
        headers=admin,
    ).json()
    _con_cookie(cliente, crear_usuario, "tecnico1", Rol.TECNICO_N2)
    with cliente.websocket_connect("/api/v1/terminal") as ws:
        ws.send_text(json.dumps({"modo": "ssh", "equipo_id": equipo["id"], "usuario": "admin"}))
        assert "escribe la contraseña de admin" in json.loads(ws.receive_text())["error"]
    eventos = cliente.get("/api/v1/eventos", headers=admin).json()
    assert any(e["accion"] == "terminal.fallo" for e in eventos)


class _CiscoFalso(paramiko.ServerInterface):
    """Como un Cisco con AAA: anuncia password pero solo acepta keyboard-interactive."""

    def get_allowed_auths(self, username: str) -> str:
        return "password,keyboard-interactive"

    def check_auth_password(self, username: str, password: str) -> int:
        return paramiko.AUTH_FAILED

    def check_auth_interactive(self, username: str, submethods: str) -> paramiko.InteractiveQuery:
        consulta = paramiko.InteractiveQuery()
        consulta.add_prompt("Password: ", echo=False)
        return consulta

    def check_auth_interactive_response(self, responses: list[str]) -> int:
        return paramiko.AUTH_SUCCESSFUL if responses == ["clave-cisco"] else paramiko.AUTH_FAILED

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return paramiko.OPEN_SUCCEEDED

    def check_channel_pty_request(self, *args: object) -> bool:
        return True

    def check_channel_shell_request(self, channel: paramiko.Channel) -> bool:
        channel.send(b"Router#")
        return True


def _servidor_ssh(clave: paramiko.PKey | None = None, solo_sha1: bool = False) -> int:
    """Un SSH falso en 127.0.0.1. solo_sha1: como un IOS viejo (group14-sha1 y ssh-rsa)."""
    servidor = socket.create_server(("127.0.0.1", 0))
    puerto = servidor.getsockname()[1]
    clave = clave or paramiko.RSAKey.generate(2048)

    def atender() -> None:
        try:
            conexion, _ = servidor.accept()
        except OSError:
            return
        transporte = paramiko.Transport(conexion)
        if solo_sha1:
            opciones = transporte.get_security_options()
            opciones.kex = ("diffie-hellman-group14-sha1",)
            opciones.key_types = ("ssh-rsa",)
        transporte.add_server_key(clave)
        try:
            transporte.start_server(server=_CiscoFalso())
            canal = transporte.accept(10)
            if canal is not None:
                import time

                time.sleep(1)
        except (paramiko.SSHException, EOFError, OSError):
            pass
        transporte.close()
        servidor.close()

    threading.Thread(target=atender, daemon=True).start()
    return puerto


def _dos_conexiones(clave: paramiko.PKey | None = None, solo_sha1: bool = False) -> int:
    """Como _servidor_ssh pero atiende un intento fallido antes (el de algoritmos modernos)."""
    servidor = socket.create_server(("127.0.0.1", 0))
    puerto = servidor.getsockname()[1]
    clave = clave or paramiko.RSAKey.generate(2048)

    def atender() -> None:
        for _ in range(2):
            try:
                conexion, _ = servidor.accept()
            except OSError:
                return
            transporte = paramiko.Transport(conexion)
            if solo_sha1:
                opciones = transporte.get_security_options()
                opciones.kex = ("diffie-hellman-group14-sha1",)
                opciones.key_types = ("ssh-rsa",)
            transporte.add_server_key(clave)
            try:
                transporte.start_server(server=_CiscoFalso())
                canal = transporte.accept(10)
                if canal is not None:
                    import time

                    time.sleep(1)
                    transporte.close()
                    break
            except (paramiko.SSHException, EOFError, OSError):
                pass
            transporte.close()
        servidor.close()

    threading.Thread(target=atender, daemon=True).start()
    return puerto


def test_ssh_entra_con_keyboard_interactive_si_rechaza_password(tmp_path: Path) -> None:
    conexion = terminal.ConexionSSH(
        "127.0.0.1", _servidor_ssh(), "tecnico", "clave-cisco", tmp_path / "known_hosts"
    )
    try:
        assert b"Router#" in conexion.recibir()
    finally:
        conexion.cerrar()
    assert "127.0.0.1" in (tmp_path / "known_hosts").read_text()


def test_ssh_con_clave_mala_explica_que_probo(tmp_path: Path) -> None:
    with pytest.raises(terminal.ErrorDeTerminal) as error:
        terminal.ConexionSSH(
            "127.0.0.1", _servidor_ssh(), "tecnico", "otra", tmp_path / "known_hosts"
        )
    assert "password y keyboard-interactive" in str(error.value)


def test_tecnico_solo_entra_a_equipos_del_inventario(
    cliente: TestClient, crear_usuario: CrearUsuario, servidor_telnet: _ServidorTelnet
) -> None:
    _con_cookie(cliente, crear_usuario, "tecnico1", Rol.TECNICO_N2)
    with cliente.websocket_connect("/api/v1/terminal") as ws:
        ws.send_text(
            json.dumps({"modo": "telnet", "host": "127.0.0.1", "puerto": servidor_telnet.puerto})
        )
        assert (
            "solo puede conectarse a los equipos del inventario"
            in json.loads(ws.receive_text())["error"]
        )


def test_muchos_intentos_fallidos_bloquean_la_terminal(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    _con_cookie(cliente, crear_usuario, "ingeniero1", Rol.INGENIERO_N3)
    for _ in range(5):
        with cliente.websocket_connect("/api/v1/terminal") as ws:
            ws.send_text(json.dumps({"modo": "ssh", "host": "127.0.0.1", "usuario": "x"}))
            assert "contraseña" in json.loads(ws.receive_text())["error"]
    with cliente.websocket_connect("/api/v1/terminal") as ws:
        ws.send_text(json.dumps({"modo": "ssh", "host": "127.0.0.1", "usuario": "x"}))
        assert "espera 15 minutos" in json.loads(ws.receive_text())["error"]


def test_cerrar_la_sesion_corta_la_terminal(
    cliente: TestClient,
    crear_usuario: CrearUsuario,
    servidor_telnet: _ServidorTelnet,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mufa.api import rutas_terminal

    monkeypatch.setattr(rutas_terminal, "REVISAR_SESION_CADA", 0.2)
    _con_cookie(cliente, crear_usuario, "ingeniero1", Rol.INGENIERO_N3)
    with cliente.websocket_connect("/api/v1/terminal") as ws:
        ws.send_text(
            json.dumps({"modo": "telnet", "host": "127.0.0.1", "puerto": servidor_telnet.puerto})
        )
        assert json.loads(ws.receive_text())["estado"] == "abierta"
        cliente.post("/api/v1/auth/logout", headers={"X-Mufa-Csrf": "1"})
        mensaje = ws.receive()
        while "text" not in mensaje or not mensaje["text"]:
            mensaje = ws.receive()
        assert "terminó" in json.loads(mensaje["text"])["error"]


def test_solo_acepta_los_hosts_permitidos(ajustes: Ajustes) -> None:
    import dataclasses

    from mufa.api import crear_app

    app = crear_app(dataclasses.replace(ajustes, hosts_permitidos=("127.0.0.1", "localhost")))
    with TestClient(app, base_url="http://127.0.0.1:8080") as local:
        assert local.get("/api/v1/salud").status_code == 200
    with TestClient(app, base_url="http://atacante.example") as ajeno:
        assert ajeno.get("/api/v1/salud").status_code == 400


def test_equipo_viejo_entra_en_modo_compatible_y_avisa(tmp_path: Path) -> None:
    conexion = terminal.ConexionSSH(
        "127.0.0.1",
        _dos_conexiones(solo_sha1=True),
        "tecnico",
        "clave-cisco",
        tmp_path / "known_hosts",
    )
    try:
        assert conexion.legado is True
        assert b"Router#" in conexion.recibir()
    finally:
        conexion.cerrar()


def test_equipo_moderno_no_usa_sha1(tmp_path: Path) -> None:
    conexion = terminal.ConexionSSH(
        "127.0.0.1", _servidor_ssh(), "tecnico", "clave-cisco", tmp_path / "known_hosts"
    )
    conexion.cerrar()
    assert conexion.legado is False


def test_clave_de_otro_tipo_se_rechaza(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    puerto = _servidor_ssh(clave=paramiko.ECDSAKey.generate())
    terminal.ConexionSSH("127.0.0.1", puerto, "tecnico", "clave-cisco", known_hosts).cerrar()
    # El mismo host:puerto ahora presenta una clave RSA: no es «nueva», es sospechosa.
    linea = known_hosts.read_text().split()[0]
    servidor = _servidor_ssh(clave=paramiko.RSAKey.generate(2048))
    known_hosts.write_text(known_hosts.read_text().replace(linea, f"[127.0.0.1]:{servidor}"))
    with pytest.raises(terminal.ErrorDeTerminal) as error:
        terminal.ConexionSSH("127.0.0.1", servidor, "tecnico", "clave-cisco", known_hosts)
    assert "cambió" in str(error.value)


def test_equipo_nuevo_se_confirma_como_en_putty(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    vistas: list[terminal.Huella] = []

    def responder(decision: str) -> terminal.Confirmar:
        def confirmar(nueva: terminal.Huella, anterior: terminal.Huella | None) -> str:
            vistas.append(nueva)
            assert anterior is None
            return decision

        return confirmar

    with pytest.raises(terminal.ErrorDeTerminal, match="cancelada"):
        terminal.ConexionSSH(
            "127.0.0.1",
            _servidor_ssh(),
            "d",
            "clave-cisco",
            known_hosts,
            confirmar=responder("cancelar"),
        )
    assert vistas[-1].sha256.startswith("SHA256:")

    terminal.ConexionSSH(
        "127.0.0.1",
        _servidor_ssh(),
        "d",
        "clave-cisco",
        known_hosts,
        confirmar=responder("una_vez"),
    ).cerrar()
    assert known_hosts.read_text() == ""  # solo esta vez: no se guarda

    terminal.ConexionSSH(
        "127.0.0.1",
        _servidor_ssh(),
        "d",
        "clave-cisco",
        known_hosts,
        confirmar=responder("guardar"),
    ).cerrar()
    assert "127.0.0.1" in known_hosts.read_text()


def test_clave_cambiada_solo_se_reemplaza_a_proposito(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    clave = paramiko.ECDSAKey.generate()
    puerto = _servidor_ssh(clave=clave)
    terminal.ConexionSSH("127.0.0.1", puerto, "d", "clave-cisco", known_hosts).cerrar()

    def mover(a: int) -> None:
        texto = known_hosts.read_text()
        known_hosts.write_text(texto.replace(texto.split()[0], f"[127.0.0.1]:{a}"))

    otro = _servidor_ssh()
    mover(otro)
    with pytest.raises(terminal.ErrorDeTerminal, match="cambió"):
        terminal.ConexionSSH(
            "127.0.0.1", otro, "d", "clave-cisco", known_hosts, confirmar=lambda n, a: "guardar"
        )
    otro = _servidor_ssh()
    mover(otro)
    terminal.ConexionSSH(
        "127.0.0.1", otro, "d", "clave-cisco", known_hosts, confirmar=lambda n, a: "reemplazar"
    ).cerrar()
    assert "ssh-rsa" in known_hosts.read_text() and "ecdsa" not in known_hosts.read_text()


def test_la_app_confirma_la_clave_por_el_websocket(
    cliente: TestClient, crear_usuario: CrearUsuario
) -> None:
    _con_cookie(cliente, crear_usuario, "ingeniero1", Rol.INGENIERO_N3)
    with cliente.websocket_connect("/api/v1/terminal") as ws:
        ws.send_text(
            json.dumps(
                {
                    "modo": "ssh",
                    "host": "127.0.0.1",
                    "puerto": _servidor_ssh(),
                    "usuario": "tecnico",
                    "password": "clave-cisco",
                }
            )
        )
        pregunta = json.loads(ws.receive_text())["confirmar_clave"]
        assert pregunta["huella"].startswith("SHA256:") and pregunta["anterior"] is None
        ws.send_text(json.dumps({"clave": "guardar"}))
        assert json.loads(ws.receive_text())["estado"] == "abierta"
