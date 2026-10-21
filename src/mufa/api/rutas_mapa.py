"""Mapa de topología y datos para el modo NOC."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from mufa import alertas, topologia
from mufa.api.deps import DB, Estado, requiere
from mufa.db import Evento, Usuario, Vecino
from mufa.permisos import Permiso
from mufa.servicios import registrar

router = APIRouter(tags=["mapa"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Diagnostico = Annotated[Usuario, Depends(requiere(Permiso.DIAGNOSTICAR))]


class NodoSalida(BaseModel):
    id: str
    nombre: str
    marca: str
    ip: str
    sitio: str
    estado: str
    plataforma: str


class EnlaceSalida(BaseModel):
    desde: str
    hasta: str
    interfaz: str
    puerto: str


class EventoReciente(BaseModel):
    cuando: datetime
    tipo: str
    titulo: str
    objeto: str


class MapaSalida(BaseModel):
    nodos: list[NodoSalida]
    enlaces: list[EnlaceSalida]
    actualizado: datetime | None
    eventos: list[EventoReciente]


class DescubrirSalida(BaseModel):
    equipos: int
    vecinos: int
    errores: dict[str, str]


def _salida(db: DB) -> MapaSalida:
    nodos, enlaces = topologia.mapa(db)
    recientes = db.scalars(
        select(Evento)
        .where(Evento.accion.in_(list(alertas.TIPOS)))
        .order_by(Evento.id.desc())
        .limit(15)
    )
    return MapaSalida(
        nodos=[NodoSalida(**vars(n)) for n in nodos],
        enlaces=[EnlaceSalida(**vars(e)) for e in enlaces],
        actualizado=db.scalar(select(func.max(Vecino.visto))),
        eventos=[
            EventoReciente(
                cuando=e.cuando,
                tipo=e.accion,
                titulo=alertas.TIPOS.get(e.accion, e.accion),
                objeto=e.objeto,
            )
            for e in recientes
        ],
    )


@router.get("/mapa")
def ver_mapa(_: Lector, db: DB) -> MapaSalida:
    return _salida(db)


@router.post("/mapa/descubrir")
def descubrir(usuario: Diagnostico, db: DB, estado: Estado) -> DescubrirSalida:
    """Lee por SNMP los vecinos (LLDP, CDP, MikroTik) de todos los equipos. Solo lectura."""
    resultado = topologia.descubrir(db, estado.cifrador)
    registrar(
        db,
        usuario,
        "mapa.descubrir",
        "",
        {"equipos": resultado.equipos, "vecinos": resultado.vecinos},
    )
    return DescubrirSalida(**vars(resultado))
