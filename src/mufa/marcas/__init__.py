"""Registro de adaptadores por marca y lectura de equipos."""

from __future__ import annotations

from pathlib import Path

from mufa.marcas.base import Adaptador, Respaldador
from mufa.marcas.cisco import CiscoIOS
from mufa.marcas.mikrotik import MikroTik
from mufa.marcas.otras import OTRAS
from mufa.models import Contexto
from mufa.ssh import KNOWN_HOSTS, SesionSoloLectura

ADAPTADORES: dict[str, Adaptador] = {
    adaptador.marca: adaptador for adaptador in (MikroTik(), CiscoIOS())
}

# Marcas que se pueden respaldar: las auditables y las que por ahora solo se respaldan.
_TODOS: list[Respaldador] = [*ADAPTADORES.values(), *OTRAS]
RESPALDADORES: dict[str, Respaldador] = {r.marca: r for r in _TODOS}

# Marcas que se pueden registrar en el inventario. Todas se monitorean por
# SNMP; los respaldos son para las de RESPALDADORES y la auditoría para las de ADAPTADORES.
MARCAS_CONOCIDAS: dict[str, str] = {
    "mikrotik": "MikroTik",
    "cisco": "Cisco",
    "huawei": "Huawei",
    "juniper": "Juniper",
    "hpe": "HPE / Aruba",
    "ubiquiti": "Ubiquiti",
    "nokia": "Nokia",
    "zte": "ZTE",
    "otra": "Otra",
}


class MarcaNoSoportada(ValueError):
    pass


def obtener(marca: str) -> Adaptador:
    try:
        return ADAPTADORES[marca]
    except KeyError:
        raise MarcaNoSoportada(f"no hay adaptador para la marca {marca!r}") from None


def respaldador(marca: str) -> Respaldador:
    try:
        return RESPALDADORES[marca]
    except KeyError:
        raise MarcaNoSoportada(f"todavía no se sabe respaldar la marca {marca!r}") from None


# Cómo termina la configuración completa de cada marca. Si falta, el respaldo se cortó.
_FINAL = {"cisco": "end", "huawei": "return"}


def falta_en_respaldo(marca: str, texto: str) -> str | None:
    """Por qué el respaldo parece cortado, o None si está entero (o no se puede saber)."""
    lineas = [linea.strip() for linea in texto.replace("\r", "").split("\n") if linea.strip()]
    final = _FINAL.get(marca)
    if final and (not lineas or lineas[-1] != final):
        return f"falta el «{final}» del final"
    if marca == "juniper" and texto.count("{") != texto.count("}"):
        return "las llaves de la configuración no cierran"
    return None


def contexto_desde_archivo(ruta: Path, marca: str = "mikrotik") -> Contexto:
    return obtener(marca).contexto_desde_texto(ruta.read_text(encoding="utf-8"))


def leer_configuracion(
    host: str,
    user: str,
    marca: str = "mikrotik",
    password: str | None = None,
    port: int = 22,
    timeout: float = 10.0,
    known_hosts: Path = KNOWN_HOSTS,
) -> str:
    """Se conecta por SSH y devuelve la configuración cruda que usa el adaptador."""
    adaptador = obtener(marca)
    with SesionSoloLectura(
        host,
        user,
        marca,
        password=password,
        port=port,
        timeout=timeout,
        known_hosts=known_hosts,
    ) as sesion:
        return adaptador.leer(sesion)


def leer_contexto(
    host: str,
    user: str,
    marca: str = "mikrotik",
    password: str | None = None,
    port: int = 22,
    timeout: float = 10.0,
    known_hosts: Path = KNOWN_HOSTS,
) -> Contexto:
    texto = leer_configuracion(host, user, marca, password, port, timeout, known_hosts)
    return obtener(marca).contexto_desde_texto(texto)
