"""Canales de alerta: Telegram, correo y webhook."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from mufa import alertas
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import CanalCrear, CanalSalida, ConfigCorreo
from mufa.db import CanalAlerta, Usuario, ahora
from mufa.permisos import Permiso
from mufa.servicios import registrar

router = APIRouter(prefix="/alertas", tags=["alertas"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Configurador = Annotated[Usuario, Depends(requiere(Permiso.CONFIGURAR_ALERTAS))]


def _salida(canal: CanalAlerta) -> CanalSalida:
    return CanalSalida(
        id=canal.id,
        nombre=canal.nombre,
        tipo=canal.tipo,
        destino=canal.destino,
        correo=ConfigCorreo(**canal.configuracion) if canal.configuracion else None,
        eventos=canal.eventos,
        activo=canal.activo,
        tiene_secreto=canal.secreto_cifrado is not None,
    )


def _obtener(db: DB, canal_id: int) -> CanalAlerta:
    canal = db.get(CanalAlerta, canal_id)
    if canal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "canal no encontrado")
    return canal


def _aplicar(canal: CanalAlerta, entrada: CanalCrear, estado: Estado) -> None:
    canal.nombre = entrada.nombre
    canal.tipo = entrada.tipo
    canal.destino = entrada.destino
    canal.configuracion = entrada.correo.model_dump() if entrada.correo else {}
    canal.eventos = list(entrada.eventos)
    canal.activo = entrada.activo
    if entrada.secreto is not None:
        canal.secreto_cifrado = estado.cifrador.cifrar(entrada.secreto)


@router.get("/tipos")
def tipos(_: Lector) -> dict[str, str]:
    """Eventos a los que se puede suscribir un canal, con su descripción."""
    return alertas.TIPOS


@router.get("/canales")
def listar(_: Configurador, db: DB) -> list[CanalSalida]:
    return [_salida(c) for c in db.scalars(select(CanalAlerta).order_by(CanalAlerta.nombre))]


@router.post("/canales", status_code=status.HTTP_201_CREATED)
def crear(entrada: CanalCrear, usuario: Configurador, db: DB, estado: Estado) -> CanalSalida:
    canal = CanalAlerta()
    _aplicar(canal, entrada, estado)
    db.add(canal)
    db.flush()
    registrar(db, usuario, "alerta.crear_canal", canal.nombre, {"tipo": canal.tipo})
    return _salida(canal)


@router.put("/canales/{canal_id}")
def reemplazar(
    canal_id: int, entrada: CanalCrear, usuario: Configurador, db: DB, estado: Estado
) -> CanalSalida:
    """Reemplaza el canal. Si no se manda 'secreto', se conserva el guardado."""
    canal = _obtener(db, canal_id)
    _aplicar(canal, entrada, estado)
    registrar(db, usuario, "alerta.editar_canal", canal.nombre)
    return _salida(canal)


@router.delete("/canales/{canal_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar(canal_id: int, usuario: Configurador, db: DB) -> None:
    canal = _obtener(db, canal_id)
    registrar(db, usuario, "alerta.borrar_canal", canal.nombre)
    db.delete(canal)


@router.post("/canales/{canal_id}/probar", status_code=status.HTTP_204_NO_CONTENT)
def probar(canal_id: int, usuario: Configurador, db: DB, estado: Estado) -> None:
    """Manda un aviso de prueba ya mismo, para comprobar que el canal funciona."""
    canal = _obtener(db, canal_id)
    mensaje = alertas.Mensaje(
        tipo="prueba",
        titulo="Prueba de alerta",
        objeto=canal.nombre,
        detalle={"enviado por": usuario.usuario},
        momento=ahora(),
    )
    secreto = estado.cifrador.descifrar(canal.secreto_cifrado) if canal.secreto_cifrado else None
    try:
        estado.enviador(canal, secreto, mensaje)
    except Exception as error:  # noqa: BLE001 — cualquier fallo del destino se informa
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"no se pudo enviar: {error}") from None
