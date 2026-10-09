"""Monitoreo SNMP: estado de los equipos y tráfico de sus interfaces."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from mufa import monitoreo, snmp
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import (
    EquipoCaido,
    EstadoSalida,
    InterfazSalida,
    PruebaSnmp,
    ResultadoPruebaSnmp,
    ResumenMonitoreo,
)
from mufa.api.rutas_inventario import credenciales_snmp, obtener_equipo
from mufa.db import Equipo, EstadoEquipo, InterfazVigilada, Usuario
from mufa.permisos import Permiso

router = APIRouter(tags=["monitoreo"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Tecnico = Annotated[Usuario, Depends(requiere(Permiso.USAR_CREDENCIALES))]
Gestor = Annotated[Usuario, Depends(requiere(Permiso.GESTIONAR_EQUIPOS))]


@router.post("/equipos/{equipo_id}/sondear")
def sondear(equipo_id: int, _: Tecnico, db: DB, estado: Estado) -> EstadoSalida:
    equipo = obtener_equipo(db, equipo_id)
    if not equipo.snmp_version:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "el equipo no tiene SNMP configurado"
        )
    return EstadoSalida.model_validate(monitoreo.sondear_equipo(db, equipo, estado.cifrador))


@router.post("/snmp/probar")
def probar_snmp(entrada: PruebaSnmp, _: Gestor, db: DB, estado: Estado) -> ResultadoPruebaSnmp:
    """Prueba una configuración SNMP antes de guardarla. Lee el grupo system y la identidad del equipo."""
    previo = obtener_equipo(db, entrada.equipo_id) if entrada.equipo_id is not None else None
    cred = credenciales_snmp(entrada.snmp, previo, estado.cifrador)
    origen = snmp.ip_de_origen(entrada.ip_gestion, cred.puerto)
    try:
        resultado = snmp.probar(entrada.ip_gestion, cred)
    except snmp.ErrorSNMP as error:
        return ResultadoPruebaSnmp(ok=False, mensaje=str(error), ip_origen=origen)
    return ResultadoPruebaSnmp(
        ok=True,
        mensaje="El equipo respondió.",
        sys_nombre=resultado.nombre,
        sys_descripcion=resultado.descripcion,
        marca_detectada=resultado.marca_detectada,
        modelo=resultado.modelo,
        serie=resultado.serie,
        version=resultado.version,
        ubicacion=resultado.ubicacion,
        ip_origen=origen,
    )


@router.get("/equipos/{equipo_id}/estado")
def ver_estado(equipo_id: int, _: Lector, db: DB) -> EstadoSalida:
    obtener_equipo(db, equipo_id)
    actual = db.get(EstadoEquipo, equipo_id)
    if actual is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "el equipo todavía no fue sondeado")
    return EstadoSalida.model_validate(actual)


@router.get("/equipos/{equipo_id}/interfaces")
def interfaces(equipo_id: int, _: Lector, db: DB) -> list[InterfazSalida]:
    obtener_equipo(db, equipo_id)
    vigiladas = {
        v.if_index: v
        for v in db.scalars(select(InterfazVigilada).where(InterfazVigilada.equipo_id == equipo_id))
    }
    salidas = []
    for trafico in monitoreo.trafico(db, equipo_id):
        vigilada = vigiladas.get(trafico.if_index)
        salidas.append(
            InterfazSalida.model_validate(trafico).model_copy(
                update={
                    "vigilada_id": vigilada.id if vigilada else None,
                    "umbral_saturacion": vigilada.umbral_saturacion if vigilada else None,
                }
            )
        )
    return salidas


@router.get("/monitoreo/resumen")
def resumen(_: Lector, db: DB) -> ResumenMonitoreo:
    caidos = db.execute(
        select(Equipo, EstadoEquipo)
        .join(EstadoEquipo, EstadoEquipo.equipo_id == Equipo.id)
        .where(Equipo.snmp_version != "", EstadoEquipo.en_linea.is_(False))
        .order_by(Equipo.nombre)
    ).all()
    return ResumenMonitoreo(
        equipos=db.scalar(select(func.count()).select_from(Equipo)) or 0,
        monitoreados=db.scalar(select(func.count()).where(Equipo.snmp_version != "")) or 0,
        en_linea=db.scalar(select(func.count()).where(EstadoEquipo.en_linea.is_(True))) or 0,
        caidos=[
            EquipoCaido(
                equipo_id=equipo.id,
                nombre=equipo.nombre,
                ultimo_en_linea=actual.ultimo_en_linea,
                error=actual.error,
                alcanzable=actual.alcanzable,
            )
            for equipo, actual in caidos
        ],
    )
