"""Prueba de no-daño: mufa solo ejecuta comandos de la lista blanca.

Recorre el código buscando llamadas a run_readonly() (el único punto por
donde mufa habla con un router) y verifica que el comando pasado esté en
ALLOWED_COMMANDS. A propósito NO mira cualquier string que empiece con
"/": el texto de remediación de un hallazgo también contiene comandos,
pero como consejo para que el operador los corra él mismo, no como algo
que mufa ejecuta.
"""

from __future__ import annotations

import ast
from pathlib import Path

from mufa.marcas.otras import OTRAS
from mufa.security import ALLOWED_COMMANDS, is_write_command, todos_los_permitidos

SRC = Path(__file__).resolve().parent.parent / "src" / "mufa"
# Recorre su tabla de comandos en un solo run_readonly: la tabla se verifica aparte.
CON_TABLA = SRC / "marcas" / "otras.py"


def _es_llamada_a_run_readonly(nodo: ast.AST) -> bool:
    if not isinstance(nodo, ast.Call):
        return False
    funcion = nodo.func
    if isinstance(funcion, ast.Name):
        return funcion.id == "run_readonly"
    if isinstance(funcion, ast.Attribute):
        return funcion.attr == "run_readonly"
    return False


def _comando_de(nodo: ast.Call) -> str | None:
    """El primer posicional o el keyword `command` de sesion.run_readonly(...)."""
    if nodo.args:
        argumento = nodo.args[0]
    else:
        coincidencias = [kw.value for kw in nodo.keywords if kw.arg == "command"]
        if not coincidencias:
            return None
        argumento = coincidencias[0]

    if isinstance(argumento, ast.Constant) and isinstance(argumento.value, str):
        return argumento.value
    return None


def _comandos_ejecutados_en(ruta: Path) -> list[str]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    comandos = []
    for nodo in ast.walk(arbol):
        if _es_llamada_a_run_readonly(nodo):
            comando = _comando_de(nodo)  # type: ignore[arg-type]
            # Un comando que no es un string literal no se puede verificar
            # estáticamente: se reporta para que el test falle.
            comandos.append(comando if comando is not None else "<comando no literal>")
    return comandos


def test_todo_comando_ejecutado_esta_en_la_lista_blanca() -> None:
    encontrados = 0
    for archivo in SRC.rglob("*.py"):
        if archivo == CON_TABLA:
            assert _comandos_ejecutados_en(archivo) == ["<comando no literal>"]
            continue
        for comando in _comandos_ejecutados_en(archivo):
            encontrados += 1
            assert comando in todos_los_permitidos(), (
                f"{archivo}: comando {comando!r} no está en ALLOWED_COMMANDS"
            )

    assert encontrados > 0, "no se encontró ninguna llamada a run_readonly: ¿se movió la función?"


def test_ningun_comando_de_la_lista_blanca_es_de_escritura() -> None:
    for marca, comandos in ALLOWED_COMMANDS.items():
        for comando in comandos:
            assert not is_write_command(comando), f"{marca}: {comando!r} es de escritura"


def test_las_marcas_que_solo_se_respaldan_usan_su_lista_blanca() -> None:
    for respaldador in OTRAS:
        for comando in respaldador.comandos:
            assert comando in ALLOWED_COMMANDS[respaldador.marca], (respaldador.marca, comando)
            assert not is_write_command(comando)
