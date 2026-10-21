"""Mapa de topología: qué equipo está conectado con cuál, según sus vecinos.

Por SNMP (solo lectura) se leen tres tablas de vecinos, las que tenga cada equipo:
- LLDP-MIB (estándar: Cisco, Huawei, Juniper, HPE, MikroTik con LLDP, la mayoría).
- CISCO-CDP-MIB (Cisco).
- MIKROTIK-MIB, tabla de vecinos (MNDP/CDP/LLDP que ve RouterOS).

Un vecino se une a un equipo de mufa por su IP de gestión o por su nombre. Los que
no están en mufa también aparecen en el mapa, para saber qué falta agregar.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mufa import monitoreo, snmp
from mufa.cifrado import Cifrador
from mufa.db import Equipo, EstadoEquipo, Vecino

log = logging.getLogger("mufa.topologia")

_LLDP = "1.0.8802.1.1.2.1"
LLDP_LOC_PUERTO_DESC = f"{_LLDP}.3.7.1.4"  # índice: puerto local
LLDP_LOC_PUERTO_ID = f"{_LLDP}.3.7.1.3"
LLDP_REM_PUERTO_ID = f"{_LLDP}.4.1.1.7"  # índice: tiempo.puerto local.índice
LLDP_REM_PUERTO_DESC = f"{_LLDP}.4.1.1.8"
LLDP_REM_NOMBRE = f"{_LLDP}.4.1.1.9"
LLDP_REM_DESCRIPCION = f"{_LLDP}.4.1.1.10"
LLDP_REM_DIRECCION = f"{_LLDP}.4.2.1.3"  # índice: tiempo.puerto.índice.tipo.largo.dirección
_CDP = "1.3.6.1.4.1.9.9.23.1.2.1.1"
CDP_DIRECCION = f"{_CDP}.4"  # índice: ifIndex.índice
CDP_NOMBRE = f"{_CDP}.6"
CDP_PUERTO = f"{_CDP}.7"
CDP_PLATAFORMA = f"{_CDP}.8"
_MTXR = "1.3.6.1.4.1.14988.1.1.11.1.1"
MTXR_IP = f"{_MTXR}.2"
MTXR_PLATAFORMA = f"{_MTXR}.5"
MTXR_NOMBRE = f"{_MTXR}.6"
MTXR_INTERFAZ = f"{_MTXR}.8"  # ifIndex

COLUMNAS = [
    LLDP_LOC_PUERTO_DESC,
    LLDP_LOC_PUERTO_ID,
    LLDP_REM_PUERTO_ID,
    LLDP_REM_PUERTO_DESC,
    LLDP_REM_NOMBRE,
    LLDP_REM_DESCRIPCION,
    LLDP_REM_DIRECCION,
    CDP_DIRECCION,
    CDP_NOMBRE,
    CDP_PUERTO,
    CDP_PLATAFORMA,
    MTXR_IP,
    MTXR_PLATAFORMA,
    MTXR_NOMBRE,
    MTXR_INTERFAZ,
    snmp.IF_NAME,
    snmp.IF_DESCR,
]

Leer = Callable[[str, snmp.CredencialesSNMP, list[str]], dict[str, dict[str, int | str]]]


def _leer(
    host: str, cred: snmp.CredencialesSNMP, columnas: list[str]
) -> dict[str, dict[str, int | str]]:
    return snmp.leer_tablas(host, cred, columnas, limite=5000, timeout=4.0)


@dataclass(frozen=True)
class VecinoLeido:
    interfaz: str
    nombre: str
    puerto: str
    ip: str
    plataforma: str
    fuente: str


def _ip(valor: int | str | None) -> str:
    """Una IP que llega como texto o como 4 bytes en hexadecimal («0x0a000001»)."""
    if not isinstance(valor, str):
        return ""
    if valor.startswith("0x") and len(valor) == 10:
        return str(ipaddress.IPv4Address(bytes.fromhex(valor[2:])))
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        return ""


def _texto(valor: int | str | None) -> str:
    if valor is None:
        return ""
    texto = str(valor)
    if texto.startswith("0x"):
        # Un ID de chasis o de puerto que es una MAC: se muestra como MAC.
        datos = bytes.fromhex(texto[2:])
        return ":".join(f"{b:02X}" for b in datos) if len(datos) == 6 else ""
    return texto.strip()[:255]


def _sin_dominio(nombre: str) -> str:
    return nombre.split(".")[0].strip().lower()


def vecinos_de(tablas: dict[str, dict[str, int | str]]) -> list[VecinoLeido]:
    nombres_if: dict[int, str] = {}
    for oid in (snmp.IF_DESCR, snmp.IF_NAME):  # ifName gana
        for sufijo, valor in tablas.get(oid, {}).items():
            if sufijo.isdigit() and isinstance(valor, str) and valor:
                nombres_if[int(sufijo)] = valor

    vecinos: list[VecinoLeido] = []

    # LLDP: el índice de la tabla remota es tiempo.puerto_local.índice.
    puertos_locales = {
        sufijo: _texto(v) for sufijo, v in tablas.get(LLDP_LOC_PUERTO_DESC, {}).items()
    }
    ids_locales = {sufijo: _texto(v) for sufijo, v in tablas.get(LLDP_LOC_PUERTO_ID, {}).items()}
    direcciones: dict[str, str] = {}
    for sufijo in tablas.get(LLDP_REM_DIRECCION, {}):
        partes = sufijo.split(".")
        # tiempo.puerto.índice.tipo(1=IPv4).largo(4).a.b.c.d
        if len(partes) >= 9 and partes[3] == "1" and partes[4] == "4":
            direcciones[".".join(partes[:3])] = ".".join(partes[5:9])
    for sufijo, nombre in tablas.get(LLDP_REM_NOMBRE, {}).items():
        partes = sufijo.split(".")
        if len(partes) < 3:
            continue
        local = partes[1]
        vecinos.append(
            VecinoLeido(
                interfaz=puertos_locales.get(local) or ids_locales.get(local) or f"puerto {local}",
                nombre=_texto(nombre),
                puerto=_texto(tablas.get(LLDP_REM_PUERTO_DESC, {}).get(sufijo))
                or _texto(tablas.get(LLDP_REM_PUERTO_ID, {}).get(sufijo)),
                ip=direcciones.get(sufijo, ""),
                plataforma=_texto(tablas.get(LLDP_REM_DESCRIPCION, {}).get(sufijo)).split("\n")[0][
                    :120
                ],
                fuente="lldp",
            )
        )

    # CDP: índice ifIndex.índice.
    for sufijo, nombre in tablas.get(CDP_NOMBRE, {}).items():
        if_index = int(sufijo.split(".")[0])
        vecinos.append(
            VecinoLeido(
                interfaz=nombres_if.get(if_index, f"ifIndex {if_index}"),
                nombre=_texto(nombre),
                puerto=_texto(tablas.get(CDP_PUERTO, {}).get(sufijo)),
                ip=_ip(tablas.get(CDP_DIRECCION, {}).get(sufijo)),
                plataforma=_texto(tablas.get(CDP_PLATAFORMA, {}).get(sufijo)),
                fuente="cdp",
            )
        )

    # MikroTik: índice propio; la interfaz viene como ifIndex.
    for sufijo, nombre in tablas.get(MTXR_NOMBRE, {}).items():
        interfaz = tablas.get(MTXR_INTERFAZ, {}).get(sufijo)
        vecinos.append(
            VecinoLeido(
                interfaz=nombres_if.get(interfaz, "") if isinstance(interfaz, int) else "",
                nombre=_texto(nombre),
                puerto="",
                ip=_ip(tablas.get(MTXR_IP, {}).get(sufijo)),
                plataforma=_texto(tablas.get(MTXR_PLATAFORMA, {}).get(sufijo)),
                fuente="mikrotik",
            )
        )

    # El mismo vecino visto por dos tablas (MikroTik también publica LLDP): uno solo.
    unicos: dict[tuple[str, str], VecinoLeido] = {}
    for v in vecinos:
        if not v.nombre and not v.ip:
            continue
        clave = (v.interfaz.lower(), _sin_dominio(v.nombre) or v.ip)
        previo = unicos.get(clave)
        if previo is None:
            unicos[clave] = v
            continue
        # Se combinan: una tabla trae la IP, otra el puerto o la plataforma.
        unicos[clave] = VecinoLeido(
            interfaz=previo.interfaz or v.interfaz,
            nombre=previo.nombre or v.nombre,
            puerto=previo.puerto or v.puerto,
            ip=previo.ip or v.ip,
            plataforma=previo.plataforma or v.plataforma,
            fuente=previo.fuente,
        )
    return list(unicos.values())


@dataclass
class ResultadoDescubrir:
    equipos: int = 0
    vecinos: int = 0
    errores: dict[str, str] = field(default_factory=dict)


def descubrir(
    db: Session, cifrador: Cifrador, leer: Leer | None = None, ahora: datetime | None = None
) -> ResultadoDescubrir:
    """Lee los vecinos de todos los equipos con SNMP y reemplaza los guardados."""
    ahora = ahora or datetime.now(UTC)
    equipos = list(db.scalars(select(Equipo).where(Equipo.snmp_version != "")))
    pedidos = [(e, monitoreo.credenciales(e, cifrador)) for e in equipos]
    resultado = ResultadoDescubrir(equipos=len(equipos))

    def leer_uno(par: tuple[Equipo, snmp.CredencialesSNMP | None]) -> list[VecinoLeido] | str:
        equipo, cred = par
        if cred is None:
            return "sin credenciales SNMP"
        try:
            return vecinos_de((leer or _leer)(equipo.ip_gestion, cred, COLUMNAS))
        except snmp.ErrorSNMP as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=8) as grupo:
        leidos = list(grupo.map(leer_uno, pedidos))
    for (equipo, _), leido in zip(pedidos, leidos, strict=True):
        if isinstance(leido, str):
            resultado.errores[equipo.nombre] = leido
            continue  # se conservan los vecinos de la vez anterior
        db.execute(delete(Vecino).where(Vecino.equipo_id == equipo.id))
        for v in leido:
            db.add(
                Vecino(
                    equipo_id=equipo.id,
                    interfaz=v.interfaz,
                    remoto_nombre=v.nombre,
                    remoto_puerto=v.puerto,
                    remoto_ip=v.ip,
                    plataforma=v.plataforma,
                    fuente=v.fuente,
                    visto=ahora,
                )
            )
        resultado.vecinos += len(leido)
    db.flush()
    return resultado


# --- el mapa ----------------------------------------------------------------------


@dataclass
class Nodo:
    id: str
    nombre: str
    marca: str = ""
    ip: str = ""
    sitio: str = ""
    estado: str = "desconocido"  # en_linea, caido, alcanzable, sin_snmp, fuera (no está en mufa)
    plataforma: str = ""


@dataclass
class Enlace:
    desde: str
    hasta: str
    interfaz: str
    puerto: str


def _estado(equipo: Equipo, estado: EstadoEquipo | None) -> str:
    if not equipo.snmp_version:
        return "sin_snmp"
    if estado is None:
        return "desconocido"
    if estado.en_linea:
        return "en_linea"
    return "alcanzable" if estado.alcanzable else "caido"


def mapa(db: Session) -> tuple[list[Nodo], list[Enlace]]:
    equipos = list(db.scalars(select(Equipo)))
    estados = {e.equipo_id: e for e in db.scalars(select(EstadoEquipo))}
    nodos: dict[str, Nodo] = {}
    por_ip: dict[str, str] = {}
    por_nombre: dict[str, str] = {}
    for e in equipos:
        clave = f"e{e.id}"
        estado = estados.get(e.id)
        nodos[clave] = Nodo(
            clave,
            e.nombre,
            e.marca,
            e.ip_gestion,
            e.sitio.nombre if e.sitio else "",
            _estado(e, estado),
        )
        por_ip[e.ip_gestion] = clave
        por_nombre[_sin_dominio(e.nombre)] = clave
        if estado and estado.sys_nombre:
            por_nombre.setdefault(_sin_dominio(estado.sys_nombre), clave)

    enlaces: dict[tuple[str, str], Enlace] = {}
    for v in db.scalars(select(Vecino).order_by(Vecino.equipo_id, Vecino.id)):
        desde = f"e{v.equipo_id}"
        if desde not in nodos:
            continue
        hasta = por_ip.get(v.remoto_ip) or por_nombre.get(_sin_dominio(v.remoto_nombre))
        if hasta is None:
            hasta = f"x:{_sin_dominio(v.remoto_nombre) or v.remoto_ip}"
            nodos.setdefault(
                hasta,
                Nodo(
                    hasta,
                    v.remoto_nombre or v.remoto_ip,
                    ip=v.remoto_ip,
                    estado="fuera",
                    plataforma=v.plataforma,
                ),
            )
        if hasta == desde:
            continue
        # A-B y B-A son el mismo cable: se dibuja una vez.
        par = (min(desde, hasta), max(desde, hasta))
        if par not in enlaces:
            enlaces[par] = Enlace(desde, hasta, v.interfaz, v.remoto_puerto)
    return list(nodos.values()), list(enlaces.values())
