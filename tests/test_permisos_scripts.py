"""Los scripts con shebang tienen que ser ejecutables en git (ruff EXE001 en el CI de Linux).

En Windows el permiso no existe en el disco, así que se mira lo que guarda git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_los_scripts_con_shebang_son_ejecutables() -> None:
    salida = subprocess.run(
        ["git", "ls-files", "-s", "--", "*.py"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    sin_permiso = []
    for linea in salida.splitlines():
        modo, _hash, _etapa, ruta = linea.split(maxsplit=3)
        archivo = RAIZ / ruta
        if archivo.exists() and archivo.read_bytes().startswith(b"#!") and modo != "100755":
            sin_permiso.append(ruta)
    assert sin_permiso == [], f"falta: git update-index --chmod=+x {' '.join(sin_permiso)}"
