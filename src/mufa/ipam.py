"""Cálculos de IPAM: uso de un prefijo y siguiente dirección libre."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

Red = ipaddress.IPv4Network | ipaddress.IPv6Network
Direccion = ipaddress.IPv4Address | ipaddress.IPv6Address

# Más allá de esto (IPv6) no se calcula porcentaje de uso: no tiene sentido.
_MAXIMO_PARA_PORCENTAJE = 2**24


class PrefijoInvalido(ValueError):
    pass


def normalizar_prefijo(texto: str) -> Red:
    try:
        return ipaddress.ip_network(texto.strip(), strict=False)
    except ValueError:
        raise PrefijoInvalido(f"prefijo inválido: {texto!r}") from None


def orden(red: Red) -> tuple[int, int, int]:
    """Orden natural: IPv4 antes que IPv6, por dirección y del más grande al más chico."""
    return (red.version, int(red.network_address), red.prefixlen)


def utilizables(red: Red) -> int:
    """Direcciones asignables: sin red ni broadcast en IPv4 (salvo /31 y /32)."""
    if red.version == 4 and red.prefixlen < 31:
        return red.num_addresses - 2
    return red.num_addresses


def es_asignable(red: Red, ip: Direccion) -> bool:
    if ip not in red:
        return False
    if red.version == 4 and red.prefixlen < 31:
        return ip not in (red.network_address, red.broadcast_address)
    return True


def _candidatas(red: Red) -> Iterator[Direccion]:
    if red.version == 4 and red.prefixlen < 31:
        yield from red.hosts()
    else:
        yield from (red.network_address + i for i in range(red.num_addresses))


def siguiente_libre(red: Red, ocupadas: Iterable[Direccion]) -> Direccion | None:
    usadas = set(ocupadas)
    for ip in _candidatas(red):
        if ip not in usadas:
            return ip
    return None


@dataclass(frozen=True)
class Uso:
    utilizables: int
    asignadas: int
    porcentaje: float | None


def uso(red: Red, asignadas: int) -> Uso:
    total = utilizables(red)
    porcentaje = round(asignadas * 100 / total, 1) if 0 < total <= _MAXIMO_PARA_PORCENTAJE else None
    return Uso(utilizables=total, asignadas=asignadas, porcentaje=porcentaje)
