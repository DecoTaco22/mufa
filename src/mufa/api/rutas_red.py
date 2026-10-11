"""Herramientas sobre la red real: vigilancia de interfaces, importación al IPAM y a
las VLANs, "¿dónde está?", explorador SNMP y caja de herramientas (ping, traceroute...).
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import threading
import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from mufa import herramientas, importacion, marcas, monitoreo, snmp
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import (
    FilaSnmp,
    Herramienta,
    HerramientaEnVivo,
    ImportarVlans,
    Recorrido,
    RespuestaDonde,
    ResultadoDonde,
    ResultadoImportacionSalida,
    SalidaHerramienta,
    VigilanciaActualizar,
    VigilanciaSalida,
    VigilarInterfaz,
)
from mufa.api.rutas_inventario import obtener_equipo
from mufa.db import DireccionIP, DominioL2, Equipo, InterfazVigilada, MuestraInterfaz, Usuario
from mufa.marcas.base import Adaptador
from mufa.permisos import Permiso
from mufa.servicios import ErrorDeConexion, conectar_y_leer, registrar

router = APIRouter(tags=["red"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Tecnico = Annotated[Usuario, Depends(requiere(Permiso.USAR_CREDENCIALES))]
Diagnostico = Annotated[Usuario, Depends(requiere(Permiso.DIAGNOSTICAR))]
Gestor = Annotated[Usuario, Depends(requiere(Permiso.GESTIONAR_EQUIPOS))]

_CONSULTAS_EN_PARALELO = 8


def _credenciales(equipo: Equipo, estado: Estado) -> snmp.CredencialesSNMP:
    cred = monitoreo.credenciales(equipo, estado.cifrador)
    if cred is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "el equipo no tiene SNMP configurado"
        )
    return cred


# --- Interfaces vigiladas


def _vigilancia(db: DB, vigilancia_id: int) -> InterfazVigilada:
    vigilada = db.get(InterfazVigilada, vigilancia_id)
    if vigilada is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vigilancia no encontrada")
    return vigilada


@router.get("/equipos/{equipo_id}/vigiladas")
def listar_vigiladas(equipo_id: int, _: Lector, db: DB) -> list[VigilanciaSalida]:
    obtener_equipo(db, equipo_id)
    vigiladas = db.scalars(
        select(InterfazVigilada)
        .where(InterfazVigilada.equipo_id == equipo_id)
        .order_by(InterfazVigilada.nombre)
    )
    return [VigilanciaSalida.model_validate(v) for v in vigiladas]


@router.post("/equipos/{equipo_id}/vigiladas", status_code=status.HTTP_201_CREATED)
def vigilar(
    equipo_id: int, entrada: VigilarInterfaz, usuario: Gestor, db: DB, estado: Estado
) -> VigilanciaSalida:
    equipo = obtener_equipo(db, equipo_id)
    if db.scalar(
        select(InterfazVigilada).where(
            InterfazVigilada.equipo_id == equipo_id, InterfazVigilada.if_index == entrada.if_index
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "esa interfaz ya está vigilada")
    plan, _aviso = estado.plan()
    usadas = db.scalar(select(func.count()).select_from(InterfazVigilada)) or 0
    plan.exigir_lugar("interfaces vigiladas", usadas, plan.max_interfaces_vigiladas)
    muestra = db.scalar(
        select(MuestraInterfaz)
        .where(MuestraInterfaz.equipo_id == equipo_id, MuestraInterfaz.if_index == entrada.if_index)
        .order_by(MuestraInterfaz.momento.desc())
        .limit(1)
    )
    if muestra is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "esa interfaz no aparece en el último sondeo del equipo",
        )
    vigilada = InterfazVigilada(
        equipo_id=equipo_id,
        if_index=entrada.if_index,
        nombre=muestra.nombre,
        umbral_saturacion=entrada.umbral_saturacion,
        minutos_saturacion=entrada.minutos_saturacion,
        operativa=muestra.operativa,
    )
    db.add(vigilada)
    db.flush()
    registrar(db, usuario, "interfaz.vigilar", f"{equipo.nombre} · {muestra.nombre}")
    return VigilanciaSalida.model_validate(vigilada)


@router.patch("/vigiladas/{vigilancia_id}")
def actualizar_vigilancia(
    vigilancia_id: int, entrada: VigilanciaActualizar, _: Gestor, db: DB
) -> VigilanciaSalida:
    vigilada = _vigilancia(db, vigilancia_id)
    for campo, valor in entrada.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(vigilada, campo, valor)
    return VigilanciaSalida.model_validate(vigilada)


@router.delete("/vigiladas/{vigilancia_id}", status_code=status.HTTP_204_NO_CONTENT)
def dejar_de_vigilar(vigilancia_id: int, usuario: Gestor, db: DB) -> None:
    vigilada = _vigilancia(db, vigilancia_id)
    registrar(db, usuario, "interfaz.dejar_de_vigilar", vigilada.nombre)
    db.delete(vigilada)


# --- Importar del equipo


@router.post("/equipos/{equipo_id}/importar/ips")
def importar_ips(
    equipo_id: int, usuario: Gestor, db: DB, estado: Estado
) -> ResultadoImportacionSalida:
    """Trae las IPs configuradas en el equipo (por SNMP) y las documenta en el IPAM."""
    equipo = obtener_equipo(db, equipo_id)
    try:
        leidas = snmp.leer_direcciones(equipo.ip_gestion, _credenciales(equipo, estado))
    except snmp.ErrorSNMP as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from None
    resultado = importacion.importar_direcciones(db, equipo, leidas)
    registrar(
        db,
        usuario,
        "ipam.importar",
        equipo.nombre,
        {"nuevas": resultado.nuevas, "conflictos": len(resultado.conflictos)},
    )
    return ResultadoImportacionSalida(**vars(resultado), fuente="SNMP")


@router.post("/equipos/{equipo_id}/importar/vlans")
def importar_vlans(
    equipo_id: int, entrada: ImportarVlans, usuario: Gestor, db: DB, estado: Estado
) -> ResultadoImportacionSalida:
    """Trae las VLANs del equipo: por su acceso (SSH/API) si la marca lo permite, si no por SNMP."""
    equipo = obtener_equipo(db, equipo_id)
    dominio = db.get(DominioL2, entrada.dominio_id)
    if dominio is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "el dominio no existe")

    adaptador = marcas.ADAPTADORES.get(equipo.marca)
    leidas: list[snmp.VlanEnEquipo] | None = None
    fuente = "SNMP"
    try:
        lee_por_acceso = adaptador is not None and (
            type(adaptador).leer_vlans is not Adaptador.leer_vlans
        )
        if adaptador is not None and lee_por_acceso and equipo.usuario_ssh:
            leidas = conectar_y_leer(
                equipo,
                estado.cifrador,
                estado.ajustes.known_hosts,
                10.0,
                adaptador.leer_vlans,
            )
            fuente = "API" if equipo.acceso != "ssh" else "SSH"
        if leidas is None:
            leidas = snmp.leer_vlans(equipo.ip_gestion, _credenciales(equipo, estado))
            fuente = "SNMP"
    except (ErrorDeConexion, snmp.ErrorSNMP) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from None
    if not leidas and fuente == "SNMP" and equipo.marca == "mikrotik":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "MikroTik no publica los números de VLAN por SNMP: configura el acceso "
            "(SSH o API) del equipo para importarlas",
        )
    resultado = importacion.importar_vlans(db, equipo, dominio, leidas)
    registrar(
        db,
        usuario,
        "vlan.importar",
        equipo.nombre,
        {"dominio": dominio.nombre, "nuevas": resultado.nuevas},
    )
    return ResultadoImportacionSalida(**vars(resultado), fuente=fuente)


# --- ¿Dónde está?

_SEPARADORES_MAC = re.compile(r"[^0-9A-Fa-f]")


def _como_mac(texto: str) -> str | None:
    limpio = _SEPARADORES_MAC.sub("", texto)
    if len(limpio) != 12:
        return None
    return ":".join(limpio[i : i + 2] for i in range(0, 12, 2)).upper()


@router.get("/donde")
def donde(q: str, _: Diagnostico, db: DB, estado: Estado) -> RespuestaDonde:
    """Busca una IP o una MAC en las tablas ARP y de bridge de los equipos, y en el IPAM."""
    consulta = q.strip()
    mac = _como_mac(consulta)
    ip: str | None = None
    if mac is None:
        try:
            ip = str(ipaddress.ip_address(consulta))
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "escribe una IP o una MAC"
            ) from None

    resultados: list[ResultadoDonde] = []
    if ip is not None:
        for direccion, equipo in db.execute(
            select(DireccionIP, Equipo)
            .join(Equipo, Equipo.id == DireccionIP.equipo_id)
            .where(DireccionIP.ip == ip)
        ):
            resultados.append(
                ResultadoDonde(
                    equipo_id=equipo.id,
                    equipo=equipo.nombre,
                    interfaz=direccion.interfaz,
                    ip=ip,
                    mac="",
                    fuente="ipam",
                )
            )

    equipos = [
        (e, cred)
        for e in db.scalars(select(Equipo).where(Equipo.snmp_version != ""))
        if (cred := monitoreo.credenciales(e, estado.cifrador)) is not None
    ]

    def consultar(par: tuple[Equipo, snmp.CredencialesSNMP]) -> list[snmp.Ubicacion] | str:
        equipo, cred = par
        try:
            return snmp.leer_vecinos(equipo.ip_gestion, cred)
        except snmp.ErrorSNMP as error:
            return str(error)

    sin_respuesta = []
    with ThreadPoolExecutor(_CONSULTAS_EN_PARALELO) as grupo:
        for (equipo, _cred), vistas in zip(equipos, grupo.map(consultar, equipos), strict=True):
            if isinstance(vistas, str):
                sin_respuesta.append(f"{equipo.nombre}: {vistas}")
                continue
            for vista in vistas:
                if (ip is not None and vista.ip == ip) or (mac is not None and vista.mac == mac):
                    resultados.append(
                        ResultadoDonde(
                            equipo_id=equipo.id,
                            equipo=equipo.nombre,
                            interfaz=vista.interfaz,
                            ip=vista.ip,
                            mac=vista.mac,
                            fuente=vista.fuente,
                        )
                    )
    return RespuestaDonde(
        consulta=mac or ip or consulta, resultados=resultados, sin_respuesta=sin_respuesta
    )


# --- Explorador SNMP


@router.post("/equipos/{equipo_id}/snmp/recorrer")
def recorrer_snmp(
    equipo_id: int, entrada: Recorrido, _: Tecnico, db: DB, estado: Estado
) -> list[FilaSnmp]:
    equipo = obtener_equipo(db, equipo_id)
    try:
        filas = snmp.recorrer(
            equipo.ip_gestion, _credenciales(equipo, estado), entrada.oid.lstrip(".")
        )
    except snmp.ErrorSNMP as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from None
    return [FilaSnmp(oid=oid, valor=valor) for oid, valor in filas]


# --- Caja de herramientas


def _herramienta(funcion: object, *argumentos: object) -> SalidaHerramienta:
    try:
        salida: herramientas.Salida = funcion(*argumentos)  # type: ignore[operator]
    except herramientas.DestinoInvalido as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except herramientas.Ocupado as error:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from None
    return SalidaHerramienta(ok=salida.ok, texto=salida.texto, segundos=salida.segundos)


@router.post("/herramientas/ping")
def ping(entrada: Herramienta, _: Diagnostico) -> SalidaHerramienta:
    return _herramienta(herramientas.ping, entrada.destino)


@router.post("/herramientas/traceroute")
def traceroute(entrada: Herramienta, _: Diagnostico) -> SalidaHerramienta:
    return _herramienta(herramientas.traceroute, entrada.destino)


@router.post("/herramientas/dns")
def dns(entrada: Herramienta, _: Diagnostico) -> SalidaHerramienta:
    return _herramienta(herramientas.dns, entrada.destino)


@router.post("/herramientas/puerto")
def puerto(entrada: Herramienta, _: Diagnostico) -> SalidaHerramienta:
    if entrada.puerto is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "falta el puerto")
    return _herramienta(herramientas.puerto, entrada.destino, entrada.puerto)


# Última línea de una salida en vivo: "\x1e<código de salida>" (el separador no aparece en
# la salida de ping/traceroute). La app la usa para saber cómo terminó.
FIN_EN_VIVO = "\x1e"


async def _transmitir(request: Request, proceso: herramientas.EnVivo) -> AsyncIterator[str]:
    """Pasa cada línea al navegador apenas el programa la escribe; si se cierra la pestaña
    o se pulsa Detener, corta el programa."""
    cola: asyncio.Queue[str | None] = asyncio.Queue()
    bucle = asyncio.get_running_loop()

    def leer() -> None:
        try:
            for linea in proceso.lineas():
                bucle.call_soon_threadsafe(cola.put_nowait, linea)
        finally:
            bucle.call_soon_threadsafe(cola.put_nowait, None)

    threading.Thread(target=leer, name="herramienta-en-vivo", daemon=True).start()
    limite = time.monotonic() + herramientas.MAXIMO_EN_VIVO
    with proceso:
        while True:
            try:
                linea = await asyncio.wait_for(cola.get(), 1.0)
            except TimeoutError:
                if await request.is_disconnected():
                    return
                if time.monotonic() > limite:
                    proceso.cortar()
                    yield "\n(se cortó a los 10 minutos)\n"
                continue
            if linea is None:
                break
            yield linea
        proceso.cortar()
        yield f"{FIN_EN_VIVO}{proceso.codigo if proceso.codigo is not None else -1}"


@router.post("/herramientas/{herramienta}/en-vivo")
def en_vivo(
    herramienta: str, entrada: HerramientaEnVivo, request: Request, _: Diagnostico
) -> StreamingResponse:
    """Ping o traceroute con la salida en vivo, como en una terminal."""
    try:
        if herramienta == "ping":
            comando = herramientas.comando_ping(entrada.destino, entrada.cantidad)
        elif herramienta == "traceroute":
            comando = herramientas.comando_traceroute(entrada.destino)
        else:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "herramienta desconocida")
        proceso = herramientas.EnVivo(comando)
    except herramientas.DestinoInvalido as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except herramientas.Ocupado as error:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from None
    return StreamingResponse(
        _transmitir(request, proceso),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no"},
    )
