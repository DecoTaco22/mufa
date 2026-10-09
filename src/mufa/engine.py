"""Motor de verificaciones: registro y ejecución.

Cada verificación se declara con @check(...) sobre una función que recibe
un Contexto y devuelve un Hallazgo o None. El motor no sabe nada de router,
DNS ni firewall: solo colecciona funciones y las corre.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mufa.models import Contexto, Hallazgo, Severidad

ComprobacionFn = Callable[[Contexto], "Hallazgo | None"]


@dataclass(frozen=True)
class Comprobacion:
    id: str
    severidad: Severidad
    titulo: str
    funcion: ComprobacionFn
    # None: aplica a todas las marcas.
    marcas: frozenset[str] | None = None


_REGISTRO: list[Comprobacion] = []


def check(
    *,
    id: str,
    severidad: Severidad,
    titulo: str,
    marcas: list[str] | None = None,
) -> Callable[[ComprobacionFn], ComprobacionFn]:
    def decorador(funcion: ComprobacionFn) -> ComprobacionFn:
        _REGISTRO.append(
            Comprobacion(
                id=id,
                severidad=severidad,
                titulo=titulo,
                funcion=funcion,
                marcas=frozenset(marcas) if marcas is not None else None,
            )
        )
        return funcion

    return decorador


def evaluar(ctx: Contexto) -> list[Hallazgo]:
    return [
        hallazgo
        for hallazgo in (
            comprobacion.funcion(ctx)
            for comprobacion in _REGISTRO
            if comprobacion.marcas is None or ctx.marca in comprobacion.marcas
        )
        if hallazgo is not None
    ]


# Importar el paquete de verificaciones dispara cada @check de arriba.
# Va al final para que "check" ya exista cuando checks/*.py lo importe.
from mufa import checks  # noqa: F401
