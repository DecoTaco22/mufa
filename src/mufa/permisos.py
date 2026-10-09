"""Roles y permisos de la app.

Los roles son fijos por ahora (los del diseño: Lectura a Admin). Cada ruta
de la API pide un permiso, nunca un rol: así un rol nuevo solo cambia esta
tabla y no el resto del código.
"""

from __future__ import annotations

from enum import Enum


class Rol(str, Enum):
    LECTURA = "lectura"
    AGENTE_N1 = "agente_n1"
    TECNICO_N2 = "tecnico_n2"
    INGENIERO_N3 = "ingeniero_n3"
    SENIOR = "senior"
    ADMIN = "admin"


class Permiso(str, Enum):
    VER = "ver"
    # Ping, traceroute, DNS, puertos y «¿Dónde está?» desde el servidor: sin credenciales.
    DIAGNOSTICAR = "diagnosticar"
    AUDITAR = "auditar"
    GESTIONAR_EQUIPOS = "gestionar_equipos"
    USAR_CREDENCIALES = "usar_credenciales"
    ADMINISTRAR_USUARIOS = "administrar_usuarios"
    VER_REGISTRO = "ver_registro"
    CONFIGURAR_ALERTAS = "configurar_alertas"


_BASE = frozenset({Permiso.VER})
# Agente N1 (soporte, mesa de ayuda): ve todo y diagnostica, pero no entra a los equipos.
_AGENTE = _BASE | {Permiso.DIAGNOSTICAR}
_TECNICO = _AGENTE | {Permiso.AUDITAR, Permiso.USAR_CREDENCIALES}
_INGENIERO = _TECNICO | {Permiso.GESTIONAR_EQUIPOS}
_SENIOR = _INGENIERO | {Permiso.VER_REGISTRO, Permiso.CONFIGURAR_ALERTAS}

PERMISOS_POR_ROL: dict[Rol, frozenset[Permiso]] = {
    Rol.LECTURA: _BASE,
    Rol.AGENTE_N1: _AGENTE,
    Rol.TECNICO_N2: _TECNICO,
    Rol.INGENIERO_N3: _INGENIERO,
    Rol.SENIOR: _SENIOR,
    Rol.ADMIN: _SENIOR | {Permiso.ADMINISTRAR_USUARIOS},
}


def tiene_permiso(rol: str, permiso: Permiso) -> bool:
    try:
        return permiso in PERMISOS_POR_ROL[Rol(rol)]
    except ValueError:
        return False
