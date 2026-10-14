"""Carga los módulos de mufa Pro, que se publican cifrados.

El código de `mufa/pro/` (licencia comercial) no se publica legible: las
descargas y el repositorio público llevan `mufa/pro/modulos.cifrado`, con
los módulos cifrados (Fernet). La llave va dentro de cada licencia Pro, que
está firmada por el emisor: sin una licencia pagada no hay llave, y sin
llave no hay código que usar, aunque se modifique la parte AGPL.

En el repositorio privado de desarrollo los módulos están legibles y se
importan normalmente (salvo que MUFA_PRO_SOLO_CIFRADO=1, para probar la
versión cifrada).

Las rutas de Pro viven en /api/v1/pro/... a través de una pasarela que existe
desde el arranque: así se activan al instalar la licencia, sin reiniciar.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import json
import logging
import os
import sys
import threading
import zlib
from collections.abc import Callable
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

log = logging.getLogger("mufa.pro")

PAQUETE = "mufa.pro"
ARCHIVO_CIFRADO = Path(__file__).resolve().parent / "pro" / "modulos.cifrado"
# El módulo que dice qué rutas y tareas trae Pro (mufa/pro/registro.py).
REGISTRO = f"{PAQUETE}.registro"


class ErrorPro(Exception):
    pass


def descifrar(archivo: Path, llave: str) -> dict[str, str]:
    """{nombre del módulo: código fuente} del archivo cifrado."""
    try:
        comprimido = Fernet(llave.encode("ascii")).decrypt(archivo.read_bytes())
    except (InvalidToken, ValueError) as error:
        raise ErrorPro("la llave de Pro de la licencia no abre estos módulos") from error
    fuentes = json.loads(zlib.decompress(comprimido))
    if not isinstance(fuentes, dict):
        raise ErrorPro("archivo de módulos Pro dañado")
    return {str(k): str(v) for k, v in fuentes.items()}


def cifrar(fuentes: dict[str, str], llave: str) -> bytes:
    datos = zlib.compress(json.dumps(fuentes, ensure_ascii=False).encode("utf-8"), 9)
    return Fernet(llave.encode("ascii")).encrypt(datos)


class _Buscador(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Importa mufa.pro.<módulo> desde el código descifrado en memoria."""

    def __init__(self, fuentes: dict[str, str]) -> None:
        self._fuentes = fuentes

    def find_spec(
        self, fullname: str, path: Any = None, target: ModuleType | None = None
    ) -> importlib.machinery.ModuleSpec | None:
        prefijo = f"{PAQUETE}."
        if fullname.startswith(prefijo) and fullname[len(prefijo) :] in self._fuentes:
            return importlib.machinery.ModuleSpec(fullname, self, origin="mufa-pro-cifrado")
        return None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType | None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        nombre = module.__name__.rsplit(".", 1)[1]
        codigo = compile(self._fuentes[nombre], f"<mufa-pro/{nombre}.py>", "exec")
        exec(codigo, module.__dict__)  # noqa: S102 - código propio, firmado por la licencia


def _hay_legibles() -> bool:
    if os.environ.get("MUFA_PRO_SOLO_CIFRADO") == "1":
        return False
    return (Path(__file__).resolve().parent / "pro" / "registro.py").exists()


class ModulosPro:
    """Los módulos Pro de esta instalación: cargados o no, según la licencia."""

    def __init__(self, archivo: Path = ARCHIVO_CIFRADO) -> None:
        self._archivo = archivo
        self._registro: ModuleType | None = None
        self._llave: str | None = None
        self._candado = threading.Lock()
        self.app: FastAPI | None = None
        # El EstadoApp del servidor: las rutas de Pro lo usan como las demás.
        self.estado: Any = None

    @property
    def cargados(self) -> bool:
        return self._registro is not None

    def cargar(self, llave: str | None) -> bool:
        """Activa Pro si la licencia trae la llave de los módulos (o están legibles)."""
        with self._candado:
            if self._registro is not None and (llave == self._llave or _hay_legibles()):
                return True
            if not _hay_legibles():
                if not llave or not self._archivo.exists():
                    return False
                try:
                    fuentes = descifrar(self._archivo, llave)
                except ErrorPro as error:
                    log.warning("%s", error)
                    return False
                sys.meta_path.insert(0, _Buscador(fuentes))
            registro = importlib.import_module(REGISTRO)
            app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
            app.state.mufa = self.estado
            for router in registro.ROUTERS:
                app.include_router(router)
            self.app, self._registro, self._llave = app, registro, llave
            log.info("módulos Pro cargados")
            return True

    def tarea_de_sondeo(self, db: Session, plan: Any, hoy: date) -> None:
        """Lo que Pro hace después de cada sondeo (por ejemplo, el resumen diario)."""
        if self._registro is not None:
            tarea: Callable[[Session, Any, date], None] = self._registro.despues_del_sondeo
            tarea(db, plan, hoy)


class Pasarela:
    """Montada en /api/v1/pro: pasa a los módulos Pro, o responde 402 si no están."""

    def __init__(self, modulos: ModulosPro) -> None:
        self._modulos = modulos

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = self._modulos.app
        if app is None:
            if scope["type"] == "http":
                respuesta = JSONResponse(
                    {"detail": "esta función es de mufa Pro: instala una licencia Pro"},
                    status_code=402,
                )
                await respuesta(scope, receive, send)
            return
        await app(scope, receive, send)
