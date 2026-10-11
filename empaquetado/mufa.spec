# Aplicación de escritorio de mufa (Windows: mufa.exe; macOS: mufa.app).
#   uv run pyinstaller empaquetado/mufa.spec --noconfirm
# Antes hay que compilar la app web (cd web && npm run build): va dentro.
# ruff: noqa
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

RAIZ = Path(SPECPATH).parent
datas, binaries, ocultos = [], [], []
paquetes = ["pysnmp", "uvicorn", "websockets", "serial", "argon2", "pyotp", "webview"]
if sys.platform == "win32":
    # WebView2 se usa a través de pythonnet.
    paquetes += ["clr_loader", "pythonnet"]
for paquete in paquetes:
    d, b, h = collect_all(paquete)
    datas += d
    binaries += b
    ocultos += h
# La app web, las plantillas de informes y las migraciones (Alembic las lee
# como archivos). Se toman de la carpeta del proyecto, esté o no instalado.
FUENTE = RAIZ / "src/mufa"
if not (FUENTE / "web/index.html").exists():
    raise SystemExit("Falta compilar la app web: cd web && npm run build")
for carpeta in ("migraciones", "web", "templates"):
    for archivo in (FUENTE / carpeta).rglob("*"):
        if archivo.is_file() and "__pycache__" not in archivo.parts:
            datas.append((str(archivo), str(archivo.parent.relative_to(FUENTE.parent))))

a = Analysis(
    [str(RAIZ / "empaquetado/lanzador.py")],
    pathex=[str(RAIZ / "src")],
    datas=datas,
    binaries=binaries,
    hiddenimports=ocultos + ["mufa.checks", "mufa.marcas", "email.mime.text"],
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # macOS: una .app de verdad (carpeta), que se abre con doble clic.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="mufa", console=False, upx=False)
    coleccion = COLLECT(exe, a.binaries, a.datas, name="mufa", upx=False)
    app = BUNDLE(
        coleccion,
        name="mufa.app",
        bundle_identifier="app.mufa.escritorio",
        # PyInstaller convierte el PNG a .icns (con Pillow).
        icon=str(RAIZ / "empaquetado/mufa.png"),
        info_plist={"NSHighResolutionCapable": True, "LSMinimumSystemVersion": "12.0"},
    )
else:
    # Windows: un solo .exe, sin ventana de consola.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        name="mufa",
        console=False,
        icon=str(RAIZ / "empaquetado/mufa.ico"),
        upx=False,
    )
