"""Administración de usuarios (solo Admin)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from mufa import auth
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import NuevaPassword, UsuarioActualizar, UsuarioCrear, UsuarioSalida
from mufa.db import Usuario
from mufa.permisos import Permiso, Rol
from mufa.servicios import registrar

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

Admin = Annotated[Usuario, Depends(requiere(Permiso.ADMINISTRAR_USUARIOS))]


def _obtener(db: DB, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "usuario no encontrado")
    return usuario


def _admins_activos(db: DB) -> int:
    return (
        db.scalar(
            select(func.count()).where(Usuario.rol == Rol.ADMIN.value, Usuario.activo.is_(True))
        )
        or 0
    )


@router.get("")
def listar(_: Admin, db: DB) -> list[UsuarioSalida]:
    usuarios = db.scalars(select(Usuario).order_by(Usuario.nombre))
    return [UsuarioSalida.model_validate(u) for u in usuarios]


@router.post("", status_code=status.HTTP_201_CREATED)
def crear(entrada: UsuarioCrear, admin: Admin, db: DB, estado: Estado) -> UsuarioSalida:
    plan, _aviso = estado.plan()
    activos = db.scalar(select(func.count()).where(Usuario.activo.is_(True))) or 0
    plan.exigir_lugar("usuarios", activos, plan.max_usuarios)
    email = entrada.email.lower() if entrada.email else None
    if db.scalar(select(Usuario).where(Usuario.usuario == entrada.usuario)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya existe ese nombre de usuario")
    if email and db.scalar(select(Usuario).where(Usuario.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya existe un usuario con ese email")
    try:
        hash_password = auth.hashear_password(entrada.password)
    except auth.PasswordDebil as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    usuario = Usuario(
        usuario=entrada.usuario,
        email=email,
        nombre=entrada.nombre,
        rol=entrada.rol.value,
        hash_password=hash_password,
    )
    db.add(usuario)
    db.flush()
    registrar(db, admin, "usuario.crear", usuario.usuario, {"rol": entrada.rol.value})
    return UsuarioSalida.model_validate(usuario)


@router.patch("/{usuario_id}")
def actualizar(usuario_id: int, entrada: UsuarioActualizar, admin: Admin, db: DB) -> UsuarioSalida:
    usuario = _obtener(db, usuario_id)
    deja_de_ser_admin = usuario.rol == Rol.ADMIN.value and (
        (entrada.rol is not None and entrada.rol != Rol.ADMIN) or entrada.activo is False
    )
    if deja_de_ser_admin and usuario.activo and _admins_activos(db) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "no se puede quitar al último administrador activo"
        )

    cambios = entrada.model_dump(exclude_unset=True)
    if entrada.nombre is not None:
        usuario.nombre = entrada.nombre
    if entrada.rol is not None:
        usuario.rol = entrada.rol.value
    if entrada.activo is not None:
        usuario.activo = entrada.activo
        if not entrada.activo:
            auth.cerrar_todas_las_sesiones(db, usuario.id)
    registrar(db, admin, "usuario.actualizar", usuario.usuario, {"cambios": cambios})
    return UsuarioSalida.model_validate(usuario)


@router.post("/{usuario_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def restablecer_password(usuario_id: int, entrada: NuevaPassword, admin: Admin, db: DB) -> None:
    usuario = _obtener(db, usuario_id)
    try:
        usuario.hash_password = auth.hashear_password(entrada.password)
    except auth.PasswordDebil as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    auth.cerrar_todas_las_sesiones(db, usuario.id)
    registrar(db, admin, "usuario.restablecer_password", usuario.usuario)


@router.post("/{usuario_id}/2fa/restablecer", status_code=status.HTTP_204_NO_CONTENT)
def restablecer_dos_pasos(usuario_id: int, admin: Admin, db: DB) -> None:
    """Para quien perdió el teléfono: al volver a entrar tiene que configurarla de nuevo."""
    usuario = _obtener(db, usuario_id)
    usuario.totp_activo = False
    usuario.totp_secreto_cifrado = None
    auth.cerrar_todas_las_sesiones(db, usuario.id)
    registrar(db, admin, "usuario.restablecer_2fa", usuario.usuario)
