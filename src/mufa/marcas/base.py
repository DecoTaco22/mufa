"""Contrato que cumple cada adaptador de marca.

Un adaptador sabe tres cosas de su fabricante: qué comandos de solo
lectura correr para obtener la configuración, cómo traducir esa salida al
Contexto común sobre el que corren las verificaciones, y cómo sacar un
respaldo completo. Las verificaciones no saben de marcas: solo miran el
Contexto.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Protocol

from mufa.models import Contexto
from mufa.snmp import VlanEnEquipo
from mufa.ssh import SesionDeLectura


class Respaldador(Protocol):
    """Lo mínimo para respaldar una marca: sacar la configuración y compararla."""

    @property
    def marca(self) -> str: ...

    @property
    def nombre(self) -> str: ...

    def leer_respaldo(self, sesion: SesionDeLectura) -> str: ...

    def normalizar_respaldo(self, texto: str) -> str: ...


class Adaptador(ABC):
    marca: ClassVar[str]
    nombre: ClassVar[str]

    @abstractmethod
    def contexto_desde_texto(self, texto: str) -> Contexto:
        """Traduce un export de configuración (archivo o salida SSH) al Contexto."""

    @abstractmethod
    def leer(self, sesion: SesionDeLectura) -> str:
        """Corre los comandos de lectura de esta marca y devuelve la configuración cruda."""

    @abstractmethod
    def leer_respaldo(self, sesion: SesionDeLectura) -> str:
        """La configuración completa del equipo, tal como se guarda en un respaldo."""

    def leer_vlans(self, sesion: SesionDeLectura) -> list[VlanEnEquipo] | None:
        """Las VLANs configuradas, si la marca las lee por su acceso (si no, se usa SNMP)."""
        return None

    def normalizar_respaldo(self, texto: str) -> str:
        """Quita lo que cambia solo (fechas, contadores) para comparar versiones.

        Dos respaldos con la misma configuración tienen que normalizarse
        igual, aunque se hayan sacado en momentos distintos.
        """
        return "\n".join(linea.rstrip() for linea in texto.replace("\r\n", "\n").split("\n"))
