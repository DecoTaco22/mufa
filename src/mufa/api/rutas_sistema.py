"""Salud, marcas soportadas, licencia y registro de eventos."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from mufa import __version__, auth, licencia, marcas, primera_vez
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import (
    EstadoInicial,
    EventoSalida,
    LicenciaInstalar,
    LicenciaSalida,
    MarcaSalida,
    PrimerAdmin,
)
from mufa.db import Equipo, Evento, Usuario
from mufa.permisos import Permiso, Rol
from mufa.servicios import registrar

router = APIRouter(tags=["sistema"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Admin = Annotated[Usuario, Depends(requiere(Permiso.ADMINISTRAR_USUARIOS))]
Revisor = Annotated[Usuario, Depends(requiere(Permiso.VER_REGISTRO))]


@router.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok", "version": __version__}


@router.get("/sistema/inicial")
def estado_inicial(db: DB) -> EstadoInicial:
    """Público: la app web lo usa para mostrar el asistente de primera vez."""
    return EstadoInicial(necesita_admin=not primera_vez.hay_usuarios(db))


@router.post("/sistema/inicial", status_code=status.HTTP_201_CREATED)
def crear_primer_admin(
    entrada: PrimerAdmin, request: Request, db: DB, estado: Estado
) -> dict[str, str]:
    if primera_vez.hay_usuarios(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "mufa ya tiene administrador")
    clave = f"inicial:{request.client.host if request.client else ''}"
    if estado.limitador.bloqueado(clave):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "demasiados intentos")
    if not primera_vez.token_valido(estado.token_inicial, entrada.token):
        estado.limitador.registrar_fallo(clave)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "el token no es correcto: está en la consola del servidor o en "
            f"{primera_vez.NOMBRE_ARCHIVO}, en el directorio de datos",
        )
    try:
        hash_password = auth.hashear_password(entrada.password)
    except auth.PasswordDebil as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    admin = Usuario(
        usuario=entrada.usuario,
        email=entrada.email.lower() if entrada.email else None,
        nombre=entrada.nombre,
        rol=Rol.ADMIN.value,
        hash_password=hash_password,
    )
    db.add(admin)
    db.flush()
    registrar(db, admin, "usuario.crear_admin_inicial", admin.usuario)
    estado.token_inicial = None
    primera_vez.descartar(estado.ajustes.dir_datos)
    return {"usuario": admin.usuario}


@router.get("/marcas")
def listar_marcas(_: Lector) -> list[MarcaSalida]:
    return [
        MarcaSalida(
            marca=marca,
            nombre=nombre,
            con_adaptador=marca in marcas.ADAPTADORES,
            con_respaldo=marca in marcas.RESPALDADORES,
        )
        for marca, nombre in marcas.MARCAS_CONOCIDAS.items()
    ]


def _licencia(db: DB, estado: Estado) -> LicenciaSalida:
    plan, aviso = estado.plan()
    return LicenciaSalida(
        plan=plan.nombre,
        cliente=plan.cliente,
        max_equipos=plan.max_equipos,
        equipos_registrados=db.scalar(select(func.count()).select_from(Equipo)) or 0,
        vence=plan.vence,
        aviso=aviso,
        funciones=[f.value for f in plan.funciones],
    )


@router.get("/licencia")
def ver_licencia(_: Lector, db: DB, estado: Estado) -> LicenciaSalida:
    return _licencia(db, estado)


@router.put("/licencia")
def instalar_licencia(
    entrada: LicenciaInstalar, admin: Admin, db: DB, estado: Estado
) -> LicenciaSalida:
    try:
        plan = licencia.verificar(entrada.licencia, licencia.hoy())
    except licencia.LicenciaInvalida as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    estado.archivo_licencia.parent.mkdir(parents=True, exist_ok=True)
    estado.archivo_licencia.write_text(entrada.licencia.strip(), encoding="utf-8")
    registrar(db, admin, "licencia.instalar", plan.cliente, {"plan": plan.nombre})
    return _licencia(db, estado)


@router.get("/eventos")
def listar_eventos(_: Revisor, db: DB, limite: int = 100) -> list[EventoSalida]:
    consulta = select(Evento).order_by(Evento.id.desc()).limit(min(max(limite, 1), 1000))
    return [EventoSalida.model_validate(e) for e in db.scalars(consulta)]
