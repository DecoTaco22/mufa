"""Operaciones de negocio que comparten la API y la CLI.

Las rutas HTTP validan permisos y formatos; lo que pasa de verdad
(auditar, registrar eventos) vive acá para no duplicarlo.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, TypeVar

import paramiko
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mufa import marcas
from mufa.cifrado import Cifrador, ErrorDeCifrado
from mufa.db import Auditoria, Equipo, EstadoEquipo, Evento, HallazgoGuardado, Usuario, ahora
from mufa.engine import evaluar
from mufa.models import Contexto
from mufa.routeros_api import ErrorApiRouterOS, SesionApiRouterOS
from mufa.ssh import SesionDeLectura, SesionSoloLectura

T = TypeVar("T")


def hallazgos_abiertos(db: Session) -> list[tuple[HallazgoGuardado, Equipo]]:
    """Los hallazgos de la última auditoría exitosa de cada equipo."""
    ultima = (
        select(Auditoria.equipo_id, func.max(Auditoria.id).label("auditoria_id"))
        .where(Auditoria.estado == "ok", Auditoria.equipo_id.is_not(None))
        .group_by(Auditoria.equipo_id)
        .subquery()
    )
    filas = db.execute(
        select(HallazgoGuardado, Equipo)
        .join(ultima, HallazgoGuardado.auditoria_id == ultima.c.auditoria_id)
        .join(Equipo, Equipo.id == ultima.c.equipo_id)
        .order_by(Equipo.nombre, HallazgoGuardado.id)
    )
    return [(hallazgo, equipo) for hallazgo, equipo in filas.tuples()]


# Cuánto resta cada hallazgo abierto al puntaje de seguridad (0 a 100).
_PESO_POR_SEVERIDAD = {"crítico": 30, "alto": 15, "medio": 7, "info": 2}


def puntaje(severidades: list[str]) -> int:
    """100 = sin hallazgos. Un crítico solo ya deja el equipo en 70."""
    return max(0, 100 - sum(_PESO_POR_SEVERIDAD.get(s, 0) for s in severidades))


def equipos_auditados(db: Session) -> set[int]:
    """Equipos con al menos una auditoría exitosa: los que tienen puntaje."""
    return set(
        db.scalars(
            select(Auditoria.equipo_id)
            .where(Auditoria.estado == "ok", Auditoria.equipo_id.is_not(None))
            .distinct()
        )
    )


def registrar(
    db: Session,
    usuario: Usuario | None,
    accion: str,
    objeto: str = "",
    detalle: dict[str, Any] | None = None,
) -> None:
    db.add(
        Evento(
            usuario_id=usuario.id if usuario else None,
            accion=accion,
            objeto=objeto,
            detalle=detalle or {},
        )
    )


def _guardar_resultado(auditoria: Auditoria, ctx: Contexto) -> None:
    for hallazgo in evaluar(ctx):
        auditoria.hallazgos.append(
            HallazgoGuardado(
                check_id=hallazgo.id,
                severidad=hallazgo.severidad.value,
                titulo=hallazgo.titulo,
                evidencia=hallazgo.evidencia,
                impacto=hallazgo.impacto,
                remediacion=hallazgo.remediacion,
                referencia=hallazgo.referencia,
            )
        )
    auditoria.estado = "ok"
    auditoria.fin = ahora()


def auditar_texto(
    db: Session, texto: str, marca: str, etiqueta: str, usuario: Usuario | None
) -> Auditoria:
    auditoria = Auditoria(
        origen="archivo", etiqueta=etiqueta, marca=marca, usuario_id=usuario.id if usuario else None
    )
    db.add(auditoria)
    _guardar_resultado(auditoria, marcas.obtener(marca).contexto_desde_texto(texto))
    registrar(db, usuario, "auditoria.archivo", etiqueta, {"marca": marca})
    db.flush()
    return auditoria


class ErrorDeConexion(Exception):
    """No se pudo leer el equipo. El mensaje ya está listo para mostrar."""


def _sesion(
    equipo: Equipo, password: str | None, known_hosts: Path, timeout: float
) -> AbstractContextManager[SesionDeLectura]:
    if equipo.acceso in ("api", "api-ssl"):
        return SesionApiRouterOS(
            equipo.ip_gestion,
            equipo.usuario_ssh,
            password=password,
            port=equipo.puerto_ssh,
            tls=equipo.acceso == "api-ssl",
            timeout=timeout,
            certificados=known_hosts.with_name(known_hosts.name + "_api"),
        )
    return SesionSoloLectura(
        equipo.ip_gestion,
        equipo.usuario_ssh,
        equipo.marca,
        password=password,
        port=equipo.puerto_ssh,
        timeout=timeout,
        known_hosts=known_hosts,
    )


def conectar_y_leer(
    equipo: Equipo,
    cifrador: Cifrador,
    known_hosts: Path,
    timeout: float,
    lector: Callable[[SesionDeLectura], T],
) -> T:
    """Abre una sesión de solo lectura (SSH o API) con las credenciales del equipo y corre `lector`."""
    try:
        password = cifrador.descifrar(equipo.password_cifrada) if equipo.password_cifrada else None
        with _sesion(equipo, password, known_hosts, timeout) as sesion:
            return lector(sesion)
    except paramiko.BadHostKeyException:
        raise ErrorDeConexion(
            "la clave SSH del equipo no coincide con la guardada: posible suplantación. "
            "Si el equipo se reinstaló, hay que confirmar su nueva clave."
        ) from None
    except paramiko.AuthenticationException:
        raise ErrorDeConexion("el equipo rechazó el usuario o la contraseña de SSH") from None
    except TimeoutError:
        raise ErrorDeConexion(
            f"el puerto {equipo.puerto_ssh} no responde: revisa que el servicio esté habilitado "
            "y que acepte conexiones desde la IP de mufa"
        ) from None
    except ConnectionRefusedError:
        raise ErrorDeConexion(
            f"el puerto {equipo.puerto_ssh} rechazó la conexión: ¿es el puerto correcto?"
        ) from None
    except (
        ErrorApiRouterOS,
        paramiko.SSHException,
        OSError,
        RuntimeError,
        ErrorDeCifrado,
        ValueError,
    ) as error:
        raise ErrorDeConexion(str(error) or type(error).__name__) from None


def auditar_equipo(
    db: Session,
    equipo: Equipo,
    usuario: Usuario | None,
    cifrador: Cifrador,
    known_hosts: Path,
    timeout: float = 10.0,
) -> Auditoria:
    """Conecta (SSH o API, solo lectura), evalúa y guarda. Un fallo queda registrado, no explota."""
    auditoria = Auditoria(
        equipo_id=equipo.id,
        origen="ssh" if equipo.acceso == "ssh" else "api",
        etiqueta=equipo.nombre,
        marca=equipo.marca,
        usuario_id=usuario.id if usuario else None,
    )
    db.add(auditoria)
    adaptador = marcas.obtener(equipo.marca)
    try:
        texto = conectar_y_leer(equipo, cifrador, known_hosts, timeout, adaptador.leer)
        ctx = adaptador.contexto_desde_texto(texto)
        if not ctx.version:
            estado = db.get(EstadoEquipo, equipo.id)
            ctx.version = estado.version if estado else ""
        _guardar_resultado(auditoria, ctx)
    except ErrorDeConexion as error:
        auditoria.estado = "error"
        auditoria.error = str(error)
        auditoria.fin = ahora()
    registrar(
        db, usuario, "auditoria.ssh", equipo.nombre, {"estado": auditoria.estado, "id": equipo.id}
    )
    criticos = [h.check_id for h in auditoria.hallazgos if h.severidad == "crítico"]
    if criticos:
        registrar(db, usuario, "auditoria.critico", equipo.nombre, {"hallazgos": criticos})
    db.flush()
    return auditoria
