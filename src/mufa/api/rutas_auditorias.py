"""Auditorías: por SSH a un equipo del inventario o sobre un export subido."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from mufa import marcas, servicios
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import (
    AuditoriaResumen,
    AuditoriaSalida,
    HallazgoAbierto,
    HallazgoSalida,
)
from mufa.api.rutas_inventario import exigir_adaptador, obtener_equipo
from mufa.db import Auditoria, HallazgoGuardado, Usuario
from mufa.permisos import Permiso

router = APIRouter(tags=["auditorias"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Auditor = Annotated[Usuario, Depends(requiere(Permiso.AUDITAR))]

TAMANO_MAXIMO_EXPORT = 5 * 1024 * 1024


def _cargar(db: DB, auditoria_id: int) -> AuditoriaSalida:
    auditoria = db.scalar(
        select(Auditoria)
        .where(Auditoria.id == auditoria_id)
        .options(selectinload(Auditoria.hallazgos))
    )
    if auditoria is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "auditoría no encontrada")
    return AuditoriaSalida.model_validate(auditoria)


@router.post("/equipos/{equipo_id}/auditar")
def auditar_equipo(equipo_id: int, usuario: Auditor, db: DB, estado: Estado) -> AuditoriaSalida:
    equipo = obtener_equipo(db, equipo_id)
    exigir_adaptador(equipo)
    if not equipo.usuario_ssh:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "el equipo no tiene usuario de acceso (SSH o API) configurado",
        )
    auditoria = servicios.auditar_equipo(
        db, equipo, usuario, estado.cifrador, estado.ajustes.known_hosts
    )
    return _cargar(db, auditoria.id)


@router.post("/auditorias/archivo", status_code=status.HTTP_201_CREATED)
async def auditar_archivo(
    usuario: Auditor,
    db: DB,
    archivo: Annotated[UploadFile, File(description="Export de configuración del equipo")],
    marca: Annotated[str, Form()] = "mikrotik",
) -> AuditoriaSalida:
    if marca not in marcas.ADAPTADORES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"marca no soportada: {marca!r}")
    contenido = await archivo.read(TAMANO_MAXIMO_EXPORT + 1)
    if len(contenido) > TAMANO_MAXIMO_EXPORT:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "el archivo supera los 5 MB")
    texto = contenido.decode("utf-8", errors="replace")
    auditoria = servicios.auditar_texto(db, texto, marca, archivo.filename or "export", usuario)
    return _cargar(db, auditoria.id)


@router.get("/auditorias")
def listar_auditorias(
    _: Lector, db: DB, equipo_id: int | None = None, limite: int = 50
) -> list[AuditoriaResumen]:
    cantidad = (
        select(func.count(HallazgoGuardado.id))
        .where(HallazgoGuardado.auditoria_id == Auditoria.id)
        .scalar_subquery()
    )
    consulta = (
        select(Auditoria, cantidad).order_by(Auditoria.id.desc()).limit(min(max(limite, 1), 500))
    )
    if equipo_id is not None:
        consulta = consulta.where(Auditoria.equipo_id == equipo_id)
    return [
        AuditoriaResumen(
            id=a.id,
            equipo_id=a.equipo_id,
            origen=a.origen,
            etiqueta=a.etiqueta,
            marca=a.marca,
            estado=a.estado,
            inicio=a.inicio,
            cantidad_hallazgos=n,
        )
        for a, n in db.execute(consulta)
    ]


@router.get("/auditorias/{auditoria_id}")
def ver_auditoria(auditoria_id: int, _: Lector, db: DB) -> AuditoriaSalida:
    return _cargar(db, auditoria_id)


@router.get("/hallazgos")
def hallazgos_abiertos(_: Lector, db: DB) -> list[HallazgoAbierto]:
    """Los hallazgos de la última auditoría exitosa de cada equipo."""
    return [
        HallazgoAbierto(
            equipo_id=equipo.id,
            equipo=equipo.nombre,
            auditoria_id=hallazgo.auditoria_id,
            hallazgo=HallazgoSalida.model_validate(hallazgo),
        )
        for hallazgo, equipo in servicios.hallazgos_abiertos(db)
    ]
