"""Salud, marcas soportadas, licencia y registro de eventos."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select

from mufa import __version__, actualizacion, auth, licencia, marcas, primera_vez, traslado
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import (
    ActualizacionAjustes,
    ActualizacionSalida,
    ArchivoExportado,
    EstadoInicial,
    EventoSalida,
    ExportarDatos,
    LicenciaInstalar,
    LicenciaSalida,
    MarcaSalida,
    PrimerAdmin,
    VersionNueva,
)
from mufa.db import Equipo, Evento, Usuario, ahora
from mufa.permisos import Permiso, Rol
from mufa.servicios import registrar

router = APIRouter(tags=["sistema"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Admin = Annotated[Usuario, Depends(requiere(Permiso.ADMINISTRAR_USUARIOS))]
Revisor = Annotated[Usuario, Depends(requiere(Permiso.VER_REGISTRO))]

# Un archivo de traslado con meses de tráfico de cientos de interfaces no llega a esto.
TAMANO_MAXIMO_TRASLADO = 512 * 1024 * 1024


@router.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok", "version": __version__}


@router.get("/sistema/inicial")
def estado_inicial(db: DB, estado: Estado) -> EstadoInicial:
    """Público: la app web lo usa para mostrar el asistente de primera vez."""
    motor = estado.sesiones.kw["bind"]
    return EstadoInicial(
        necesita_admin=not primera_vez.hay_usuarios(db),
        puede_importar=traslado.ruta_sqlite(motor) is not None,
    )


@router.post("/sistema/inicial", status_code=status.HTTP_201_CREATED)
def crear_primer_admin(
    entrada: PrimerAdmin, request: Request, db: DB, estado: Estado
) -> dict[str, str]:
    if primera_vez.hay_usuarios(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "mufa ya tiene administrador")
    _token_de_primera_vez(entrada.token, request, estado)
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


def _token_de_primera_vez(token: str, request: Request, estado: Estado) -> None:
    clave = f"inicial:{request.client.host if request.client else ''}"
    if estado.limitador.bloqueado(clave):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "demasiados intentos")
    if not primera_vez.token_valido(estado.token_inicial, token):
        estado.limitador.registrar_fallo(clave)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "el token no es correcto: está en la consola del servidor o en "
            f"{primera_vez.NOMBRE_ARCHIVO}, en el directorio de datos",
        )


@router.post("/sistema/exportar")
def exportar_datos(
    entrada: ExportarDatos, admin: Admin, db: DB, estado: Estado
) -> ArchivoExportado:
    """Todos los datos en un archivo cifrado con la frase, para llevarlos a otra computadora."""
    ruta = traslado.ruta_sqlite(estado.sesiones.kw["bind"])
    if ruta is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "con PostgreSQL se respalda la base de datos del servidor (pg_dump) y el archivo "
            "secreto.key",
        )
    if not auth.verificar_password(admin.hash_password, entrada.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "la contraseña no es correcta")
    try:
        contenido = traslado.exportar(ruta, estado.ajustes.dir_datos, entrada.frase)
    except traslado.ErrorDeTraslado as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    registrar(db, admin, "sistema.exportar_datos")
    return ArchivoExportado(
        nombre=f"mufa-{ahora():%Y-%m-%d}{traslado.EXTENSION}", contenido=contenido
    )


@router.post("/sistema/importar", status_code=status.HTTP_201_CREATED)
async def importar_datos(
    request: Request,
    estado: Estado,
    archivo: Annotated[UploadFile, File(description="Archivo .mufa de la otra computadora")],
    frase: Annotated[str, Form(max_length=256)],
    token: Annotated[str, Form(max_length=200)] = "",
) -> dict[str, int]:
    """En una instalación nueva (sin usuarios), trae los datos de otra computadora."""
    with estado.sesiones() as db:
        if primera_vez.hay_usuarios(db):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "mufa ya tiene cuentas en esta computadora"
            )
    _token_de_primera_vez(token, request, estado)
    contenido = await archivo.read(TAMANO_MAXIMO_TRASLADO + 1)
    if len(contenido) > TAMANO_MAXIMO_TRASLADO:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "el archivo es demasiado grande")
    motor = estado.sesiones.kw["bind"]
    try:
        # scrypt y la copia de la base tardan: fuera del hilo del servidor.
        clave = await asyncio.to_thread(
            traslado.importar,
            contenido.decode("ascii", errors="replace"),
            frase,
            motor,
            estado.ajustes.dir_datos,
        )
    except traslado.ErrorDeTraslado as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    estado.cifrador.cambiar_clave(clave)
    estado.token_inicial = None
    primera_vez.descartar(estado.ajustes.dir_datos)
    with estado.sesiones() as db:
        usuarios = db.scalar(select(func.count()).select_from(Usuario)) or 0
        registrar(
            db, None, "sistema.importar_datos", archivo.filename or "", {"usuarios": usuarios}
        )
        db.commit()
    return {"usuarios": usuarios}


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
    estado.pro.cargar(plan.llaves_pro)
    return _licencia(db, estado)


def _actualizador(estado: Estado) -> actualizacion.Actualizador:
    if estado.actualizador is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sin actualizaciones")
    return estado.actualizador


def _actualizacion(db: DB, estado: Estado) -> ActualizacionSalida:
    a = _actualizador(estado)
    nueva = a.nueva
    return ActualizacionSalida(
        version_actual=a.version_actual,
        modo=a.modo.value,
        buscar=a.busca and actualizacion.buscar_activado(db),
        revisada=a.revisada,
        nueva=VersionNueva(version=nueva.version, publicada=nueva.publicada, notas=nueva.notas)
        if nueva
        else None,
        puede_instalar=a.archivo is not None,
        estado=a.estado,
        error=a.error,
        pasos=a.pasos,
        url_versiones=actualizacion.URL_VERSIONES,
    )


@router.get("/sistema/actualizacion")
def ver_actualizacion(_: Lector, db: DB, estado: Estado) -> ActualizacionSalida:
    return _actualizacion(db, estado)


@router.put("/sistema/actualizacion")
def ajustar_actualizacion(
    entrada: ActualizacionAjustes, admin: Admin, db: DB, estado: Estado
) -> ActualizacionSalida:
    actualizacion.cambiar_buscar(db, entrada.buscar)
    registrar(db, admin, "sistema.buscar_actualizaciones", "sí" if entrada.buscar else "no")
    db.flush()
    return _actualizacion(db, estado)


@router.post("/sistema/actualizacion/buscar")
async def buscar_actualizacion(_: Admin, db: DB, estado: Estado) -> ActualizacionSalida:
    a = _actualizador(estado)
    if not a.busca:
        raise HTTPException(status.HTTP_409_CONFLICT, "esta instalación no busca actualizaciones")
    await asyncio.to_thread(a.buscar)
    return _actualizacion(db, estado)


@router.post("/sistema/actualizacion/instalar", status_code=status.HTTP_202_ACCEPTED)
def instalar_actualizacion(admin: Admin, db: DB, estado: Estado) -> ActualizacionSalida:
    a = _actualizador(estado)
    nueva = a.nueva
    try:
        a.instalar_en_segundo_plano()
    except RuntimeError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    registrar(db, admin, "sistema.actualizar", nueva.version if nueva else "")
    return _actualizacion(db, estado)


@router.get("/eventos")
def listar_eventos(_: Revisor, db: DB, limite: int = 100) -> list[EventoSalida]:
    consulta = select(Evento).order_by(Evento.id.desc()).limit(min(max(limite, 1), 1000))
    return [EventoSalida.model_validate(e) for e in db.scalars(consulta)]
