"""Parser mínimo de exports/scripts de RouterOS (.rsc).

Entiende lo suficiente del formato de `/export` para las verificaciones
actuales: menús (líneas que empiezan con "/"), comandos `set`/`add` con
pares clave=valor, continuaciones de línea con "\\" y comentarios "#".
No es un parser completo del lenguaje de scripting de RouterOS.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field


@dataclass
class Comando:
    menu: str
    verbo: str
    propiedades: dict[str, str] = field(default_factory=dict)
    # Lo que no es clave=valor: "set telnet disabled=yes" -> ["telnet"].
    argumentos: list[str] = field(default_factory=list)


def _desenvolver_continuaciones(texto: str) -> list[str]:
    lineas = texto.replace("\r\n", "\n").split("\n")
    resultado: list[str] = []
    acumulado = ""

    for cruda in lineas:
        linea = cruda.rstrip()
        if linea.endswith("\\"):
            acumulado += linea[:-1] + " "
            continue
        resultado.append(acumulado + linea)
        acumulado = ""

    if acumulado:
        resultado.append(acumulado)

    return resultado


def parsear(texto: str) -> list[Comando]:
    comandos: list[Comando] = []
    menu_actual = ""

    for linea in _desenvolver_continuaciones(texto):
        despojada = linea.strip()
        if not despojada or despojada.startswith("#"):
            continue
        if despojada.startswith("/"):
            menu_actual = despojada
            continue

        try:
            tokens = shlex.split(despojada)
        except ValueError:
            continue
        if not tokens:
            continue

        verbo, *resto = tokens
        propiedades = {
            clave: valor
            for token in resto
            if "=" in token
            for clave, _, valor in [token.partition("=")]
        }
        argumentos = [token for token in resto if "=" not in token]
        comandos.append(
            Comando(menu=menu_actual, verbo=verbo, propiedades=propiedades, argumentos=argumentos)
        )

    return comandos
