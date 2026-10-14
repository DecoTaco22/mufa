"""Dependencias comunes de las rutas: estado de la app, sesión de BD, usuario, permisos."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from mufa import alertas, dos_pasos, licencia
from mufa.actualizacion import Actualizador
from mufa.auth import LimitadorDeIntentos, usuario_de_token
from mufa.cifrado import Cifrador
from mufa.config import Ajustes
from mufa.db import Usuario
from mufa.modulos_pro import ModulosPro
from mufa.permisos import Permiso, tiene_permiso
from mufa.tareas import Programador


@dataclass
class EstadoApp:
    ajustes: Ajustes
    sesiones: sessionmaker[Session]
    cifrador: Cifrador
    limitador: LimitadorDeIntentos
    # Reemplazable en pruebas para no mandar avisos reales.
    enviador: alertas.Enviador = alertas.enviar
    # Token para crear el primer administrador (None cuando ya hay usuarios).
    token_inicial: str | None = None
    # Las tareas automáticas: «Respaldar todo ahora» las usa.
    programador: Programador | None = None
    pro: ModulosPro = field(default_factory=ModulosPro)
    actualizador: Actualizador | None = None

    @property
    def archivo_licencia(self) -> Path:
        return self.ajustes.dir_datos / "licencia.txt"

    def plan(self) -> tuple[licencia.Plan, str]:
        return licencia.plan_vigente(self.archivo_licencia, licencia.hoy())


def obtener_estado(request: Request) -> EstadoApp:
    estado: EstadoApp = request.app.state.mufa
    return estado


Estado = Annotated[EstadoApp, Depends(obtener_estado)]


def obtener_db(estado: Estado) -> Iterator[Session]:
    with estado.sesiones() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


DB = Annotated[Session, Depends(obtener_db)]

_bearer = HTTPBearer(auto_error=False)

# La app web usa una cookie HttpOnly (JavaScript no puede leer el token);
# la CLI y las integraciones usan "Authorization: Bearer".
COOKIE_SESION = "mufa_sesion"
CABECERA_CSRF = "X-Mufa-Csrf"
_METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def obtener_token(
    request: Request,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credenciales is not None:
        return credenciales.credentials
    cookie = request.cookies.get(COOKIE_SESION)
    if cookie:
        # Con cookie, todo cambio exige una cabecera propia: otro sitio no puede
        # mandarla sin una petición CORS, y mufa no habilita CORS.
        if request.method not in _METODOS_SEGUROS and request.headers.get(CABECERA_CSRF) != "1":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "falta la cabecera anti-CSRF")
        return cookie
    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "falta el token de sesión",
        headers={"WWW-Authenticate": "Bearer"},
    )


Token = Annotated[str, Depends(obtener_token)]


def usuario_actual(token: Token, db: DB) -> Usuario:
    usuario = usuario_de_token(db, token)
    if usuario is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "sesión inválida o vencida",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


UsuarioActual = Annotated[Usuario, Depends(usuario_actual)]


def requiere_funcion(funcion: licencia.Funcion) -> Callable[[EstadoApp], None]:
    """Para las rutas de los módulos de pago: 402 si el plan instalado no los incluye."""

    def verificar(estado: Estado) -> None:
        plan, _aviso = estado.plan()
        if not plan.permite(funcion):
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"{funcion.value} no está incluido en el plan {plan.nombre}",
            )

    return verificar


def falta_dos_pasos(usuario: Usuario, estado: EstadoApp) -> bool:
    return (
        estado.ajustes.exigir_dos_pasos
        and usuario.rol in dos_pasos.ROLES_OBLIGADOS
        and not usuario.totp_activo
    )


def requiere(permiso: Permiso) -> Callable[[Usuario, EstadoApp], Usuario]:
    """Permiso del rol, y verificación en dos pasos activa si el rol la exige.

    Las rutas de /auth usan UsuarioActual a secas: son las que hacen falta
    para poder activar el segundo paso.
    """

    def verificar(usuario: UsuarioActual, estado: Estado) -> Usuario:
        if falta_dos_pasos(usuario, estado):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "tu rol requiere activar la verificación en dos pasos (/auth/2fa/iniciar)",
            )
        if not tiene_permiso(usuario.rol, permiso):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"tu rol no tiene el permiso {permiso.value!r}"
            )
        return usuario

    return verificar
