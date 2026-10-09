"""Resumen para el panel principal: todo lo que importa en una sola consulta."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from mufa import marcas, servicios
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import EquipoCaido, HallazgoAbierto, HallazgoSalida
from mufa.db import (
    CanalAlerta,
    Equipo,
    EstadoEquipo,
    HallazgoGuardado,
    Respaldo,
    Usuario,
    ahora,
    como_utc,
)
from mufa.permisos import Permiso

router = APIRouter(tags=["panel"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]

_ORDEN_SEVERIDAD = {"crítico": 0, "alto": 1, "medio": 2, "info": 3}
# Un respaldo diario está al día si se confirmó en las últimas 26 h.
_RESPALDO_AL_DIA = timedelta(hours=26)


class Panel(BaseModel):
    equipos: int
    max_equipos: int | None
    plan: str
    monitoreados: int
    en_linea: int
    caidos: list[EquipoCaido]
    hallazgos_por_severidad: dict[str, int]
    # Promedio de los equipos auditados; None si no hay ninguno.
    puntaje_red: int | None
    hallazgos_principales: list[HallazgoAbierto]
    respaldables: int
    respaldos_al_dia: int
    canales_de_alerta: int


def _puntaje_red(db: DB, abiertos: list[tuple[HallazgoGuardado, Equipo]]) -> int | None:
    auditados = servicios.equipos_auditados(db)
    if not auditados:
        return None
    severidades: dict[int, list[str]] = {i: [] for i in auditados}
    for hallazgo, equipo in abiertos:
        severidades.setdefault(equipo.id, []).append(hallazgo.severidad)
    puntajes = [servicios.puntaje(s) for s in severidades.values()]
    return round(sum(puntajes) / len(puntajes))


@router.get("/panel")
def panel(_: Lector, db: DB, estado: Estado) -> Panel:
    plan, _aviso = estado.plan()
    abiertos = servicios.hallazgos_abiertos(db)
    abiertos.sort(key=lambda fila: (_ORDEN_SEVERIDAD.get(fila[0].severidad, 9), fila[1].nombre))

    respaldables = list(
        db.scalars(
            select(Equipo.id).where(
                Equipo.usuario_ssh != "", Equipo.marca.in_(list(marcas.RESPALDADORES))
            )
        )
    )
    ultimos = dict(
        db.execute(
            select(Respaldo.equipo_id, func.max(Respaldo.confirmado))
            .where(Respaldo.equipo_id.in_(respaldables))
            .group_by(Respaldo.equipo_id)
        )
        .tuples()
        .all()
    )
    limite = ahora() - _RESPALDO_AL_DIA
    caidos = db.execute(
        select(Equipo, EstadoEquipo)
        .join(EstadoEquipo, EstadoEquipo.equipo_id == Equipo.id)
        .where(Equipo.snmp_version != "", EstadoEquipo.en_linea.is_(False))
        .order_by(Equipo.nombre)
    ).tuples()

    return Panel(
        equipos=db.scalar(select(func.count()).select_from(Equipo)) or 0,
        max_equipos=plan.max_equipos,
        plan=plan.nombre,
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
        hallazgos_por_severidad=dict(Counter(h.severidad for h, _ in abiertos)),
        puntaje_red=_puntaje_red(db, abiertos),
        hallazgos_principales=[
            HallazgoAbierto(
                equipo_id=equipo.id,
                equipo=equipo.nombre,
                auditoria_id=hallazgo.auditoria_id,
                hallazgo=HallazgoSalida.model_validate(hallazgo),
            )
            for hallazgo, equipo in abiertos[:8]
        ],
        respaldables=len(respaldables),
        respaldos_al_dia=sum(1 for momento in ultimos.values() if como_utc(momento) >= limite),
        canales_de_alerta=db.scalar(select(func.count()).where(CanalAlerta.activo.is_(True))) or 0,
    )
