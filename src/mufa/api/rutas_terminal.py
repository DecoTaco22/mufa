"""Terminal hacia los equipos (SSH, Telnet, serie) por WebSocket.

Protocolo, después de conectar a /api/v1/terminal:
  1. La app manda un texto JSON {"modo": "ssh"|"telnet"|"serial", ...} para abrir.
  2. mufa contesta {"estado": "abierta", "titulo": ...} o {"error": ...} y cierra.
  3. Mensajes binarios: teclas (app → mufa) y salida (mufa → app).
     Texto JSON {"columnas": n, "filas": n}: la ventana cambió de tamaño.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import MutableMapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError, field_validator

from mufa import herramientas, terminal
from mufa.api.deps import COOKIE_SESION, EstadoApp, falta_dos_pasos, requiere
from mufa.auth import usuario_de_token
from mufa.cifrado import ErrorDeCifrado
from mufa.db import Equipo, Usuario
from mufa.permisos import Permiso, tiene_permiso
from mufa.servicios import registrar

router = APIRouter(tags=["terminal"])

Tecnico = Annotated[Usuario, Depends(requiere(Permiso.USAR_CREDENCIALES))]

REVISAR_SESION_CADA = 60.0
# Cuánto se espera a que la persona confirme la clave de un equipo nuevo.
CONFIRMAR_EN = 120.0
# Una sesión olvidada abierta se cierra sola.
INACTIVIDAD_MAXIMA = 30 * 60


class Apertura(BaseModel):
    modo: str = Field(pattern="^(ssh|telnet|serial)$")
    # Un equipo guardado (usa su IP y sus credenciales) o un destino a mano.
    equipo_id: int | None = None
    host: str = Field(default="", max_length=253)
    puerto: int | None = Field(default=None, ge=1, le=65535)
    usuario: str = Field(default="", max_length=128)
    password: str | None = Field(default=None, max_length=512)
    columnas: int = 120
    filas: int = 32

    # Serie
    @field_validator("columnas")
    @classmethod
    def _columnas(cls, valor: int) -> int:
        # Una ventana todavía sin tamaño manda 0 o 2: se ajusta, no se rechaza.
        return min(max(valor, 40), 500)

    @field_validator("filas")
    @classmethod
    def _filas(cls, valor: int) -> int:
        return min(max(valor, 10), 200)

    puerto_serie: str = Field(default="", max_length=64)
    baudios: int = Field(default=115200, ge=300, le=4_000_000)
    bits: int = Field(default=8, ge=5, le=8)
    paridad: str = Field(default="N", pattern="^[NEO]$")
    parada: int = Field(default=1, ge=1, le=2)


@router.get("/terminal/puertos-serie")
def listar_puertos_serie(_: Tecnico) -> list[dict[str, str]]:
    """Puertos serie de la computadora donde corre mufa (cables USB-serial)."""
    return terminal.puertos_serie()


def _autenticar(ws: WebSocket, estado: EstadoApp) -> Usuario | None:
    # Un WebSocket no lleva la cabecera anti-CSRF: se exige que venga de la propia app.
    origen = ws.headers.get("origin")
    if origen is not None and origen.split("://", 1)[-1] != ws.headers.get("host"):
        return None
    token = ws.cookies.get(COOKIE_SESION)
    if not token:
        return None
    with estado.sesiones() as db:
        usuario = usuario_de_token(db, token)
        if usuario is None or falta_dos_pasos(usuario, estado):
            return None
        if not tiene_permiso(usuario.rol, Permiso.USAR_CREDENCIALES):
            return None
        db.expunge(usuario)
        return usuario


def _abrir(
    apertura: Apertura,
    estado: EstadoApp,
    destino_libre: bool,
    confirmar: terminal.Confirmar | None = None,
) -> tuple[terminal.Conexion, str]:
    """La conexión y un título para la pestaña. Bloquea: corre en un hilo."""
    conexion: terminal.Conexion
    if apertura.modo != "serial" and apertura.equipo_id is None and not destino_libre:
        # Un técnico entra a los equipos del inventario; ir a cualquier IP desde el
        # servidor de mufa es de quien administra la red (Ingeniero N3 en adelante).
        raise terminal.ErrorDeTerminal(
            "tu rol solo puede conectarse a los equipos del inventario: elige uno de la lista"
        )
    if apertura.modo == "serial":
        conexion = terminal.ConexionSerial(
            apertura.puerto_serie,
            apertura.baudios,
            apertura.bits,
            apertura.paridad,
            apertura.parada,
        )
        return conexion, f"{apertura.puerto_serie} · {apertura.baudios}"

    host, usuario, password, puerto_guardado = (
        apertura.host,
        apertura.usuario,
        apertura.password,
        None,
    )
    titulo = ""
    if apertura.equipo_id is not None:
        with estado.sesiones() as db:
            equipo = db.get(Equipo, apertura.equipo_id)
            if equipo is None:
                raise terminal.ErrorDeTerminal("el equipo no existe")
            host, titulo = equipo.ip_gestion, equipo.nombre
            # La contraseña guardada es la de SU usuario: con otro usuario hay que escribirla.
            mismo_usuario = not usuario or usuario == equipo.usuario_ssh
            usuario = usuario or equipo.usuario_ssh
            if password is None and mismo_usuario and equipo.password_cifrada:
                try:
                    password = estado.cifrador.descifrar(equipo.password_cifrada)
                except ErrorDeCifrado:
                    raise terminal.ErrorDeTerminal(
                        "no se pudo leer la contraseña guardada"
                    ) from None
            if equipo.acceso == "ssh":
                puerto_guardado = equipo.puerto_ssh
    try:
        host = herramientas.validar_destino(host)
    except herramientas.DestinoInvalido as error:
        raise terminal.ErrorDeTerminal(str(error)) from None
    titulo = titulo or host

    if apertura.modo == "telnet":
        puerto = apertura.puerto or 23
        return terminal.ConexionTelnet(host, puerto, apertura.columnas, apertura.filas), titulo
    if not usuario:
        raise terminal.ErrorDeTerminal("falta el usuario de SSH")
    if not password:
        raise terminal.ErrorDeTerminal(f"escribe la contraseña de {usuario}")
    puerto = apertura.puerto or puerto_guardado or 22
    conexion = terminal.ConexionSSH(
        host,
        puerto,
        usuario,
        password,
        estado.ajustes.known_hosts,
        apertura.columnas,
        apertura.filas,
        confirmar=confirmar,
    )
    return conexion, f"{usuario}@{titulo}"


@router.websocket("/terminal")
async def sesion_de_terminal(ws: WebSocket) -> None:
    estado: EstadoApp = ws.app.state.mufa
    usuario = _autenticar(ws, estado)
    if usuario is None:
        await ws.close(code=4401, reason="sesión inválida o sin permiso")
        return
    await ws.accept()
    try:
        apertura = Apertura.model_validate_json(await asyncio.wait_for(ws.receive_text(), 30))
    except (TimeoutError, ValidationError, WebSocketDisconnect, KeyError):
        await ws.close(code=4400, reason="apertura inválida")
        return

    # Contra probar contraseñas de un equipo a fuerza bruta desde mufa.
    clave_intentos = f"terminal:{usuario.id}"
    if estado.limitador.bloqueado(clave_intentos):
        await ws.send_text(
            json.dumps({"error": "demasiados intentos fallidos seguidos: espera 15 minutos"})
        )
        await ws.close()
        return

    destino_libre = tiene_permiso(usuario.rol, Permiso.GESTIONAR_EQUIPOS)
    bucle_principal = asyncio.get_running_loop()
    reemplazos: list[str] = []

    async def preguntar(nueva: terminal.Huella, anterior: terminal.Huella | None) -> str:
        await ws.send_text(
            json.dumps(
                {
                    "confirmar_clave": {
                        "tipo": nueva.tipo,
                        "huella": nueva.sha256,
                        "anterior": None
                        if anterior is None
                        else {"tipo": anterior.tipo, "huella": anterior.sha256},
                        "puede_reemplazar": destino_libre,
                    }
                }
            )
        )
        respuesta = json.loads(await asyncio.wait_for(ws.receive_text(), CONFIRMAR_EN))
        decision = str(respuesta.get("clave", "cancelar"))
        if anterior is not None:
            # Reemplazar la clave de un equipo es de quien administra la red.
            if decision != "reemplazar" or not destino_libre:
                return "cancelar"
            reemplazos.append(f"{anterior.sha256} → {nueva.sha256}")
            return "reemplazar"
        return decision if decision in ("guardar", "una_vez") else "cancelar"

    def confirmar(nueva: terminal.Huella, anterior: terminal.Huella | None) -> str:
        futuro = asyncio.run_coroutine_threadsafe(preguntar(nueva, anterior), bucle_principal)
        try:
            return futuro.result(CONFIRMAR_EN + 5)
        except Exception:  # noqa: BLE001 - sin respuesta o la pestaña se cerró
            return "cancelar"

    try:
        conexion, titulo = await asyncio.to_thread(
            _abrir, apertura, estado, destino_libre, confirmar
        )
    except terminal.ErrorDeTerminal as error:
        estado.limitador.registrar_fallo(clave_intentos)
        # Queda en el registro para poder revisar por qué no entró (sin la contraseña).
        with estado.sesiones() as db:
            registrar(
                db,
                usuario,
                "terminal.fallo",
                apertura.host or apertura.puerto_serie or str(apertura.equipo_id or ""),
                {"modo": apertura.modo, "puerto": apertura.puerto, "motivo": str(error)},
            )
            db.commit()
        await ws.send_text(json.dumps({"error": str(error)}))
        await ws.close()
        return

    destino = titulo if apertura.modo != "serial" else apertura.puerto_serie
    inicio = time.monotonic()
    with estado.sesiones() as db:
        for cambio in reemplazos:
            registrar(db, usuario, "terminal.clave_reemplazada", destino, {"huellas": cambio})
        registrar(db, usuario, "terminal.abrir", destino, {"modo": apertura.modo})
        db.commit()
    abierta: dict[str, str] = {"estado": "abierta", "titulo": titulo}
    if getattr(conexion, "legado", False):
        abierta["aviso"] = (
            "este equipo solo habla algoritmos SSH antiguos (SHA-1): conviene actualizar "
            "su firmware o regenerar su clave SSH"
        )
    await ws.send_text(json.dumps(abierta))

    bucle = asyncio.get_running_loop()
    salida: asyncio.Queue[bytes] = asyncio.Queue()

    def leer() -> None:
        while True:
            datos = conexion.recibir()
            bucle.call_soon_threadsafe(salida.put_nowait, datos)
            if not datos:
                return

    lector = bucle.run_in_executor(None, leer)

    async def hacia_la_app() -> None:
        while True:
            datos = await salida.get()
            if not datos:
                return
            await ws.send_bytes(datos)

    async def desde_la_app() -> None:
        while True:
            mensaje: MutableMapping[str, Any] = await asyncio.wait_for(
                ws.receive(), INACTIVIDAD_MAXIMA
            )
            if mensaje["type"] == "websocket.disconnect":
                return
            if mensaje.get("bytes"):
                await asyncio.to_thread(conexion.enviar, mensaje["bytes"])
            elif mensaje.get("text"):
                try:
                    control = json.loads(mensaje["text"])
                    conexion.redimensionar(int(control["columnas"]), int(control["filas"]))
                except (ValueError, KeyError, TypeError):
                    pass

    token = ws.cookies.get(COOKIE_SESION, "")

    async def sesion_vigente() -> None:
        # Si a la persona le cierran la sesión (cambio de contraseña, usuario
        # desactivado, rol sin permiso), su terminal se corta en menos de un minuto.
        while True:
            await asyncio.sleep(REVISAR_SESION_CADA)
            with estado.sesiones() as db:
                vigente = usuario_de_token(db, token)
                sigue = vigente is not None and tiene_permiso(
                    vigente.rol, Permiso.USAR_CREDENCIALES
                )
            if not sigue:
                await ws.send_text(json.dumps({"error": "tu sesión de mufa terminó"}))
                return

    tareas = [
        asyncio.create_task(hacia_la_app()),
        asyncio.create_task(desde_la_app()),
        asyncio.create_task(sesion_vigente()),
    ]
    try:
        await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for tarea in tareas:
            tarea.cancel()
        conexion.cerrar()
        await asyncio.gather(*tareas, lector, return_exceptions=True)
        try:
            await ws.close()
        except RuntimeError:
            pass
        with estado.sesiones() as db:
            registrar(
                db,
                usuario,
                "terminal.cerrar",
                destino,
                {"modo": apertura.modo, "segundos": round(time.monotonic() - inicio)},
            )
            db.commit()
