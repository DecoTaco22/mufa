"""Monitoreo por SNMP: estado de cada equipo y tráfico de sus interfaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mufa import alcance, snmp
from mufa.cifrado import Cifrador
from mufa.db import Equipo, EstadoEquipo, InterfazVigilada, MuestraInterfaz, ahora, como_utc
from mufa.servicios import registrar

Sondeo = Callable[[str, snmp.CredencialesSNMP, float], snmp.ResultadoSondeo]
Alcance = Callable[[str, list[int]], str]

# sysUpTime se cuenta en centésimas en 32 bits: vuelve a cero a los ~497 días
# sin que el equipo se haya reiniciado. Cerca de ese punto no se avisa.
_DESBORDE_UPTIME = 2**32 // 100


def credenciales(equipo: Equipo, cifrador: Cifrador) -> snmp.CredencialesSNMP | None:
    if equipo.snmp_version == "3":
        return snmp.CredencialesSNMP(
            version="3",
            puerto=equipo.snmp_puerto,
            usuario=equipo.snmp_usuario,
            clave_auth=cifrador.descifrar(equipo.snmp_auth_cifrada or ""),
            clave_priv=cifrador.descifrar(equipo.snmp_priv_cifrada or ""),
            protocolo_auth=equipo.snmp_protocolo_auth,
            protocolo_priv=equipo.snmp_protocolo_priv,
        )
    if equipo.snmp_version == "2c":
        return snmp.CredencialesSNMP(
            version="2c",
            puerto=equipo.snmp_puerto,
            comunidad=cifrador.descifrar(equipo.snmp_comunidad_cifrada or ""),
        )
    return None


def sondear_equipo(
    db: Session,
    equipo: Equipo,
    cifrador: Cifrador,
    timeout: float = 2.0,
    sondeo: Sondeo = snmp.sondear,
    verificar_alcance: Alcance = alcance.verificar,
) -> EstadoEquipo:
    """Sondea, guarda el estado y una muestra por interfaz. Registra caídas y recuperaciones."""
    cred = credenciales(equipo, cifrador)
    if cred is None:
        raise ValueError("el equipo no tiene SNMP configurado")

    estado = db.get(EstadoEquipo, equipo.id)
    primer_sondeo = estado is None
    if estado is None:
        estado = EstadoEquipo(equipo_id=equipo.id, en_linea=False)
        db.add(estado)
    estaba_en_linea = estado.en_linea
    momento = ahora()
    estado.ultimo_sondeo = momento

    try:
        resultado = sondeo(equipo.ip_gestion, cred, timeout)
    except snmp.ErrorSNMP as error:
        estado.en_linea = False
        via = verificar_alcance(equipo.ip_gestion, [equipo.puerto_ssh])
        estado.alcanzable = bool(via)
        estado.error = (
            f"El equipo está encendido (responde a {via}), pero SNMP no. {error}"
            if via
            else str(error)
        )
        if estaba_en_linea:
            registrar(db, None, "equipo.caido", equipo.nombre, {"error": str(error)})
        db.flush()
        return estado

    _detectar_reinicio(db, equipo, estado.uptime_segundos, resultado.uptime_segundos)
    _actualizar_identidad(db, equipo, estado, resultado)
    _vigilar_interfaces(db, equipo, resultado.interfaces, momento)

    estado.en_linea = True
    estado.alcanzable = True
    estado.error = ""
    estado.ultimo_en_linea = momento
    estado.sys_nombre = resultado.nombre
    estado.sys_descripcion = resultado.descripcion
    estado.sys_object_id = resultado.object_id
    estado.marca_detectada = resultado.marca_detectada
    estado.uptime_segundos = resultado.uptime_segundos
    for interfaz in resultado.interfaces:
        db.add(
            MuestraInterfaz(
                equipo_id=equipo.id,
                momento=momento,
                if_index=interfaz.if_index,
                nombre=interfaz.nombre,
                operativa=interfaz.operativa,
                velocidad_mbps=interfaz.velocidad_mbps,
                octetos_entrada=interfaz.octetos_entrada,
                octetos_salida=interfaz.octetos_salida,
            )
        )
    if not estaba_en_linea and not primer_sondeo:
        registrar(db, None, "equipo.recuperado", equipo.nombre)
    db.flush()
    return estado


def _detectar_reinicio(
    db: Session, equipo: Equipo, anterior: int | None, actual: int | None
) -> None:
    if anterior is None or actual is None or actual >= anterior:
        return
    if anterior > _DESBORDE_UPTIME - 86_400:
        return
    registrar(
        db,
        None,
        "equipo.reinicio",
        equipo.nombre,
        {"encendido_hace": f"{actual // 60} min", "estaba_encendido": f"{anterior // 86_400} días"},
    )


def _actualizar_identidad(
    db: Session, equipo: Equipo, estado: EstadoEquipo, resultado: snmp.ResultadoSondeo
) -> None:
    """Guarda lo leído por SNMP y completa la ficha del equipo si estaba vacía."""
    if estado.serie and resultado.serie and resultado.serie != estado.serie:
        # Otro equipo con la misma IP: un reemplazo, o alguien suplantándolo.
        registrar(
            db,
            None,
            "equipo.cambio_serie",
            equipo.nombre,
            {"antes": estado.serie, "ahora": resultado.serie},
        )
    estado.ubicacion = resultado.ubicacion
    estado.serie = resultado.serie
    estado.modelo = resultado.modelo
    estado.version = resultado.version
    if not equipo.modelo and resultado.modelo:
        equipo.modelo = resultado.modelo[:120]
    if not equipo.numero_serie and resultado.serie:
        equipo.numero_serie = resultado.serie[:120]


def uso_porcentual(
    anterior: MuestraInterfaz | None, actual: snmp.Interfaz, momento: datetime
) -> float | None:
    """Uso de la interfaz (el mayor entre entrada y salida) en % de su velocidad."""
    if anterior is None or not actual.velocidad_mbps:
        return None
    segundos = (como_utc(momento) - como_utc(anterior.momento)).total_seconds()
    tasas = [
        _tasa(anterior.octetos_entrada, actual.octetos_entrada, segundos),
        _tasa(anterior.octetos_salida, actual.octetos_salida, segundos),
    ]
    validas = [t for t in tasas if t is not None]
    if not validas:
        return None
    return max(validas) * 100 / (actual.velocidad_mbps * 1_000_000)


def _vigilar_interfaces(
    db: Session, equipo: Equipo, interfaces: list[snmp.Interfaz], momento: datetime
) -> None:
    """Avisa cuando una interfaz vigilada cambia de estado o pasa su umbral de saturación."""
    vigiladas = list(
        db.scalars(select(InterfazVigilada).where(InterfazVigilada.equipo_id == equipo.id))
    )
    if not vigiladas:
        return
    actuales = {i.if_index: i for i in interfaces}
    previo = db.scalar(
        select(MuestraInterfaz.momento)
        .where(MuestraInterfaz.equipo_id == equipo.id, MuestraInterfaz.momento < momento)
        .order_by(MuestraInterfaz.momento.desc())
        .limit(1)
    )
    anteriores = (
        {
            m.if_index: m
            for m in db.scalars(
                select(MuestraInterfaz).where(
                    MuestraInterfaz.equipo_id == equipo.id, MuestraInterfaz.momento == previo
                )
            )
        }
        if previo is not None
        else {}
    )
    for vigilada in vigiladas:
        actual = actuales.get(vigilada.if_index)
        if actual is None:
            continue
        vigilada.nombre = actual.nombre
        objeto = f"{equipo.nombre} · {actual.nombre}"
        if vigilada.operativa is not None and vigilada.operativa != actual.operativa:
            registrar(
                db, None, "interfaz.recuperada" if actual.operativa else "interfaz.caida", objeto
            )
        vigilada.operativa = actual.operativa

        uso = uso_porcentual(anteriores.get(vigilada.if_index), actual, momento)
        if uso is None:
            continue
        if uso >= vigilada.umbral_saturacion:
            if vigilada.saturada_desde is None:
                vigilada.saturada_desde = momento
            sostenida = como_utc(momento) - como_utc(vigilada.saturada_desde)
            if not vigilada.aviso_saturacion and sostenida >= timedelta(
                minutes=vigilada.minutos_saturacion
            ):
                registrar(
                    db,
                    None,
                    "interfaz.saturada",
                    objeto,
                    {
                        "uso": f"{uso:.0f} % de {actual.velocidad_mbps} Mbps",
                        "umbral": f"{vigilada.umbral_saturacion} %",
                        "durante": f"{int(sostenida.total_seconds() // 60)} min",
                    },
                )
                vigilada.aviso_saturacion = True
        else:
            if vigilada.aviso_saturacion:
                registrar(db, None, "interfaz.normal", objeto, {"uso": f"{uso:.0f} %"})
            vigilada.saturada_desde = None
            vigilada.aviso_saturacion = False


@dataclass
class TraficoInterfaz:
    if_index: int
    nombre: str
    operativa: bool
    velocidad_mbps: int | None
    bps_entrada: float | None
    bps_salida: float | None


def _tasa(antes: int, despues: int, segundos: float) -> float | None:
    # Un contador que baja es un reinicio del equipo o un desborde: no hay tasa.
    if segundos <= 0 or despues < antes:
        return None
    return (despues - antes) * 8 / segundos


def trafico(db: Session, equipo_id: int) -> list[TraficoInterfaz]:
    """Estado de cada interfaz y su tráfico entre las dos últimas muestras."""
    momentos = list(
        db.scalars(
            select(MuestraInterfaz.momento)
            .where(MuestraInterfaz.equipo_id == equipo_id)
            .distinct()
            .order_by(MuestraInterfaz.momento.desc())
            .limit(2)
        )
    )
    if not momentos:
        return []
    muestras = db.scalars(
        select(MuestraInterfaz).where(
            MuestraInterfaz.equipo_id == equipo_id, MuestraInterfaz.momento.in_(momentos)
        )
    )
    ultima: dict[int, MuestraInterfaz] = {}
    previa: dict[int, MuestraInterfaz] = {}
    for muestra in muestras:
        destino = ultima if muestra.momento == momentos[0] else previa
        destino[muestra.if_index] = muestra

    resultado = []
    for indice in sorted(ultima):
        actual, anterior = ultima[indice], previa.get(indice)
        segundos = (
            (como_utc(actual.momento) - como_utc(anterior.momento)).total_seconds()
            if anterior
            else 0
        )
        resultado.append(
            TraficoInterfaz(
                if_index=indice,
                nombre=actual.nombre,
                operativa=actual.operativa,
                velocidad_mbps=actual.velocidad_mbps,
                bps_entrada=(
                    _tasa(anterior.octetos_entrada, actual.octetos_entrada, segundos)
                    if anterior
                    else None
                ),
                bps_salida=(
                    _tasa(anterior.octetos_salida, actual.octetos_salida, segundos)
                    if anterior
                    else None
                ),
            )
        )
    return resultado


def purgar_muestras(db: Session, dias: int) -> None:
    db.execute(
        delete(MuestraInterfaz).where(MuestraInterfaz.momento < ahora() - timedelta(days=dias))
    )
