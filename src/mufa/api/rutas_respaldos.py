"""Respaldos de configuración y diferencias entre versiones."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from mufa import copias, marcas, respaldos
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import (
    DestinoEntrada,
    DestinoSalida,
    Diferencias,
    EquipoEnRespaldos,
    ProgramaRespaldos,
    PruebaDestino,
    RespaldoConContenido,
    RespaldoSalida,
    ResultadoEnvioSalida,
    ResultadoRespaldo,
    ResumenRespaldos,
    UltimoEnvioSalida,
)
from mufa.api.rutas_inventario import obtener_equipo
from mufa.db import Equipo, Evento, Respaldo, Usuario
from mufa.permisos import Permiso
from mufa.servicios import ErrorDeConexion, registrar

router = APIRouter(tags=["respaldos"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
# El contenido de una configuración es sensible: lo ve quien puede usar credenciales.
Tecnico = Annotated[Usuario, Depends(requiere(Permiso.USAR_CREDENCIALES))]
Ingeniero = Annotated[Usuario, Depends(requiere(Permiso.GESTIONAR_EQUIPOS))]
# Mandar las configuraciones fuera de mufa es como las alertas: Senior y Admin.
Senior = Annotated[Usuario, Depends(requiere(Permiso.CONFIGURAR_ALERTAS))]

_RESULTADOS = ("respaldo.nuevo", "respaldo.sin_cambios", "respaldo.error")


def _obtener(db: DB, respaldo_id: int) -> Respaldo:
    respaldo = db.get(Respaldo, respaldo_id)
    if respaldo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "respaldo no encontrado")
    return respaldo


@router.post("/equipos/{equipo_id}/respaldar")
def respaldar(equipo_id: int, usuario: Tecnico, db: DB, estado: Estado) -> ResultadoRespaldo:
    equipo = obtener_equipo(db, equipo_id)
    if equipo.marca not in marcas.RESPALDADORES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"todavía no se sabe respaldar {equipo.marca!r}: solo se monitorea por SNMP",
        )
    if not equipo.usuario_ssh:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "el equipo no tiene usuario de acceso (SSH o API) configurado",
        )
    try:
        resultado = respaldos.respaldar_equipo(
            db, equipo, usuario, "manual", estado.cifrador, estado.ajustes.known_hosts
        )
    except ErrorDeConexion as error:
        db.commit()  # que el intento fallido quede en el registro de eventos
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from None
    return ResultadoRespaldo(
        respaldo=RespaldoSalida.model_validate(resultado.respaldo), cambio=resultado.cambio
    )


@router.get("/equipos/{equipo_id}/respaldos")
def listar(equipo_id: int, _: Lector, db: DB) -> list[RespaldoSalida]:
    obtener_equipo(db, equipo_id)
    consulta = select(Respaldo).where(Respaldo.equipo_id == equipo_id).order_by(Respaldo.id.desc())
    return [RespaldoSalida.model_validate(r) for r in db.scalars(consulta)]


@router.get("/respaldos/{respaldo_id}")
def ver(respaldo_id: int, usuario: Tecnico, db: DB, estado: Estado) -> RespaldoConContenido:
    respaldo = _obtener(db, respaldo_id)
    registrar(db, usuario, "respaldo.ver", str(respaldo.id), {"equipo_id": respaldo.equipo_id})
    return RespaldoConContenido(
        **RespaldoSalida.model_validate(respaldo).model_dump(),
        contenido=respaldos.contenido(respaldo, estado.cifrador),
    )


@router.get("/respaldos/{respaldo_id}/diferencias")
def diferencias(
    respaldo_id: int, _: Tecnico, db: DB, estado: Estado, contra: int | None = None
) -> Diferencias:
    """Qué cambió desde `contra` (por defecto, la versión anterior del mismo equipo)."""
    posterior = _obtener(db, respaldo_id)
    if contra is None:
        anterior = db.scalar(
            select(Respaldo)
            .where(Respaldo.equipo_id == posterior.equipo_id, Respaldo.id < posterior.id)
            .order_by(Respaldo.id.desc())
            .limit(1)
        )
        if anterior is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "es la primera versión del equipo")
    else:
        anterior = _obtener(db, contra)
        if anterior.equipo_id != posterior.equipo_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "los respaldos son de equipos distintos"
            )
    equipo = db.get(Equipo, posterior.equipo_id)
    marca = equipo.marca if equipo else ""
    return Diferencias(
        desde=anterior.id,
        hasta=posterior.id,
        diferencias=respaldos.diferencias(
            marca,
            respaldos.contenido(anterior, estado.cifrador),
            respaldos.contenido(posterior, estado.cifrador),
            f"respaldo {anterior.id}",
            f"respaldo {posterior.id}",
        ),
    )


def _destino_salida(destino: copias.Destino) -> DestinoSalida:
    return DestinoSalida(
        activo=destino.activo,
        protocolo=destino.protocolo,
        host=destino.host,
        puerto=destino.puerto,
        usuario=destino.usuario,
        tiene_password=bool(destino.password_cifrada),
        carpeta=destino.carpeta,
        organizar=destino.organizar,
        verificar_certificado=destino.verificar_certificado,
    )


def _estado_de_equipos(db: DB) -> list[EquipoEnRespaldos]:
    versiones = dict(
        db.execute(select(Respaldo.equipo_id, func.count()).group_by(Respaldo.equipo_id)).all()
    )
    ultimos = dict(
        db.execute(
            select(Respaldo.equipo_id, func.max(Respaldo.confirmado)).group_by(Respaldo.equipo_id)
        ).all()
    )
    # El último resultado de cada equipo (por nombre, como queda en el registro).
    resultados: dict[str, Evento] = {}
    for evento in db.scalars(
        select(Evento).where(Evento.accion.in_(_RESULTADOS)).order_by(Evento.id.desc()).limit(2000)
    ):
        resultados.setdefault(evento.objeto, evento)

    filas = []
    for equipo in db.scalars(select(Equipo).order_by(Equipo.nombre)):
        ultimo = resultados.get(equipo.nombre)
        error = ""
        if equipo.marca not in marcas.RESPALDADORES:
            estado = "sin_soporte"
        elif not equipo.usuario_ssh:
            estado = "sin_acceso"
        elif ultimo is not None and ultimo.accion == "respaldo.error":
            estado = "error"
            error = str(ultimo.detalle.get("error", ""))
        elif equipo.id in ultimos:
            estado = "ok"
        else:
            estado = "pendiente"
        filas.append(
            EquipoEnRespaldos(
                id=equipo.id,
                nombre=equipo.nombre,
                marca=equipo.marca,
                estado=estado,
                ultimo=ultimos.get(equipo.id),
                versiones=versiones.get(equipo.id, 0),
                error=error,
            )
        )
    return filas


@router.get("/respaldos")
def resumen(_: Lector, db: DB, estado: Estado) -> ResumenRespaldos:
    """Todo lo de la sección Respaldos: horario, servidor de copia y estado de cada equipo."""
    momento = respaldos.hora_local()
    programa = respaldos.leer_programa(db)
    envio = copias.leer_ultimo_envio(db)
    automaticos = estado.ajustes.intervalo_respaldo_horas > 0
    return ResumenRespaldos(
        programa=ProgramaRespaldos(
            activo=programa.activo, hora=programa.hora, secretos=programa.secretos
        ),
        proximo=respaldos.proximo_respaldo(db, momento) if automaticos else None,
        hora_servidor=momento,
        zona=momento.tzname() or "",
        respaldando=bool(estado.programador and estado.programador.respaldando),
        destino=_destino_salida(copias.leer_destino(db)),
        ultimo_envio=UltimoEnvioSalida(
            cuando=datetime.fromisoformat(envio.cuando),
            ok=envio.ok,
            archivos=envio.archivos,
            mensaje=envio.mensaje,
        )
        if envio and envio.cuando
        else None,
        equipos=_estado_de_equipos(db),
    )


@router.put("/respaldos/programa")
def cambiar_programa(datos: ProgramaRespaldos, usuario: Ingeniero, db: DB) -> ProgramaRespaldos:
    respaldos.guardar_programa(
        db, respaldos.Programa(activo=datos.activo, hora=datos.hora, secretos=datos.secretos)
    )
    registrar(
        db,
        usuario,
        "respaldo.programa",
        datos.hora,
        {"activo": datos.activo, "secretos": datos.secretos},
    )
    return datos


@router.post("/respaldos/ejecutar", status_code=status.HTTP_202_ACCEPTED)
def respaldar_todo(usuario: Ingeniero, db: DB, estado: Estado) -> dict[str, bool]:
    """Respalda todos los equipos ahora, en segundo plano. La página consulta el avance."""
    if estado.programador is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "las tareas no están disponibles")
    iniciado = estado.programador.respaldar_en_segundo_plano()
    if iniciado:
        registrar(db, usuario, "respaldo.todos")
    return {"iniciado": iniciado}


def _destino_desde(datos: DestinoEntrada, actual: copias.Destino, estado: Estado) -> copias.Destino:
    try:
        carpeta = copias.carpeta_valida(datos.carpeta) or "/"
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if datos.activo and not datos.host:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "falta la IP del servidor")
    if datos.password is None:
        password_cifrada = actual.password_cifrada
    else:
        password_cifrada = estado.cifrador.cifrar(datos.password) if datos.password else ""
    return copias.Destino(
        activo=datos.activo,
        protocolo=datos.protocolo,
        host=datos.host,
        puerto=datos.puerto,
        usuario=datos.usuario,
        password_cifrada=password_cifrada,
        carpeta=carpeta,
        organizar=datos.organizar,
        verificar_certificado=datos.verificar_certificado,
    )


@router.put("/respaldos/destino")
def guardar_destino(
    datos: DestinoEntrada, usuario: Senior, db: DB, estado: Estado
) -> DestinoSalida:
    destino = _destino_desde(datos, copias.leer_destino(db), estado)
    copias.guardar_destino(db, destino)
    registrar(
        db,
        usuario,
        "respaldo.destino",
        f"{destino.protocolo}://{destino.host}",
        {"activo": destino.activo, "carpeta": destino.carpeta},
    )
    return _destino_salida(destino)


@router.post("/respaldos/destino/probar")
def probar_destino(datos: DestinoEntrada, _: Senior, db: DB, estado: Estado) -> PruebaDestino:
    """Entra al servidor con lo que está en el formulario (aunque no se haya guardado)."""
    destino = _destino_desde(datos, copias.leer_destino(db), estado)
    password = (
        estado.cifrador.descifrar(destino.password_cifrada) if destino.password_cifrada else ""
    )
    try:
        huella = copias.probar(destino, password, estado.ajustes.known_hosts)
    except copias.ErrorDeCopia as error:
        return PruebaDestino(ok=False, mensaje=str(error))
    return PruebaDestino(
        ok=True,
        mensaje=f"Conexión correcta: la carpeta {destino.carpeta} está lista.",
        huella=huella,
    )


@router.post("/respaldos/enviar")
def enviar_ahora(usuario: Senior, db: DB, estado: Estado) -> ResultadoEnvioSalida:
    """Sube ya la última versión de cada equipo al servidor configurado."""
    try:
        resultado = copias.enviar(
            db, estado.cifrador, estado.ajustes.known_hosts, usuario, respaldos.hora_local()
        )
    except copias.ErrorDeCopia as error:
        db.commit()  # que el intento quede en el registro
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from None
    return ResultadoEnvioSalida(archivos=resultado.archivos, rutas=resultado.rutas)
