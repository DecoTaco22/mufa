"""Inicio y cierre de sesión, cambio de contraseña y verificación en dos pasos."""

from __future__ import annotations

import time
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, or_, select

from mufa import auth, dos_pasos
from mufa.api.deps import (
    COOKIE_SESION,
    DB,
    Estado,
    Token,
    UsuarioActual,
    falta_dos_pasos,
)
from mufa.api.esquemas import (
    CambioPassword,
    CodigoDosPasos,
    CodigosRecuperacion,
    DesactivarDosPasos,
    DosPasosInicio,
    LoginEntrada,
    LoginSalida,
    UsuarioSalida,
    Yo,
)
from mufa.cifrado import Cifrador
from mufa.db import CodigoRecuperacion, Usuario
from mufa.servicios import registrar

router = APIRouter(prefix="/auth", tags=["auth"])

_CREDENCIALES_INVALIDAS = "usuario o contraseña incorrectos"
CABECERA_DOS_PASOS = "X-Mufa-Dos-Pasos"


def _nuevos_codigos(db: DB, usuario: Usuario) -> list[str]:
    """Reemplaza los códigos de recuperación del usuario y devuelve los nuevos en claro."""
    db.execute(delete(CodigoRecuperacion).where(CodigoRecuperacion.usuario_id == usuario.id))
    codigos = dos_pasos.nuevos_codigos_recuperacion()
    for codigo in codigos:
        db.add(CodigoRecuperacion(usuario_id=usuario.id, hash_codigo=dos_pasos.hash_codigo(codigo)))
    return codigos


def _usar_codigo_recuperacion(db: DB, usuario: Usuario, codigo: str) -> bool:
    guardado = db.scalar(
        select(CodigoRecuperacion).where(
            CodigoRecuperacion.usuario_id == usuario.id,
            CodigoRecuperacion.hash_codigo == dos_pasos.hash_codigo(codigo),
            CodigoRecuperacion.usado.is_(False),
        )
    )
    if guardado is None:
        return False
    guardado.usado = True
    return True


def _codigo_valido(usuario: Usuario, codigo: str, cifrador: Cifrador) -> bool:
    """Verifica el código y, si sirve, lo marca como usado."""
    if usuario.totp_secreto_cifrado is None:
        return False
    secreto = cifrador.descifrar(usuario.totp_secreto_cifrado)
    paso = dos_pasos.verificar(secreto, codigo, usuario.totp_ultimo_paso, time.time())
    if paso is None:
        return False
    usuario.totp_ultimo_paso = paso
    return True


@router.post("/login")
def login(
    entrada: LoginEntrada, request: Request, respuesta: Response, db: DB, estado: Estado
) -> LoginSalida:
    """Con la cabecera X-Mufa-Cliente: web, la sesión va en una cookie HttpOnly."""
    identificador = entrada.usuario.strip().lower()
    ip = request.client.host if request.client else "desconocida"
    claves = (f"usuario:{identificador}", f"ip:{ip}")

    if estado.limitador.bloqueado(*claves):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "demasiados intentos fallidos; esperá 15 minutos",
        )

    usuario = db.scalar(
        select(Usuario).where(or_(Usuario.usuario == identificador, Usuario.email == identificador))
    )
    valida = auth.verificar_password(usuario.hash_password if usuario else None, entrada.password)
    if usuario is None or not valida or not usuario.activo:
        estado.limitador.registrar_fallo(*claves)
        registrar(db, usuario, "auth.login_fallido", identificador, {"ip": ip})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _CREDENCIALES_INVALIDAS)

    if usuario.totp_activo:
        if entrada.codigo is None:
            # La contraseña es correcta: no cuenta como intento fallido.
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "falta el código de verificación en dos pasos",
                headers={CABECERA_DOS_PASOS: "requerido"},
            )
        if "-" in entrada.codigo:
            valido = _usar_codigo_recuperacion(db, usuario, entrada.codigo)
            if valido:
                registrar(db, usuario, "auth.codigo_recuperacion_usado", usuario.usuario)
        else:
            valido = _codigo_valido(usuario, entrada.codigo, estado.cifrador)
        if not valido:
            estado.limitador.registrar_fallo(*claves)
            registrar(db, usuario, "auth.codigo_fallido", usuario.usuario, {"ip": ip})
            db.commit()
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "código de verificación incorrecto o ya usado",
                headers={CABECERA_DOS_PASOS: "requerido"},
            )

    estado.limitador.limpiar(*claves)
    token, sesion = auth.crear_sesion(
        db, usuario, timedelta(hours=estado.ajustes.duracion_sesion_horas)
    )
    registrar(db, usuario, "auth.login", usuario.usuario, {"ip": ip})
    if request.headers.get("X-Mufa-Cliente") == "web":
        respuesta.set_cookie(
            COOKIE_SESION,
            token,
            max_age=estado.ajustes.duracion_sesion_horas * 3600,
            path="/api",
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
        )
        return LoginSalida(
            token=None, expira=sesion.expira, usuario=UsuarioSalida.model_validate(usuario)
        )
    return LoginSalida(
        token=token, expira=sesion.expira, usuario=UsuarioSalida.model_validate(usuario)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(token: Token, usuario: UsuarioActual, db: DB, respuesta: Response) -> None:
    auth.cerrar_sesion(db, token)
    respuesta.delete_cookie(COOKIE_SESION, path="/api")
    registrar(db, usuario, "auth.logout", usuario.usuario)


@router.get("/yo")
def yo(usuario: UsuarioActual, estado: Estado) -> Yo:
    return Yo(
        **UsuarioSalida.model_validate(usuario).model_dump(),
        dos_pasos_requerido=falta_dos_pasos(usuario, estado),
    )


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_password(entrada: CambioPassword, usuario: UsuarioActual, db: DB) -> None:
    if not auth.verificar_password(usuario.hash_password, entrada.actual):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "la contraseña actual no es correcta")
    try:
        usuario.hash_password = auth.hashear_password(entrada.nueva)
    except auth.PasswordDebil as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    # Cambiar la contraseña cierra todas las sesiones, incluida la actual.
    auth.cerrar_todas_las_sesiones(db, usuario.id)
    registrar(db, usuario, "auth.cambio_password", usuario.usuario)


@router.post("/2fa/iniciar")
def iniciar_dos_pasos(usuario: UsuarioActual, db: DB, estado: Estado) -> DosPasosInicio:
    """Genera un secreto nuevo. No queda activo hasta confirmarlo con un código."""
    if usuario.totp_activo:
        raise HTTPException(status.HTTP_409_CONFLICT, "la verificación en dos pasos ya está activa")
    secreto = dos_pasos.nuevo_secreto()
    usuario.totp_secreto_cifrado = estado.cifrador.cifrar(secreto)
    usuario.totp_ultimo_paso = 0
    registrar(db, usuario, "auth.2fa_iniciar", usuario.usuario)
    return DosPasosInicio(
        secreto=secreto, uri=dos_pasos.uri_de_configuracion(secreto, usuario.usuario)
    )


@router.post("/2fa/confirmar")
def confirmar_dos_pasos(
    entrada: CodigoDosPasos, usuario: UsuarioActual, db: DB, estado: Estado
) -> CodigosRecuperacion:
    if usuario.totp_activo:
        raise HTTPException(status.HTTP_409_CONFLICT, "la verificación en dos pasos ya está activa")
    if usuario.totp_secreto_cifrado is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "primero hay que iniciarla")
    if not _codigo_valido(usuario, entrada.codigo, estado.cifrador):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "código incorrecto")
    usuario.totp_activo = True
    registrar(db, usuario, "auth.2fa_activar", usuario.usuario)
    return CodigosRecuperacion(codigos_recuperacion=_nuevos_codigos(db, usuario))


@router.post("/2fa/codigos-recuperacion")
def regenerar_codigos(
    entrada: DesactivarDosPasos, usuario: UsuarioActual, db: DB, estado: Estado
) -> CodigosRecuperacion:
    """Invalida los códigos anteriores y entrega diez nuevos. Pide contraseña y código."""
    if not usuario.totp_activo:
        raise HTTPException(status.HTTP_409_CONFLICT, "la verificación en dos pasos no está activa")
    if not auth.verificar_password(usuario.hash_password, entrada.password) or not _codigo_valido(
        usuario, entrada.codigo, estado.cifrador
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "contraseña o código incorrectos")
    registrar(db, usuario, "auth.2fa_nuevos_codigos", usuario.usuario)
    return CodigosRecuperacion(codigos_recuperacion=_nuevos_codigos(db, usuario))


@router.post("/2fa/desactivar", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_dos_pasos(
    entrada: DesactivarDosPasos, usuario: UsuarioActual, db: DB, estado: Estado
) -> None:
    if not usuario.totp_activo:
        raise HTTPException(status.HTTP_409_CONFLICT, "la verificación en dos pasos no está activa")
    if not auth.verificar_password(usuario.hash_password, entrada.password) or not _codigo_valido(
        usuario, entrada.codigo, estado.cifrador
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "contraseña o código incorrectos")
    usuario.totp_activo = False
    usuario.totp_secreto_cifrado = None
    registrar(db, usuario, "auth.2fa_desactivar", usuario.usuario)
