"""Servidor HTTP de mufa: crea la app de FastAPI con su estado y sus rutas."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mufa import __version__, primera_vez
from mufa.api import (
    rutas_alertas,
    rutas_auditorias,
    rutas_auth,
    rutas_fibra,
    rutas_inventario,
    rutas_ipam,
    rutas_monitoreo,
    rutas_panel,
    rutas_red,
    rutas_respaldos,
    rutas_sistema,
    rutas_terminal,
    rutas_usuarios,
    rutas_vlans,
)
from mufa.api.deps import EstadoApp
from mufa.auth import LimitadorDeIntentos
from mufa.cifrado import Cifrador, cargar_o_crear_clave
from mufa.config import Ajustes, cargar_ajustes
from mufa.db import crear_motor, fabrica_de_sesiones
from mufa.licencia import LimiteDelPlan
from mufa.migraciones import actualizar_base
from mufa.modulos_pro import ModulosPro, Pasarela
from mufa.tareas import Programador

PREFIJO = "/api/v1"

# La app web compilada (ver web/). Si no está, el servidor solo expone la API.
DIRECTORIO_WEB = Path(__file__).resolve().parent.parent / "web"

_CABECERAS_DE_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
}
# La API solo devuelve JSON: no carga nada.
_CSP_API = "default-src 'none'; frame-ancestors 'none'"
# La app web: todo sale del propio servidor, nada de terceros ni código en línea.
# style-src 'unsafe-inline': la terminal (xterm.js) calcula su tamaño en un <style>
# propio. Los scripts siguen sin poder ser inline.
_CSP_WEB = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


def crear_app(ajustes: Ajustes | None = None, migrar: bool = True) -> FastAPI:
    ajustes = ajustes or cargar_ajustes()
    ajustes.dir_datos.mkdir(parents=True, exist_ok=True)
    if migrar:
        actualizar_base(ajustes.url_base_datos)

    sesiones = fabrica_de_sesiones(crear_motor(ajustes.url_base_datos))
    cifrador = Cifrador(cargar_o_crear_clave(ajustes.archivo_clave))
    pro = ModulosPro()
    programador = Programador(ajustes, sesiones, cifrador, pro)

    @asynccontextmanager
    async def ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
        programador.iniciar()
        try:
            yield
        finally:
            programador.detener()

    app = FastAPI(
        lifespan=ciclo_de_vida,
        title="mufa",
        version=__version__,
        docs_url=f"{PREFIJO}/docs",
        redoc_url=None,
        openapi_url=f"{PREFIJO}/openapi.json",
    )
    if ajustes.hosts_permitidos:
        # Cubre HTTP y WebSocket: otra página que apunte su dominio a 127.0.0.1 no llega.
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ajustes.hosts_permitidos))
    app.state.mufa = EstadoApp(
        ajustes=ajustes,
        sesiones=sesiones,
        cifrador=cifrador,
        limitador=LimitadorDeIntentos(),
        token_inicial=primera_vez.preparar(sesiones, ajustes.dir_datos),
        programador=programador,
        pro=pro,
    )
    pro.estado = app.state.mufa
    pro.cargar(app.state.mufa.plan()[0].llave_pro)
    if app.state.mufa.token_inicial:
        print(
            "\nmufa todavía no tiene administrador. Ábrelo en el navegador y usa este token:\n"
            f"  {app.state.mufa.token_inicial}\n"
            f"(también está en {primera_vez.archivo_token(ajustes.dir_datos)})\n",
            file=sys.stderr,
            flush=True,
        )

    @app.middleware("http")
    async def cabeceras_de_seguridad(
        request: Request, siguiente: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        respuesta = await siguiente(request)
        ruta = request.url.path
        for nombre, valor in _CABECERAS_DE_SEGURIDAD.items():
            respuesta.headers.setdefault(nombre, valor)
        if ruta.startswith(f"{PREFIJO}/"):
            respuesta.headers.setdefault("Cache-Control", "no-store")
            # La documentación interactiva carga sus scripts: tiene su propia política.
            if ruta != f"{PREFIJO}/docs":
                respuesta.headers.setdefault("Content-Security-Policy", _CSP_API)
        else:
            respuesta.headers.setdefault("Content-Security-Policy", _CSP_WEB)
            # Los archivos de assets/ llevan un hash en el nombre: se pueden guardar.
            cache = (
                "public, max-age=31536000, immutable" if ruta.startswith("/assets/") else "no-cache"
            )
            respuesta.headers.setdefault("Cache-Control", cache)
        return respuesta

    for modulo in (
        rutas_sistema,
        rutas_panel,
        rutas_auth,
        rutas_usuarios,
        rutas_inventario,
        rutas_auditorias,
        rutas_respaldos,
        rutas_monitoreo,
        rutas_alertas,
        rutas_ipam,
        rutas_vlans,
        rutas_fibra,
        rutas_red,
        rutas_terminal,
    ):
        app.include_router(modulo.router, prefix=PREFIJO)
    # Antes que la app web: si no, /{ruta:path} se quedaría con /api/v1/pro/...
    app.mount(f"{PREFIJO}/pro", Pasarela(pro))

    @app.exception_handler(LimiteDelPlan)
    async def limite_del_plan(request: Request, error: LimiteDelPlan) -> JSONResponse:
        # 402: la app lo muestra como una invitación a Pro, no como un error.
        return JSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, content={"detail": str(error)}
        )

    if (DIRECTORIO_WEB / "index.html").exists():
        _servir_web(app, DIRECTORIO_WEB)
    return app


def _servir_web(app: FastAPI, directorio: Path) -> None:
    """Sirve la app web. Cualquier ruta que no sea un archivo es una pantalla de la app."""
    app.mount("/assets", StaticFiles(directory=directorio / "assets"), name="assets")
    indice = directorio / "index.html"

    @app.get("/{ruta:path}", include_in_schema=False)
    async def app_web(ruta: str) -> FileResponse:
        if ruta.startswith(PREFIJO.lstrip("/")):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "ruta de la API inexistente")
        archivo = (directorio / ruta).resolve()
        # resolve() + is_relative_to: nada de ../ para salir del directorio web.
        if ruta and archivo.is_file() and archivo.is_relative_to(directorio):
            return FileResponse(archivo)
        return FileResponse(indice)
