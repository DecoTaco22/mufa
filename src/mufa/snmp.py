"""Sondeo SNMP: estado, identidad e interfaces de un equipo de cualquier marca.

SNMPv3 con autenticación y cifrado (authPriv) es el modo recomendado. v2c
se acepta solo para equipos viejos que no soportan v3: la comunidad viaja
en texto plano por la red.

Solo se hacen GET y WALK: mufa nunca envía SET por SNMP.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    bulk_walk_cmd,
    get_cmd,
    next_cmd,
    usmAesCfb128Protocol,
    usmAesCfb256Protocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMACSHAAuthProtocol,
)
from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject

SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
SYS_LOCATION = "1.3.6.1.2.1.1.6.0"

# MIKROTIK-MIB
MTXR_VERSION = "1.3.6.1.4.1.14988.1.1.4.4.0"
MTXR_SERIE = "1.3.6.1.4.1.14988.1.1.7.3.0"
MTXR_MODELO = "1.3.6.1.4.1.14988.1.1.7.8.0"
# ENTITY-MIB: el chasis suele ser la primera fila con serie.
ENT_SERIE = "1.3.6.1.2.1.47.1.1.1.1.11"
ENT_MODELO = "1.3.6.1.2.1.47.1.1.1.1.13"

# IP-MIB (ipAddrTable, IPv4): índice = la dirección.
IP_AD_IF_INDEX = "1.3.6.1.2.1.4.20.1.2"
IP_AD_MASCARA = "1.3.6.1.2.1.4.20.1.3"
# ipNetToMediaPhysAddress (ARP): índice = ifIndex.a.b.c.d
ARP_MAC = "1.3.6.1.2.1.4.22.1.2"
# BRIDGE-MIB: MAC aprendida -> puerto del bridge -> ifIndex.
FDB_PUERTO = "1.3.6.1.2.1.17.4.3.1.2"
PUERTO_A_IF_INDEX = "1.3.6.1.2.1.17.1.4.1.2"
# Q-BRIDGE-MIB y CISCO-VTP-MIB: nombre de cada VLAN, índice = número.
QBRIDGE_VLAN_NOMBRE = "1.3.6.1.2.1.17.7.1.4.3.1.1"
CISCO_VTP_VLAN_NOMBRE = "1.3.6.1.4.1.9.9.46.1.3.1.1.4.1"

IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"
IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"

PROTOCOLOS_AUTH = {"sha": usmHMACSHAAuthProtocol, "sha256": usmHMAC192SHA256AuthProtocol}
# Sin DES ni 3DES: son débiles y cualquier equipo con SNMPv3 actual soporta AES.
PROTOCOLOS_PRIV = {"aes": usmAesCfb128Protocol, "aes256": usmAesCfb256Protocol}

# Número de empresa (IANA) en sysObjectID -> marca de mufa.
_EMPRESAS = {
    "14988": "mikrotik",
    "9": "cisco",
    "2011": "huawei",
    "2636": "juniper",
    "11": "hpe",
    "14823": "hpe",
    "41112": "ubiquiti",
    "6527": "nokia",
    "3902": "zte",
}
_PREFIJO_EMPRESAS = "1.3.6.1.4.1."


class ErrorSNMP(Exception):
    pass


@dataclass(frozen=True)
class CredencialesSNMP:
    version: str  # "3" o "2c"
    puerto: int = 161
    comunidad: str = ""
    usuario: str = ""
    clave_auth: str = ""
    clave_priv: str = ""
    protocolo_auth: str = "sha"
    protocolo_priv: str = "aes"


@dataclass
class Interfaz:
    if_index: int
    nombre: str
    operativa: bool
    velocidad_mbps: int | None
    octetos_entrada: int
    octetos_salida: int


@dataclass
class ResultadoSondeo:
    nombre: str
    descripcion: str
    object_id: str
    uptime_segundos: int | None
    marca_detectada: str
    interfaces: list[Interfaz] = field(default_factory=list)
    ubicacion: str = ""
    serie: str = ""
    modelo: str = ""
    version: str = ""


@dataclass(frozen=True)
class DireccionEnEquipo:
    ip: str
    prefijo: int
    interfaz: str


@dataclass(frozen=True)
class VlanEnEquipo:
    numero: int
    nombre: str
    interfaz: str = ""


@dataclass(frozen=True)
class Ubicacion:
    """Dónde vio un equipo una IP o una MAC."""

    ip: str
    mac: str
    interfaz: str
    fuente: str  # "arp" o "bridge"


def _vacio(valor: Any) -> bool:
    return valor is None or isinstance(valor, (NoSuchObject, NoSuchInstance, EndOfMibView))


def _texto(valor: Any) -> str:
    if _vacio(valor):
        return ""
    texto = valor.prettyPrint() if hasattr(valor, "prettyPrint") else str(valor)
    # Algunos agentes devuelven OCTET STRING binario como "0x..."; no es texto útil.
    return "" if texto.startswith("0x") else texto.strip()


def _mac(valor: Any) -> str:
    datos = bytes(valor.asOctets()) if hasattr(valor, "asOctets") else b""
    return ":".join(f"{b:02X}" for b in datos) if len(datos) == 6 else ""


_VERSION_GENERICA = re.compile(r"Version\s+([\w.()\-]+)", re.IGNORECASE)


def _version_y_modelo_de_descripcion(marca: str, descripcion: str) -> tuple[str, str]:
    """Lo que se puede sacar de sysDescr cuando el MIB propio no lo da."""
    if marca == "mikrotik" and descripcion.startswith("RouterOS "):
        return "", descripcion.removeprefix("RouterOS ").strip()
    coincidencia = _VERSION_GENERICA.search(descripcion)
    return (coincidencia.group(1).rstrip(","), "") if coincidencia else ("", "")


def marca_por_object_id(object_id: str) -> str:
    if not object_id.startswith(_PREFIJO_EMPRESAS):
        return ""
    empresa = object_id[len(_PREFIJO_EMPRESAS) :].split(".")[0]
    return _EMPRESAS.get(empresa, "")


def _autenticacion(cred: CredencialesSNMP) -> CommunityData | UsmUserData:
    if cred.version == "2c":
        return CommunityData(cred.comunidad, mpModel=1)
    if cred.version == "3":
        try:
            auth = PROTOCOLOS_AUTH[cred.protocolo_auth]
            priv = PROTOCOLOS_PRIV[cred.protocolo_priv]
        except KeyError as error:
            raise ErrorSNMP(f"protocolo SNMPv3 desconocido: {error}") from None
        return UsmUserData(
            cred.usuario,
            cred.clave_auth,
            cred.clave_priv,
            authProtocol=auth,
            privProtocol=priv,
        )
    raise ErrorSNMP(f"versión SNMP no soportada: {cred.version!r}")


def interfaces_desde_columnas(columnas: dict[str, dict[int, Any]]) -> list[Interfaz]:
    """Arma las interfaces a partir de las columnas de ifTable/ifXTable (índice -> valor)."""
    indices = sorted(set(columnas.get(IF_DESCR, {})) | set(columnas.get(IF_NAME, {})))
    interfaces = []
    for indice in indices:
        nombre = str(columnas.get(IF_NAME, {}).get(indice) or columnas[IF_DESCR].get(indice, ""))
        velocidad = columnas.get(IF_HIGH_SPEED, {}).get(indice)
        interfaces.append(
            Interfaz(
                if_index=indice,
                nombre=nombre,
                operativa=int(columnas.get(IF_OPER_STATUS, {}).get(indice, 2)) == 1,
                velocidad_mbps=int(velocidad) if velocidad is not None else None,
                octetos_entrada=int(columnas.get(IF_HC_IN_OCTETS, {}).get(indice, 0)),
                octetos_salida=int(columnas.get(IF_HC_OUT_OCTETS, {}).get(indice, 0)),
            )
        )
    return interfaces


def _espera(destino: UdpTransportTarget) -> float:
    """Cuánto esperar una respuesta antes de darla por perdida (pysnmp a veces no avisa nunca)."""
    return float(destino.timeout) * (int(destino.retries) + 1) + 1.0


async def _get(
    motor: SnmpEngine,
    auth: CommunityData | UsmUserData,
    destino: UdpTransportTarget,
    oids: Iterable[str],
) -> dict[str, Any]:
    try:
        error, estado, _indice, valores = await asyncio.wait_for(
            get_cmd(
                motor,
                auth,
                destino,
                ContextData(),
                *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            ),
            _espera(destino),
        )
    except TimeoutError:
        raise ErrorSNMP("No SNMP response received before timeout") from None
    if error:
        raise ErrorSNMP(str(error))
    if estado:
        raise ErrorSNMP(estado.prettyPrint())
    return {str(oid): valor for oid, valor in valores}


# Equipos que no contestan GETBULK (hay MikroTik que con SNMPv3 no lo hacen):
# con ellos se recorre con GETNEXT, más lento pero seguro.
_SIN_BULK: set[tuple[str, int]] = set()


class _SinRespuesta(Exception):
    pass


async def _recorrer_con(
    pasos: Any, prefijo: str, limite: int, espera: float, resultado: dict[str, Any]
) -> None:
    """Consume un walk de pysnmp con un tope por paso: si el equipo deja de contestar, corta."""
    try:
        while True:
            try:
                error, estado, _indice, valores = await asyncio.wait_for(anext(pasos), espera)
            except StopAsyncIteration:
                return
            except TimeoutError:
                raise _SinRespuesta from None
            if error:
                if "timeout" in str(error).lower():
                    raise _SinRespuesta
                raise ErrorSNMP(str(error))
            if estado:
                # Una columna que el equipo no implementa no es un error.
                return
            for oid, valor in valores:
                texto = str(oid)
                if texto.startswith(prefijo):
                    resultado[texto[len(prefijo) :]] = valor
            if len(resultado) >= limite:
                return
    finally:
        with contextlib.suppress(Exception):
            await pasos.aclose()


async def _por_getnext(
    motor: SnmpEngine,
    auth: CommunityData | UsmUserData,
    destino: UdpTransportTarget,
    columnas: list[str],
    limite: int,
) -> dict[str, dict[str, Any]]:
    """Recorre varias columnas a la vez con GETNEXT: una consulta trae una fila de cada una."""
    resultados: dict[str, dict[str, Any]] = {columna: {} for columna in columnas}
    posicion = {columna: columna for columna in columnas}
    espera = _espera(destino)
    while posicion:
        pendientes = list(posicion)
        try:
            error, estado, _indice, valores = await asyncio.wait_for(
                next_cmd(
                    motor,
                    auth,
                    destino,
                    ContextData(),
                    *(ObjectType(ObjectIdentity(posicion[c])) for c in pendientes),
                ),
                espera,
            )
        except TimeoutError:
            raise ErrorSNMP("No SNMP response received before timeout") from None
        if error:
            raise ErrorSNMP(str(error))
        if estado:
            break
        for columna, (oid, valor) in zip(pendientes, valores, strict=False):
            texto = str(oid)
            prefijo = columna + "."
            fuera = not texto.startswith(prefijo) or isinstance(valor, EndOfMibView)
            if fuera or len(resultados[columna]) >= limite:
                del posicion[columna]
                continue
            resultados[columna][texto[len(prefijo) :]] = valor
            posicion[columna] = texto
    return resultados


async def _tablas(
    motor: SnmpEngine,
    auth: CommunityData | UsmUserData,
    destino: UdpTransportTarget,
    columnas: list[str],
    limite: int = 50_000,
) -> dict[str, dict[str, Any]]:
    """Recorre columnas: columna -> {sufijo del OID: valor}. Por GETBULK si el equipo lo contesta."""
    equipo = destino.get_transport_info()[1]
    if equipo not in _SIN_BULK:
        resultados: dict[str, dict[str, Any]] = {}
        try:
            for columna in columnas:
                resultados[columna] = {}
                pasos = bulk_walk_cmd(
                    motor,
                    auth,
                    destino,
                    ContextData(),
                    0,
                    25,
                    ObjectType(ObjectIdentity(columna)),
                    lexicographicMode=False,
                )
                # El primer paso decide: si GETBULK no vuelve en un timeout, no va a volver.
                await _recorrer_con(
                    pasos, columna + ".", limite, float(destino.timeout) + 1, resultados[columna]
                )
            return resultados
        except _SinRespuesta:
            _SIN_BULK.add(equipo)
    return await _por_getnext(motor, auth, destino, columnas, limite)


async def _tabla(
    motor: SnmpEngine,
    auth: CommunityData | UsmUserData,
    destino: UdpTransportTarget,
    columna: str,
    limite: int = 50_000,
) -> dict[str, Any]:
    """Recorre una columna: sufijo del OID (lo que sigue a la columna) -> valor."""
    return (await _tablas(motor, auth, destino, [columna], limite))[columna]


async def _columna(
    motor: SnmpEngine,
    auth: CommunityData | UsmUserData,
    destino: UdpTransportTarget,
    columna: str,
) -> dict[int, Any]:
    return _por_indice(await _tabla(motor, auth, destino, columna))


def _por_indice(tabla: dict[str, Any]) -> dict[int, Any]:
    return {int(sufijo.rsplit(".", 1)[-1]): valor for sufijo, valor in tabla.items()}


async def _identidad(
    motor: SnmpEngine,
    auth: CommunityData | UsmUserData,
    destino: UdpTransportTarget,
    marca: str,
    descripcion: str,
) -> tuple[str, str, str, str]:
    """(ubicación, serie, modelo, versión). Lo que falte queda vacío: nunca hace fallar el sondeo."""
    ubicacion = serie = modelo = version = ""
    try:
        if marca == "mikrotik":
            datos = await _get(
                motor, auth, destino, (SYS_LOCATION, MTXR_SERIE, MTXR_MODELO, MTXR_VERSION)
            )
            serie = _texto(datos.get(MTXR_SERIE))
            modelo = _texto(datos.get(MTXR_MODELO))
            version = _texto(datos.get(MTXR_VERSION))
        else:
            datos = await _get(motor, auth, destino, (SYS_LOCATION,))
            series = await _tabla(motor, auth, destino, ENT_SERIE, limite=200)
            modelos = await _tabla(motor, auth, destino, ENT_MODELO, limite=200)
            serie = next((t for v in series.values() if (t := _texto(v))), "")
            modelo = next((t for v in modelos.values() if (t := _texto(v))), "")
        ubicacion = _texto(datos.get(SYS_LOCATION))
    except ErrorSNMP:
        pass
    version_descr, modelo_descr = _version_y_modelo_de_descripcion(marca, descripcion)
    return ubicacion, serie, modelo or modelo_descr, version or version_descr


async def _sondear(
    host: str, cred: CredencialesSNMP, timeout: float, con_interfaces: bool = True
) -> ResultadoSondeo:
    motor = SnmpEngine()
    try:
        auth = _autenticacion(cred)
        destino = await UdpTransportTarget.create((host, cred.puerto), timeout=timeout, retries=1)
        sistema = await _get(motor, auth, destino, (SYS_DESCR, SYS_OBJECT_ID, SYS_UPTIME, SYS_NAME))
        object_id = str(sistema.get(SYS_OBJECT_ID, "") or "")
        descripcion = str(sistema.get(SYS_DESCR, "") or "")
        marca = marca_por_object_id(object_id)
        ubicacion, serie, modelo, version = await _identidad(
            motor, auth, destino, marca, descripcion
        )
        columnas: dict[str, dict[int, Any]] = {}
        if con_interfaces:
            leidas = await _tablas(
                motor,
                auth,
                destino,
                [
                    IF_DESCR,
                    IF_OPER_STATUS,
                    IF_NAME,
                    IF_HC_IN_OCTETS,
                    IF_HC_OUT_OCTETS,
                    IF_HIGH_SPEED,
                ],
            )
            columnas = {c: _por_indice(t) for c, t in leidas.items()}
    finally:
        motor.close_dispatcher()

    uptime = sistema.get(SYS_UPTIME)
    return ResultadoSondeo(
        nombre=str(sistema.get(SYS_NAME, "") or ""),
        descripcion=descripcion,
        object_id=object_id,
        uptime_segundos=int(uptime) // 100 if uptime is not None and str(uptime) else None,
        marca_detectada=marca,
        interfaces=interfaces_desde_columnas(columnas),
        ubicacion=ubicacion,
        serie=serie,
        modelo=modelo,
        version=version,
    )


Consulta = Callable[[SnmpEngine, CommunityData | UsmUserData, UdpTransportTarget], Awaitable[Any]]


async def _con_sesion(host: str, cred: CredencialesSNMP, timeout: float, consulta: Consulta) -> Any:
    motor = SnmpEngine()
    try:
        auth = _autenticacion(cred)
        destino = await UdpTransportTarget.create((host, cred.puerto), timeout=timeout, retries=1)
        return await consulta(motor, auth, destino)
    finally:
        motor.close_dispatcher()


def _consultar(host: str, cred: CredencialesSNMP, timeout: float, consulta: Consulta) -> Any:
    """Corre una consulta de solo lectura. Bloquea: se llama desde hilos de trabajo."""
    try:
        return asyncio.run(_con_sesion(host, cred, timeout, consulta))
    except ErrorSNMP as error:
        raise ErrorSNMP(explicar(str(error), host, cred)) from error
    except Exception as error:  # pysnmp lanza errores variados ante equipos que no responden
        raise ErrorSNMP(explicar(str(error) or type(error).__name__, host, cred)) from error


async def _nombres_de(
    motor: SnmpEngine,
    auth: CommunityData | UsmUserData,
    destino: UdpTransportTarget,
    indices: set[int],
) -> dict[int, str]:
    """El nombre de solo esas interfaces (GET de a 20): en un concentrador con miles
    de sesiones PPPoE recorrer ifName entero tarda minutos."""
    if len(indices) > 300:
        return await _nombres_de_interfaz(motor, auth, destino)
    nombres: dict[int, str] = {}
    orden = sorted(indices)
    for inicio in range(0, len(orden), 20):
        grupo = orden[inicio : inicio + 20]
        datos = await _get(motor, auth, destino, [f"{IF_NAME}.{i}" for i in grupo])
        for i in grupo:
            valor = datos.get(f"{IF_NAME}.{i}")
            if not _vacio(valor):
                nombres[i] = _texto(valor)
    return nombres


async def _nombres_de_interfaz(
    motor: SnmpEngine, auth: CommunityData | UsmUserData, destino: UdpTransportTarget
) -> dict[int, str]:
    nombres = await _columna(motor, auth, destino, IF_NAME)
    if not nombres:
        nombres = await _columna(motor, auth, destino, IF_DESCR)
    return {indice: _texto(valor) for indice, valor in nombres.items()}


def leer_direcciones(
    host: str, cred: CredencialesSNMP, timeout: float = 3.0
) -> list[DireccionEnEquipo]:
    """Las IPv4 configuradas en el equipo, con su prefijo e interfaz (ipAddrTable)."""

    async def consulta(
        motor: SnmpEngine, auth: CommunityData | UsmUserData, destino: UdpTransportTarget
    ) -> list[DireccionEnEquipo]:
        leidas = await _tablas(motor, auth, destino, [IP_AD_IF_INDEX, IP_AD_MASCARA])
        indices, mascaras = leidas[IP_AD_IF_INDEX], leidas[IP_AD_MASCARA]
        usados = {int(i) for i in indices.values() if not _vacio(i)}
        nombres = await _nombres_de(motor, auth, destino, usados)
        direcciones = []
        for ip, indice in indices.items():
            mascara = _texto(mascaras.get(ip))
            try:
                red = ipaddress.ip_network(f"{ip}/{mascara}", strict=False)
            except ValueError:
                continue
            nombre = "" if _vacio(indice) else nombres.get(int(indice), "")
            direcciones.append(DireccionEnEquipo(ip=ip, prefijo=red.prefixlen, interfaz=nombre))
        return direcciones

    resultado: list[DireccionEnEquipo] = _consultar(host, cred, timeout, consulta)
    return resultado


def leer_vlans(host: str, cred: CredencialesSNMP, timeout: float = 3.0) -> list[VlanEnEquipo]:
    """VLANs por Q-BRIDGE-MIB o, en Cisco, CISCO-VTP-MIB. Vacío si el equipo no las expone."""

    async def consulta(
        motor: SnmpEngine, auth: CommunityData | UsmUserData, destino: UdpTransportTarget
    ) -> list[VlanEnEquipo]:
        vlans: dict[int, str] = {}
        for columna in (QBRIDGE_VLAN_NOMBRE, CISCO_VTP_VLAN_NOMBRE):
            for sufijo, valor in (await _tabla(motor, auth, destino, columna)).items():
                numero = int(sufijo.rsplit(".", 1)[-1])
                if 1 <= numero <= 4094:
                    vlans.setdefault(numero, _texto(valor))
        return [VlanEnEquipo(numero=n, nombre=nombre) for n, nombre in sorted(vlans.items())]

    resultado: list[VlanEnEquipo] = _consultar(host, cred, timeout, consulta)
    return resultado


def _ip_de_sufijo(sufijo: str) -> tuple[int, str] | None:
    """ipNetToMedia: "ifIndex.a.b.c.d" -> (ifIndex, "a.b.c.d")."""
    partes = sufijo.split(".")
    if len(partes) != 5:
        return None
    return int(partes[0]), ".".join(partes[1:])


def leer_vecinos(host: str, cred: CredencialesSNMP, timeout: float = 3.0) -> list[Ubicacion]:
    """Tabla ARP y MACs aprendidas por el bridge: para responder "¿dónde está?"."""

    async def consulta(
        motor: SnmpEngine, auth: CommunityData | UsmUserData, destino: UdpTransportTarget
    ) -> list[Ubicacion]:
        nombres = await _nombres_de_interfaz(motor, auth, destino)
        resultado = []
        for sufijo, valor in (await _tabla(motor, auth, destino, ARP_MAC)).items():
            par = _ip_de_sufijo(sufijo)
            if par and (mac := _mac(valor)):
                resultado.append(
                    Ubicacion(ip=par[1], mac=mac, interfaz=nombres.get(par[0], ""), fuente="arp")
                )
        puertos = {
            int(sufijo): int(valor)
            for sufijo, valor in (await _tabla(motor, auth, destino, PUERTO_A_IF_INDEX)).items()
            if not _vacio(valor)
        }
        for sufijo, valor in (await _tabla(motor, auth, destino, FDB_PUERTO)).items():
            octetos = sufijo.split(".")
            if len(octetos) != 6 or _vacio(valor):
                continue
            mac = ":".join(f"{int(o):02X}" for o in octetos)
            interfaz = nombres.get(puertos.get(int(valor), -1), "")
            resultado.append(Ubicacion(ip="", mac=mac, interfaz=interfaz, fuente="bridge"))
        return resultado

    resultado: list[Ubicacion] = _consultar(host, cred, timeout, consulta)
    return resultado


def recorrer(
    host: str, cred: CredencialesSNMP, oid: str, limite: int = 500, timeout: float = 3.0
) -> list[tuple[str, str]]:
    """Explorador SNMP: (OID, valor) bajo `oid`, hasta `limite` filas. Solo lectura."""

    async def consulta(
        motor: SnmpEngine, auth: CommunityData | UsmUserData, destino: UdpTransportTarget
    ) -> list[tuple[str, str]]:
        tabla = await _tabla(motor, auth, destino, oid, limite=limite)
        filas = [
            (f"{oid}.{sufijo}", _texto(valor) or str(valor)) for sufijo, valor in tabla.items()
        ]
        if not filas:
            # Puede ser un escalar (termina en .0) o una hoja sin hijos.
            datos = await _get(motor, auth, destino, (oid,))
            filas = [(o, _texto(v)) for o, v in datos.items() if not _vacio(v)]
        return filas[:limite]

    resultado: list[tuple[str, str]] = _consultar(host, cred, timeout, consulta)
    return resultado


def ip_de_origen(host: str, puerto: int = 161) -> str:
    """La IP local con la que se sale hacia `host`: la que el equipo tiene que permitir.

    Un socket UDP "conectado" no manda nada; solo elige la ruta.
    """
    try:
        familia = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(familia, socket.SOCK_DGRAM) as prueba:
            prueba.connect((host, puerto))
            return str(prueba.getsockname()[0])
    except OSError:
        return ""


def explicar(error: str, host: str, cred: CredencialesSNMP) -> str:
    """Traduce los errores de pysnmp a qué revisar en el equipo."""
    texto = error.lower()
    origen = ip_de_origen(host, cred.puerto) or "la IP de mufa"
    if "timeout" in texto or "no snmp response" in texto:
        if cred.version == "3":
            return (
                "El equipo no respondió por SNMPv3. Revisa, en este orden: "
                f"(1) que {origen} esté permitida en el equipo "
                "(en MikroTik: Addresses de la comunidad); "
                "(2) que el usuario y las dos contraseñas sean iguales a las del equipo; "
                "(3) que los protocolos coincidan (en MikroTik, AES es AES-128); "
                f"(4) que ningún firewall bloquee UDP {cred.puerto}."
            )
        return (
            "El equipo no respondió por SNMP v2c. Revisa la comunidad, "
            f"que {origen} esté permitida en el equipo y que ningún firewall bloquee "
            f"UDP {cred.puerto}."
        )
    if "unknown usm user" in texto:
        return (
            f"El equipo no tiene un usuario SNMPv3 llamado '{cred.usuario}'. "
            "En MikroTik, el usuario es el nombre (Name) de la comunidad."
        )
    if "digest" in texto or "authentication failure" in texto:
        return (
            "La clave de autenticación o el protocolo (SHA-1 / SHA-256) no coinciden "
            "con los del equipo."
        )
    if "decrypt" in texto:
        return (
            "La clave de cifrado o el protocolo (AES-128 / AES-256) no coinciden "
            "con los del equipo. En MikroTik, AES es AES-128."
        )
    if "security level" in texto:
        return (
            "El equipo no acepta autenticación con cifrado para ese usuario. "
            "En MikroTik, la comunidad tiene que tener Security = private."
        )
    return error


def sondear(host: str, cred: CredencialesSNMP, timeout: float = 2.0) -> ResultadoSondeo:
    """Sondea un equipo. Bloquea: se llama desde hilos de trabajo, no desde el bucle de la API."""
    return _correr(host, cred, timeout, con_interfaces=True)


def probar(host: str, cred: CredencialesSNMP, timeout: float = 3.0) -> ResultadoSondeo:
    """Solo el grupo system: para verificar la configuración antes de guardarla."""
    return _correr(host, cred, timeout, con_interfaces=False)


def _correr(
    host: str, cred: CredencialesSNMP, timeout: float, con_interfaces: bool
) -> ResultadoSondeo:
    try:
        return asyncio.run(_sondear(host, cred, timeout, con_interfaces))
    except ErrorSNMP as error:
        raise ErrorSNMP(explicar(str(error), host, cred)) from error
    except Exception as error:  # pysnmp lanza errores variados ante equipos que no responden
        raise ErrorSNMP(explicar(str(error) or type(error).__name__, host, cred)) from error
