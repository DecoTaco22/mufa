"""Carga los módulos de mufa Pro, que se publican cifrados.

El código de `mufa/pro/` (licencia comercial) no se publica legible: las
descargas y el repositorio público llevan `mufa/pro/modulos.cifrado`, con
los módulos cifrados (Fernet). Las llaves van dentro de cada licencia Pro,
que está firmada por el emisor: sin una licencia pagada no hay llave, y sin
llave no hay código que usar, aunque se modifique la parte AGPL.

La llave se rota de vez en cuando (scripts/cifrar_pro.py --rotar): una
licencia que ya no se renueva abre los módulos de las versiones que salieron
mientras estaba pagada, pero no los de las siguientes.

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
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
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


def descifrar(archivo: Path, llaves: str | Sequence[str]) -> dict[str, str]:
    """{nombre del módulo: código fuente} del archivo cifrado, con la llave que lo abra."""
    if isinstance(llaves, str):
        llaves = [llaves]
    try:
        if not llaves:
            raise ValueError("sin llaves")
        fernet = MultiFernet([Fernet(llave.encode("ascii")) for llave in llaves])
        comprimido = fernet.decrypt(archivo.read_bytes())
    except (InvalidToken, ValueError) as error:
        raise ErrorPro("las llaves de Pro de la licencia no abren estos módulos") from error
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
        self._llaves: tuple[str, ...] = ()
        # La licencia trae llaves pero ninguna abre los módulos de esta versión.
        self.faltan_llaves = False
        self._candado = threading.Lock()
        self.app: FastAPI | None = None
        # El EstadoApp del servidor: las rutas de Pro lo usan como las demás.
        self.estado: Any = None

    @property
    def cargados(self) -> bool:
        return self._registro is not None

    def cargar(self, llaves: Sequence[str]) -> bool:
        """Activa Pro si la licencia trae la llave de los módulos (o están legibles)."""
        llaves = tuple(llaves)
        with self._candado:
            if self._registro is not None and (llaves == self._llaves or _hay_legibles()):
                return True
            if not _hay_legibles():
                if not llaves or not self._archivo.exists():
                    return False
                try:
                    fuentes = descifrar(self._archivo, llaves)
                except ErrorPro as error:
                    log.warning("%s", error)
                    self.faltan_llaves = True
                    return False
                self.faltan_llaves = False
                sys.meta_path.insert(0, _Buscador(fuentes))
            registro = importlib.import_module(REGISTRO)
            if hasattr(registro, "al_cargar"):
                registro.al_cargar(self.estado)
            app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
            app.state.mufa = self.estado
            for router in registro.ROUTERS:
                app.include_router(router)
            self.app, self._registro, self._llaves = app, registro, llaves
            log.info("módulos Pro cargados")
            return True

    def tarea_de_sondeo(self, db: Session, plan: Any, hoy: date) -> None:
        """Lo que Pro hace después de cada sondeo (por ejemplo, el resumen diario)."""
        if self._registro is not None:
            tarea: Callable[[Session, Any, date], None] = self._registro.despues_del_sondeo
            tarea(db, plan, hoy)

    def tarea_frecuente(self, db: Session, plan: Any) -> None:
        """Lo que Pro revisa seguido (cada vuelta del programador, unos 15 segundos)."""
        if self._registro is not None and hasattr(self._registro, "cada_rato"):
            tarea: Callable[[Session, Any], None] = self._registro.cada_rato
            tarea(db, plan)


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
