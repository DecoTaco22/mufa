# Aplicación de escritorio de mufa (Windows: carpeta mufa con mufa.exe; macOS: mufa.app).
#   uv run pyinstaller empaquetado/mufa.spec --noconfirm
# Antes hay que compilar la app web (cd web && npm run build): va dentro.
# ruff: noqa
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

RAIZ = Path(SPECPATH).parent
datas, binaries, ocultos = [], [], []
# fpdf: lo usan los informes de Pro, que van cifrados (PyInstaller no ve que lo importan).
paquetes = ["pysnmp", "uvicorn", "websockets", "serial", "argon2", "pyotp", "webview", "fpdf"]
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
# Los módulos Pro van cifrados (mufa/modulos_pro.py): PyInstaller no puede leer
# qué importan, así que lo que usan de la biblioteca estándar va a mano.
PRO_CIFRADO = FUENTE / "pro" / "modulos.cifrado"
if PRO_CIFRADO.exists():
    datas.append((str(PRO_CIFRADO), "mufa/pro"))
OCULTOS_PRO = [
    "statistics", "itertools", "math", "collections", "dataclasses", "decimal", "fractions",
    "io", "json", "re", "secrets", "smtplib", "ssl", "email.message", "fastapi.responses",
]

a = Analysis(
    [str(RAIZ / "empaquetado/lanzador.py")],
    pathex=[str(RAIZ / "src")],
    datas=datas,
    binaries=binaries,
    hiddenimports=ocultos + OCULTOS_PRO + ["mufa.checks", "mufa.marcas", "mufa.pro", "email.mime.text"],
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
VERSION = re.search(r'__version__ = "([^"]+)"', (FUENTE / "__init__.py").read_text(encoding="utf-8")).group(1)
COPYRIGHT = "Copyright (C) 2026 los autores de mufa. GNU AGPL v3."

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
        version=VERSION,
        info_plist={
            "CFBundleName": "mufa",
            "CFBundleDisplayName": "mufa",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "CFBundleDevelopmentRegion": "es",
            "NSHumanReadableCopyright": COPYRIGHT,
            "LSApplicationCategoryType": "public.app-category.utilities",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
else:
    # Windows: una carpeta (mufa.exe + _internal) que instala el instalador
    # (empaquetado/windows/mufa.iss). Un .exe de un solo archivo se descomprime
    # en una carpeta temporal cada vez que se abre: más lento, y los antivirus
    # lo confunden con malware.
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    numeros = tuple(int(n) for n in re.findall(r"\d+", VERSION)[:3]) + (0,)
    textos = {
        "CompanyName": "mufa",
        "FileDescription": "mufa",
        "FileVersion": VERSION,
        "InternalName": "mufa",
        "LegalCopyright": COPYRIGHT,
        "OriginalFilename": "mufa.exe",
        "ProductName": "mufa",
        "ProductVersion": VERSION,
    }
    version = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numeros, prodvers=numeros),
        kids=[
            # 0x0C0A: español; 1200: Unicode.
            StringFileInfo([StringTable("0C0A04B0", [StringStruct(k, v) for k, v in textos.items()])]),
            VarFileInfo([VarStruct("Translation", [0x0C0A, 1200])]),
        ],
    )
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="mufa",
        console=False,
        icon=str(RAIZ / "empaquetado/mufa.ico"),
        version=version,
        upx=False,
    )
    coleccion = COLLECT(exe, a.binaries, a.datas, name="mufa", upx=False)
