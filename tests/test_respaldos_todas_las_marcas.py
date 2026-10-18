"""Respaldos de todas las marcas, el horario diario y la copia a un servidor FTP o SFTP."""

from __future__ import annotations

import socket
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paramiko
import pytest
from fastapi.testclient import TestClient
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from mufa import respaldos
from mufa.permisos import Rol
from mufa.ssh import SesionSoloLectura, limpiar_consola
from tests.conftest import CrearUsuario
from tests.ssh_falso import ServidorSSHFalso

API = "/api/v1"
GUATEMALA = timezone(timedelta(hours=-6))
CLAVE_SERVIDOR = paramiko.RSAKey.generate(2048)
HUAWEI = """!Software Version V800R021C10SPC100
!Last configuration was updated at 2026-10-08 11:58:01-06:00
#
sysname CORE-HW
#
interface GigabitEthernet0/0/1
 description UPLINK
#
return
"""


def _equipo(cliente: TestClient, admin: dict[str, str], marca: str, puerto: int) -> int:
    datos = {
        "nombre": f"{marca.upper()} Norte",
        "marca": marca,
        "ip_gestion": "127.0.0.1",
        "puerto_ssh": puerto,
        "usuario_ssh": "mufa",
        "password_ssh": "clave-correcta",
    }
    respuesta = cliente.post(f"{API}/equipos", json=datos, headers=admin)
    assert respuesta.status_code == 201, respuesta.text
    return int(respuesta.json()["id"])


def test_huawei_se_respalda_y_las_fechas_no_cuentan_como_cambio(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    config = {"texto": HUAWEI}
    router = ServidorSSHFalso(
        lambda c: config["texto"] if c == "display current-configuration" else ""
    )
    try:
        equipo_id = _equipo(cliente, admin, "huawei", router.puerto)
        primero = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin)
        assert primero.status_code == 200, primero.text
        assert primero.json()["cambio"] is True

        config["texto"] = HUAWEI.replace("11:58:01", "12:00:07")
        segundo = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).json()
        assert segundo["cambio"] is False

        assert router.comandos == ["display current-configuration"] * 2
    finally:
        router.cerrar()


def test_hpe_prueba_los_comandos_de_cada_sistema_en_orden(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    # Un ArubaOS-CX: no conoce el comando de Comware, sí el de estilo Cisco.
    def responder(comando: str) -> str:
        if comando == "display current-configuration":
            return "% Unrecognized command found at '^' position.\n"
        return "hostname ARUBA-1\nvlan 10\n    name GESTION\n"

    router = ServidorSSHFalso(responder)
    try:
        equipo_id = _equipo(cliente, admin, "hpe", router.puerto)
        respuesta = cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin)
        assert respuesta.status_code == 200, respuesta.text
        respaldo_id = respuesta.json()["respaldo"]["id"]
        contenido = cliente.get(f"{API}/respaldos/{respaldo_id}", headers=admin).json()
        assert "hostname ARUBA-1" in contenido["contenido"]
        assert router.comandos == ["display current-configuration", "show running-config"]
    finally:
        router.cerrar()


def test_marca_sin_soporte_y_sin_usuario_en_el_resumen(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    for datos in (
        {"nombre": "Caja negra", "marca": "otra", "ip_gestion": "10.0.0.9"},
        {"nombre": "Juniper sin usuario", "marca": "juniper", "ip_gestion": "10.0.0.8"},
    ):
        assert cliente.post(f"{API}/equipos", json=datos, headers=admin).status_code == 201
    resumen = cliente.get(f"{API}/respaldos", headers=admin).json()
    estados = {e["nombre"]: e["estado"] for e in resumen["equipos"]}
    assert estados == {"Caja negra": "sin_soporte", "Juniper sin usuario": "sin_acceso"}
    assert resumen["programa"] == {"activo": True, "hora": "12:00", "secretos": True}


# --- Equipos que solo hablan por consola, con paginación ---------------------------


class _ConsolaHuawei(paramiko.ServerInterface):
    """Rechaza los comandos sueltos y pagina con «---- More ----» como un VRP."""

    def __init__(self) -> None:
        self.canal: paramiko.Channel | None = None
        self.listo = threading.Event()

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
        canal.sendall(b"\r\nInfo: The max number of VTY users is 10.\r\n<CORE-HW>")
        recibido = b""
        while b"\n" not in recibido:
            recibido += canal.recv(100)
        # Primero apaga la paginación de esta sesión (no toca la configuración).
        assert recibido.strip() == b"screen-length 0 temporary"
        canal.sendall(
            b"screen-length 0 temporary\r\nInfo: The configuration takes effect on the current user terminal interface only.\r\n<CORE-HW>"
        )
        recibido = b""
        while b"\n" not in recibido:
            recibido += canal.recv(100)
        assert recibido.strip() == b"display current-configuration"
        canal.sendall(b"display current-configuration\r\n#\r\nsysname CORE-HW\r\n")
        canal.sendall(b"  ---- More ----")
        assert canal.recv(1) == b" "  # la única tecla extra: pedir la página siguiente
        canal.sendall(b"\x1b[42D" + b" " * 42 + b"\x1b[42D")
        canal.sendall(b" description UPLINK\r\n#\r\nreturn\r\n<CORE-HW>")
        self.listo.set()


def test_equipo_que_solo_acepta_consola_y_pagina(tmp_path: Path) -> None:
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    puerto = servidor.getsockname()[1]
    consola = _ConsolaHuawei()

    def aceptar() -> None:
        conexion, _ = servidor.accept()
        transporte = paramiko.Transport(conexion)
        transporte.add_server_key(CLAVE_SERVIDOR)
        transporte.start_server(server=consola)

    threading.Thread(target=aceptar, daemon=True).start()
    known_hosts = tmp_path / "known_hosts"
    try:
        with SesionSoloLectura(
            "127.0.0.1", "mufa", "huawei", "x", puerto, 5.0, known_hosts
        ) as sesion:
            texto = sesion.run_readonly("display current-configuration")
        assert consola.listo.is_set()
        assert texto.split("\n") == ["#", "sysname CORE-HW", " description UPLINK", "#", "return"]
    finally:
        servidor.close()


def test_limpiar_consola_quita_pausas_de_cada_marca() -> None:
    cisco = " --More-- \x08\x08\x08\x08\x08\x08\x08\x08\x08\x08          \x08\x08\x08\x08\x08\x08\x08\x08\x08\x08 ip address 10.0.0.1"
    assert limpiar_consola(cisco) == " ip address 10.0.0.1"
    huawei = "  ---- More ----\x1b[42D" + " " * 42 + "\x1b[42D interface Vlanif10"
    assert limpiar_consola(huawei) == " interface Vlanif10"


# --- Horario -------------------------------------------------------------------------


def test_respalda_una_vez_por_dia_despues_de_la_hora(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    sesiones = cliente.app.state.mufa.sesiones  # type: ignore[attr-defined]
    with sesiones() as db:
        antes = datetime(2026, 10, 8, 11, 59, tzinfo=GUATEMALA)
        a_las_doce = datetime(2026, 10, 8, 12, 0, tzinfo=GUATEMALA)
        assert not respaldos.toca_respaldar(db, antes)
        assert respaldos.toca_respaldar(db, a_las_doce)
        assert respaldos.proximo_respaldo(db, antes) == a_las_doce

        respaldos.marcar_respaldado_hoy(db, a_las_doce)
        assert not respaldos.toca_respaldar(db, datetime(2026, 10, 8, 18, 0, tzinfo=GUATEMALA))
        assert respaldos.proximo_respaldo(db, a_las_doce) == datetime(
            2026, 10, 9, 12, 0, tzinfo=GUATEMALA
        )
        # Si la PC estuvo apagada a las 12, respalda apenas arranca.
        assert respaldos.toca_respaldar(db, datetime(2026, 10, 9, 15, 30, tzinfo=GUATEMALA))

    cambio = cliente.put(
        f"{API}/respaldos/programa", json={"activo": True, "hora": "23:30"}, headers=admin
    )
    assert cambio.status_code == 200
    assert cliente.get(f"{API}/respaldos", headers=admin).json()["programa"]["hora"] == "23:30"
    malo = cliente.put(f"{API}/respaldos/programa", json={"hora": "25:00"}, headers=admin)
    assert malo.status_code == 422


# --- Copia a un servidor -------------------------------------------------------------


@pytest.fixture
def servidor_ftp(tmp_path: Path):  # type: ignore[no-untyped-def]
    raiz = tmp_path / "ftp"
    raiz.mkdir()
    autorizador = DummyAuthorizer()
    autorizador.add_user("respaldos", "clave-ftp", str(raiz), perm="elradfmw")
    manejador = type("Manejador", (FTPHandler,), {"authorizer": autorizador})
    servidor = FTPServer(("127.0.0.1", 0), manejador)
    hilo = threading.Thread(target=servidor.serve_forever, kwargs={"timeout": 0.2}, daemon=True)
    hilo.start()
    yield raiz, servidor.address[1]
    servidor.close_all()


def _respaldar_un_mikrotik(cliente: TestClient, admin: dict[str, str]) -> ServidorSSHFalso:
    router = ServidorSSHFalso(
        lambda c: "/system identity\nset name=r1\n" if c.startswith("/export") else ""
    )
    equipo = {
        "nombre": "RT Centro/1",  # la barra no puede crear carpetas en el servidor
        "marca": "mikrotik",
        "ip_gestion": "127.0.0.1",
        "puerto_ssh": router.puerto,
        "usuario_ssh": "mufa",
        "password_ssh": "clave-correcta",
    }
    equipo_id = cliente.post(f"{API}/equipos", json=equipo, headers=admin).json()["id"]
    assert cliente.post(f"{API}/equipos/{equipo_id}/respaldar", headers=admin).status_code == 200
    return router


def test_copia_por_ftp_en_una_carpeta_por_equipo(
    cliente: TestClient, admin: dict[str, str], servidor_ftp: tuple[Path, int]
) -> None:
    raiz, puerto = servidor_ftp
    router = _respaldar_un_mikrotik(cliente, admin)
    try:
        destino = {
            "activo": True,
            "protocolo": "ftp",
            "host": "127.0.0.1",
            "puerto": puerto,
            "usuario": "respaldos",
            "password": "clave-ftp",
            "carpeta": "/mufa/routers",
        }
        prueba = cliente.post(f"{API}/respaldos/destino/probar", json=destino, headers=admin)
        assert prueba.json()["ok"] is True, prueba.json()
        assert (
            cliente.put(f"{API}/respaldos/destino", json=destino, headers=admin).status_code == 200
        )

        # La contraseña no vuelve nunca a la pantalla.
        guardado = cliente.get(f"{API}/respaldos", headers=admin).json()["destino"]
        assert guardado["tiene_password"] is True
        assert "password" not in guardado

        enviado = cliente.post(f"{API}/respaldos/enviar", headers=admin)
        assert enviado.status_code == 200, enviado.text
        assert enviado.json()["archivos"] == 1
        archivos = list((raiz / "mufa" / "routers" / "RT_Centro_1").iterdir())
        assert len(archivos) == 1
        assert archivos[0].suffix == ".rsc"
        assert archivos[0].read_text(encoding="utf-8") == "/system identity\nset name=r1\n"

        resumen = cliente.get(f"{API}/respaldos", headers=admin).json()
        assert resumen["ultimo_envio"]["ok"] is True
    finally:
        router.cerrar()


def test_copia_falla_con_contrasena_mala_y_queda_registrada(
    cliente: TestClient, admin: dict[str, str], servidor_ftp: tuple[Path, int]
) -> None:
    _, puerto = servidor_ftp
    destino = {
        "activo": True,
        "protocolo": "ftp",
        "host": "127.0.0.1",
        "puerto": puerto,
        "usuario": "respaldos",
        "password": "otra",
    }
    prueba = cliente.post(f"{API}/respaldos/destino/probar", json=destino, headers=admin).json()
    assert prueba == {
        "ok": False,
        "mensaje": "el servidor rechazó el usuario o la contraseña",
        "huella": "",
    }
    cliente.put(f"{API}/respaldos/destino", json=destino, headers=admin)
    assert cliente.post(f"{API}/respaldos/enviar", headers=admin).status_code == 502
    eventos = cliente.get(f"{API}/eventos", headers=admin).json()
    assert any(e["accion"] == "respaldo.copia_error" for e in eventos)


def test_destino_validado_y_solo_para_senior(
    cliente: TestClient, admin: dict[str, str], crear_usuario: CrearUsuario
) -> None:
    for malo in ({"host": "ftp://x/y"}, {"host": "10.0.0.5", "carpeta": "/a/../etc"}):
        respuesta = cliente.put(f"{API}/respaldos/destino", json=malo, headers=admin)
        assert respuesta.status_code == 422, malo
    ingeniero = crear_usuario("ing", Rol.INGENIERO_N3)
    assert cliente.put(f"{API}/respaldos/destino", json={}, headers=ingeniero).status_code == 403
    assert cliente.post(f"{API}/respaldos/enviar", headers=ingeniero).status_code == 403
    # El horario sí lo puede cambiar un ingeniero.
    assert cliente.put(f"{API}/respaldos/programa", json={}, headers=ingeniero).status_code == 200


# --- SFTP ------------------------------------------------------------------------------


class _Archivo(paramiko.SFTPHandle):
    def __init__(self, ruta: Path) -> None:
        super().__init__()
        self.writefile = ruta.open("wb")


class _SFTPEnCarpeta(paramiko.SFTPServerInterface):
    raiz: Path

    def _ruta(self, ruta: str) -> Path:
        return self.raiz / ruta.lstrip("/")

    def stat(self, path: str) -> paramiko.SFTPAttributes | int:
        ruta = self._ruta(path)
        if not ruta.exists():
            return paramiko.SFTP_NO_SUCH_FILE
        return paramiko.SFTPAttributes.from_stat(ruta.stat())

    lstat = stat

    def mkdir(self, path: str, attr: paramiko.SFTPAttributes) -> int:
        self._ruta(path).mkdir()
        return paramiko.SFTP_OK

    def open(self, path: str, flags: int, attr: paramiko.SFTPAttributes) -> _Archivo:
        return _Archivo(self._ruta(path))


class _ServidorSFTP(paramiko.ServerInterface):
    def check_auth_password(self, username: str, password: str) -> int:
        ok = username == "copias" and password == "clave-sftp"
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return paramiko.OPEN_SUCCEEDED


def test_copia_por_sftp_en_una_carpeta_por_dia(
    cliente: TestClient, admin: dict[str, str], tmp_path: Path
) -> None:
    raiz = tmp_path / "sftp"
    raiz.mkdir()
    _SFTPEnCarpeta.raiz = raiz
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(5)
    puerto = servidor.getsockname()[1]

    def aceptar() -> None:
        while True:
            try:
                conexion, _ = servidor.accept()
            except OSError:
                return
            transporte = paramiko.Transport(conexion)
            transporte.add_server_key(CLAVE_SERVIDOR)
            transporte.set_subsystem_handler("sftp", paramiko.SFTPServer, _SFTPEnCarpeta)
            transporte.start_server(server=_ServidorSFTP())

    threading.Thread(target=aceptar, daemon=True).start()
    router = _respaldar_un_mikrotik(cliente, admin)
    try:
        destino = {
            "activo": True,
            "protocolo": "sftp",
            "host": "127.0.0.1",
            "puerto": puerto,
            "usuario": "copias",
            "password": "clave-sftp",
            "carpeta": "respaldos",
            "organizar": "por_dia",
        }
        prueba = cliente.post(f"{API}/respaldos/destino/probar", json=destino, headers=admin).json()
        assert prueba["ok"] is True, prueba
        assert prueba["huella"].startswith("SHA256:")
        cliente.put(f"{API}/respaldos/destino", json=destino, headers=admin)
        enviado = cliente.post(f"{API}/respaldos/enviar", headers=admin)
        assert enviado.status_code == 200, enviado.text
        hoy = respaldos.hora_local().strftime("%Y-%m-%d")
        assert (raiz / "respaldos" / hoy / "RT_Centro_1.rsc").read_text() == (
            "/system identity\nset name=r1\n"
        )
    finally:
        servidor.close()
        router.cerrar()
