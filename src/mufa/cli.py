"""CLI de mufa."""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import paramiko
import typer
from rich.console import Console

from mufa.engine import evaluar
from mufa.marcas import contexto_desde_archivo, leer_contexto
from mufa.report import generar_html
from mufa.ssh import KNOWN_HOSTS

app = typer.Typer(
    add_completion=False, help="Herramientas de diagnóstico para operadores de internet."
)
console = Console()


@app.command()
def audit(
    host: str | None = typer.Argument(
        None, help="IP o host del router. No usar junto con --offline."
    ),
    user: str | None = typer.Option(None, "--user", help="Usuario SSH de solo lectura."),
    password: str | None = typer.Option(
        None, "--password", help="Contraseña SSH (se pide por prompt si se omite)."
    ),
    port: int = typer.Option(22, "--port", help="Puerto SSH."),
    marca: str = typer.Option("mikrotik", "--marca", help="Marca del equipo."),
    offline: Path | None = typer.Option(
        None, "--offline", help="Leer un export .rsc en vez de conectarse por SSH."
    ),
    formato: str = typer.Option("texto", "--format", help="Formato de salida: texto o html."),
    salida: Path | None = typer.Option(
        None, "-o", "--output", help="Archivo de salida. Obligatorio con --format html."
    ),
) -> None:
    """Audita un router: conecta (o lee un export), evalúa reglas, muestra hallazgos."""
    if offline is not None:
        ctx = contexto_desde_archivo(offline, marca)
        etiqueta = str(offline)
    else:
        if host is None or user is None:
            raise typer.BadParameter("host y --user son obligatorios sin --offline.")
        if password is None:
            password = typer.prompt("Contraseña", hide_input=True)
        try:
            ctx = leer_contexto(host, user, marca, password=password, port=port)
        except paramiko.BadHostKeyException:
            console.print(
                f"La clave SSH de {host} no coincide con la guardada en {KNOWN_HOSTS}. "
                "Puede ser un equipo haciéndose pasar por el router; si el router se "
                "reinstaló, borrá su línea de ese archivo y volvé a intentar.",
                markup=False,
            )
            raise typer.Exit(1) from None
        except (paramiko.SSHException, OSError, RuntimeError) as error:
            console.print(f"No se pudo leer {host}: {error}", markup=False)
            raise typer.Exit(1) from None
        etiqueta = host

    hallazgos = evaluar(ctx)

    if formato == "html":
        if salida is None:
            raise typer.BadParameter("--format html requiere -o/--output.")
        salida.write_text(generar_html(hallazgos, host=etiqueta), encoding="utf-8")
        console.print(f"Informe guardado en {salida}")
        return

    if not hallazgos:
        console.print("Sin hallazgos con las verificaciones disponibles.")
        return

    for hallazgo in hallazgos:
        console.print(
            f"[{hallazgo.severidad.value}] {hallazgo.id} — {hallazgo.titulo}", markup=False
        )
        console.print(f"  {hallazgo.evidencia}", markup=False)


@app.command()
def servidor(
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Dirección donde escuchar. 0.0.0.0 la expone a la red."
    ),
    puerto: int = typer.Option(8080, "--puerto", help="Puerto HTTP."),
    proxy: str | None = typer.Option(
        None,
        "--proxy-confiable",
        help=(
            "IP del proxy HTTPS (o '*' si solo el proxy puede llegar al servidor). "
            "Sin esto, todas las conexiones parecen venir del proxy y el bloqueo por "
            "intentos fallidos las trataría como una sola."
        ),
    ),
) -> None:
    """Arranca el servidor web y la API (aplica las migraciones pendientes)."""
    import uvicorn

    from mufa.api import crear_app

    uvicorn.run(
        crear_app(),
        host=host,
        port=puerto,
        proxy_headers=proxy is not None,
        forwarded_allow_ips=proxy,
        server_header=False,
    )


@app.command("crear-admin")
def crear_admin(
    usuario: str = typer.Option(..., "--usuario", help="Nombre de usuario para iniciar sesión."),
    nombre: str = typer.Option(..., "--nombre", help="Nombre visible."),
    email: str | None = typer.Option(None, "--email", help="Email (opcional)."),
    password_stdin: bool = typer.Option(
        False, "--password-stdin", help="Leer la contraseña de la entrada estándar (scripts)."
    ),
) -> None:
    """Crea un usuario administrador (para la primera instalación o una recuperación)."""
    from sqlalchemy import select

    from mufa.api.esquemas import PATRON_USUARIO
    from mufa.auth import PasswordDebil, hashear_password
    from mufa.config import cargar_ajustes
    from mufa.db import Usuario, crear_motor, fabrica_de_sesiones
    from mufa.migraciones import actualizar_base
    from mufa.permisos import Rol
    from mufa.servicios import registrar

    ajustes = cargar_ajustes()
    ajustes.dir_datos.mkdir(parents=True, exist_ok=True)
    actualizar_base(ajustes.url_base_datos)
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = typer.prompt(
            "Contraseña (mínimo 12 caracteres)", hide_input=True, confirmation_prompt=True
        )
    try:
        hash_password = hashear_password(password)
    except PasswordDebil as error:
        console.print(str(error), markup=False)
        raise typer.Exit(1) from None

    usuario = usuario.strip().lower()
    if re.fullmatch(PATRON_USUARIO, usuario) is None:
        console.print(
            "El usuario debe tener de 3 a 32 caracteres: minúsculas, números, '.', '_' o '-', "
            "y empezar con una letra.",
            markup=False,
        )
        raise typer.Exit(1)

    with fabrica_de_sesiones(crear_motor(ajustes.url_base_datos))() as db:
        if db.scalar(select(Usuario).where(Usuario.usuario == usuario)) is not None:
            console.print(f"Ya existe el usuario {usuario}.", markup=False)
            raise typer.Exit(1)
        nuevo = Usuario(
            usuario=usuario,
            email=email.lower() if email else None,
            nombre=nombre,
            rol=Rol.ADMIN.value,
            hash_password=hash_password,
        )
        db.add(nuevo)
        db.flush()
        registrar(db, None, "usuario.crear_admin_cli", nuevo.usuario)
        db.commit()
    console.print(
        f"Administrador {usuario} creado. Al entrar por primera vez, activá la "
        "verificación en dos pasos: es obligatoria para administradores.",
        markup=False,
    )


def main() -> None:
    # En consolas legacy de Windows, stdout suele quedar en cp1252 y
    # rompe cualquier tilde o guion largo en el informe de texto.
    for flujo in (sys.stdout, sys.stderr):
        if isinstance(flujo, io.TextIOWrapper) and flujo.encoding.lower() != "utf-8":
            flujo.reconfigure(encoding="utf-8")
    app()


if __name__ == "__main__":
    main()
