"""VLANs: documentación por dominio de capa 2, sin números duplicados."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from mufa.api.deps import DB, requiere
from mufa.api.esquemas import (
    DominioCrear,
    DominioSalida,
    VlanActualizar,
    VlanCrear,
    VlanEnEquipoEntrada,
    VlanEnEquipoSalida,
    VlanSalida,
)
from mufa.db import DominioL2, Equipo, Usuario, Vlan, VlanEnEquipo
from mufa.permisos import Permiso
from mufa.servicios import registrar

router = APIRouter(prefix="/vlans", tags=["vlans"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Gestor = Annotated[Usuario, Depends(requiere(Permiso.GESTIONAR_EQUIPOS))]


def _dominio(db: DB, dominio_id: int) -> DominioL2:
    dominio = db.get(DominioL2, dominio_id)
    if dominio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dominio no encontrado")
    return dominio


def _vlan(db: DB, vlan_id: int) -> Vlan:
    vlan = db.get(Vlan, vlan_id)
    if vlan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "VLAN no encontrada")
    return vlan


@router.get("/dominios")
def listar_dominios(_: Lector, db: DB) -> list[DominioSalida]:
    dominios = db.scalars(select(DominioL2).order_by(DominioL2.nombre))
    return [DominioSalida.model_validate(d) for d in dominios]


@router.post("/dominios", status_code=status.HTTP_201_CREATED)
def crear_dominio(entrada: DominioCrear, usuario: Gestor, db: DB) -> DominioSalida:
    if db.scalar(select(DominioL2).where(DominioL2.nombre == entrada.nombre)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya existe un dominio con ese nombre")
    dominio = DominioL2(nombre=entrada.nombre, descripcion=entrada.descripcion)
    db.add(dominio)
    db.flush()
    registrar(db, usuario, "vlan.crear_dominio", dominio.nombre)
    return DominioSalida.model_validate(dominio)


@router.delete("/dominios/{dominio_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_dominio(dominio_id: int, usuario: Gestor, db: DB) -> None:
    dominio = _dominio(db, dominio_id)
    registrar(db, usuario, "vlan.borrar_dominio", dominio.nombre)
    db.delete(dominio)


@router.get("/dominios/{dominio_id}/vlans")
def listar_vlans(dominio_id: int, _: Lector, db: DB) -> list[VlanSalida]:
    _dominio(db, dominio_id)
    vlans = list(
        db.scalars(select(Vlan).where(Vlan.dominio_id == dominio_id).order_by(Vlan.numero))
    )
    enlaces: dict[int, list[VlanEnEquipoSalida]] = {}
    for enlace, equipo in db.execute(
        select(VlanEnEquipo, Equipo)
        .join(Equipo, Equipo.id == VlanEnEquipo.equipo_id)
        .where(VlanEnEquipo.vlan_id.in_([v.id for v in vlans]))
        .order_by(Equipo.nombre)
    ):
        enlaces.setdefault(enlace.vlan_id, []).append(
            VlanEnEquipoSalida(
                equipo_id=equipo.id,
                equipo=equipo.nombre,
                interfaz=enlace.interfaz,
                nombre_en_equipo=enlace.nombre_en_equipo,
            )
        )
    return [
        VlanSalida.model_validate(v).model_copy(update={"equipos": enlaces.get(v.id, [])})
        for v in vlans
    ]


@router.post("/dominios/{dominio_id}/vlans", status_code=status.HTTP_201_CREATED)
def crear_vlan(dominio_id: int, entrada: VlanCrear, usuario: Gestor, db: DB) -> VlanSalida:
    dominio = _dominio(db, dominio_id)
    usadas = {
        v.numero: v.nombre for v in db.scalars(select(Vlan).where(Vlan.dominio_id == dominio_id))
    }
    if entrada.numero is None:
        numero = next((n for n in range(entrada.desde, 4095) if n not in usadas), None)
        if numero is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "no quedan VLANs libres en el dominio")
    else:
        numero = entrada.numero
        if numero in usadas:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"la VLAN {numero} ya está usada como {usadas[numero]!r} en {dominio.nombre}",
            )
    vlan = Vlan(
        dominio_id=dominio_id,
        numero=numero,
        nombre=entrada.nombre,
        descripcion=entrada.descripcion,
        reservada=entrada.reservada,
    )
    db.add(vlan)
    db.flush()
    for enlace in entrada.equipos:
        _enlazar(db, vlan, enlace)
    registrar(db, usuario, "vlan.crear", f"{dominio.nombre}/{numero}", {"nombre": vlan.nombre})
    return VlanSalida.model_validate(vlan).model_copy(update={"equipos": _enlaces_de(db, vlan.id)})


def _enlaces_de(db: DB, vlan_id: int) -> list[VlanEnEquipoSalida]:
    return [
        VlanEnEquipoSalida(
            equipo_id=equipo.id,
            equipo=equipo.nombre,
            interfaz=enlace.interfaz,
            nombre_en_equipo=enlace.nombre_en_equipo,
        )
        for enlace, equipo in db.execute(
            select(VlanEnEquipo, Equipo)
            .join(Equipo, Equipo.id == VlanEnEquipo.equipo_id)
            .where(VlanEnEquipo.vlan_id == vlan_id)
            .order_by(Equipo.nombre)
        )
    ]


def _enlazar(db: DB, vlan: Vlan, entrada: VlanEnEquipoEntrada) -> Equipo:
    equipo = db.get(Equipo, entrada.equipo_id)
    if equipo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "el equipo no existe")
    interfaz = entrada.interfaz.strip()
    existente = db.scalar(
        select(VlanEnEquipo).where(
            VlanEnEquipo.vlan_id == vlan.id,
            VlanEnEquipo.equipo_id == equipo.id,
            VlanEnEquipo.interfaz == interfaz,
        )
    )
    if existente is None:
        db.add(VlanEnEquipo(vlan_id=vlan.id, equipo_id=equipo.id, interfaz=interfaz))
        db.flush()
    return equipo


@router.post("/{vlan_id}/equipos", status_code=status.HTTP_201_CREATED)
def agregar_equipo(
    vlan_id: int, entrada: VlanEnEquipoEntrada, usuario: Gestor, db: DB
) -> VlanSalida:
    """Documenta a mano en qué equipo (y en qué interfaz) está la VLAN."""
    vlan = _vlan(db, vlan_id)
    equipo = _enlazar(db, vlan, entrada)
    registrar(db, usuario, "vlan.agregar_equipo", str(vlan.numero), {"equipo": equipo.nombre})
    return VlanSalida.model_validate(vlan).model_copy(update={"equipos": _enlaces_de(db, vlan.id)})


@router.delete("/{vlan_id}/equipos/{equipo_id}", status_code=status.HTTP_204_NO_CONTENT)
def quitar_equipo(
    vlan_id: int, equipo_id: int, usuario: Gestor, db: DB, interfaz: str = ""
) -> None:
    vlan = _vlan(db, vlan_id)
    enlace = db.scalar(
        select(VlanEnEquipo).where(
            VlanEnEquipo.vlan_id == vlan.id,
            VlanEnEquipo.equipo_id == equipo_id,
            VlanEnEquipo.interfaz == interfaz,
        )
    )
    if enlace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "la VLAN no está en ese equipo")
    db.delete(enlace)
    registrar(db, usuario, "vlan.quitar_equipo", str(vlan.numero), {"equipo_id": equipo_id})


@router.patch("/{vlan_id}")
def actualizar_vlan(vlan_id: int, entrada: VlanActualizar, usuario: Gestor, db: DB) -> VlanSalida:
    vlan = _vlan(db, vlan_id)
    for campo, valor in entrada.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(vlan, campo, valor)
    registrar(db, usuario, "vlan.actualizar", str(vlan.numero))
    return VlanSalida.model_validate(vlan)


@router.delete("/{vlan_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_vlan(vlan_id: int, usuario: Gestor, db: DB) -> None:
    vlan = _vlan(db, vlan_id)
    registrar(db, usuario, "vlan.borrar", str(vlan.numero))
    db.delete(vlan)
