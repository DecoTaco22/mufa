"""IPAM: prefijos anidados, uso y asignación de direcciones."""

from __future__ import annotations

import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from mufa import ipam
from mufa.api.deps import DB, requiere
from mufa.api.esquemas import (
    DireccionCrear,
    DireccionSalida,
    PrefijoActualizar,
    PrefijoCrear,
    PrefijoSalida,
)
from mufa.db import DireccionIP, Equipo, Prefijo, Sitio, Usuario
from mufa.permisos import Permiso
from mufa.servicios import registrar

router = APIRouter(prefix="/ipam", tags=["ipam"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Gestor = Annotated[Usuario, Depends(requiere(Permiso.GESTIONAR_EQUIPOS))]


def _redes(db: DB) -> dict[int, ipam.Red]:
    return {p.id: ipam.normalizar_prefijo(p.prefijo) for p in db.scalars(select(Prefijo))}


def _salidas(db: DB, prefijos: list[Prefijo]) -> list[PrefijoSalida]:
    """Uso de cada prefijo contando todas las direcciones que caen adentro, también en hijos."""
    redes = _redes(db)
    nombres: dict[int, str] = {i: n for i, n in db.execute(select(Equipo.id, Equipo.nombre))}
    filas = db.execute(
        select(DireccionIP.ip, DireccionIP.equipo_id, DireccionIP.interfaz, DireccionIP.prefijo_id)
    ).all()
    direcciones = [ipaddress.ip_address(f.ip) for f in filas]
    # Equipo e interfaz de cada prefijo, en el orden en que aparecen (sin repetir).
    donde: dict[int, dict[str, None]] = {}
    principal: dict[int, int] = {}
    for fila in filas:
        if fila.equipo_id in nombres:
            principal.setdefault(fila.prefijo_id, fila.equipo_id)
            texto = nombres[fila.equipo_id] + (f" · {fila.interfaz}" if fila.interfaz else "")
            donde.setdefault(fila.prefijo_id, {})[texto] = None
    salidas = []
    for prefijo in prefijos:
        red = redes[prefijo.id]
        asignadas = sum(1 for ip in direcciones if ip in red)
        uso = ipam.uso(red, asignadas)
        contenedores = [
            (otra.prefixlen, otro_id)
            for otro_id, otra in redes.items()
            if otro_id != prefijo.id and otra.version == red.version and red.subnet_of(otra)  # type: ignore[arg-type]
        ]
        salidas.append(
            PrefijoSalida(
                id=prefijo.id,
                prefijo=prefijo.prefijo,
                descripcion=prefijo.descripcion,
                sitio_id=prefijo.sitio_id,
                vlan=prefijo.vlan,
                reservado=prefijo.reservado,
                utilizables=uso.utilizables,
                asignadas=uso.asignadas,
                porcentaje_uso=uso.porcentaje,
                contenido_en=max(contenedores)[1] if contenedores else None,
                equipos=list(donde.get(prefijo.id, {}))[:4],
                equipo_id=principal.get(prefijo.id),
                equipo=nombres.get(principal.get(prefijo.id, -1), ""),
            )
        )
    return salidas


def _obtener(db: DB, prefijo_id: int) -> Prefijo:
    prefijo = db.get(Prefijo, prefijo_id)
    if prefijo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prefijo no encontrado")
    return prefijo


def _validar_sitio(db: DB, sitio_id: int | None) -> None:
    if sitio_id is not None and db.get(Sitio, sitio_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "el sitio no existe")


@router.get("/prefijos")
def listar_prefijos(_: Lector, db: DB) -> list[PrefijoSalida]:
    prefijos = list(db.scalars(select(Prefijo)))
    prefijos.sort(key=lambda p: ipam.orden(ipam.normalizar_prefijo(p.prefijo)))
    return _salidas(db, prefijos)


@router.post("/prefijos", status_code=status.HTTP_201_CREATED)
def crear_prefijo(entrada: PrefijoCrear, usuario: Gestor, db: DB) -> PrefijoSalida:
    try:
        red = ipam.normalizar_prefijo(entrada.prefijo)
    except ipam.PrefijoInvalido as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if db.scalar(select(Prefijo).where(Prefijo.prefijo == str(red))) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{red} ya está documentado")
    _validar_sitio(db, entrada.sitio_id)
    prefijo = Prefijo(
        prefijo=str(red),
        descripcion=entrada.descripcion,
        sitio_id=entrada.sitio_id,
        vlan=entrada.vlan,
        reservado=entrada.reservado,
    )
    db.add(prefijo)
    db.flush()
    registrar(db, usuario, "ipam.crear_prefijo", prefijo.prefijo)
    return _salidas(db, [prefijo])[0]


@router.get("/prefijos/{prefijo_id}")
def ver_prefijo(prefijo_id: int, _: Lector, db: DB) -> PrefijoSalida:
    return _salidas(db, [_obtener(db, prefijo_id)])[0]


@router.patch("/prefijos/{prefijo_id}")
def actualizar_prefijo(
    prefijo_id: int, entrada: PrefijoActualizar, usuario: Gestor, db: DB
) -> PrefijoSalida:
    prefijo = _obtener(db, prefijo_id)
    cambios = entrada.model_dump(exclude_unset=True)
    if cambios.get("prefijo"):
        cambios["prefijo"] = _nueva_red(db, prefijo, cambios["prefijo"])
    else:
        cambios.pop("prefijo", None)
    if "sitio_id" in cambios:
        _validar_sitio(db, cambios["sitio_id"])
    for campo, valor in cambios.items():
        if valor is not None or campo in ("sitio_id", "vlan"):
            setattr(prefijo, campo, valor)
    registrar(db, usuario, "ipam.actualizar_prefijo", prefijo.prefijo)
    return _salidas(db, [prefijo])[0]


def _nueva_red(db: DB, prefijo: Prefijo, texto: str) -> str:
    try:
        red = ipam.normalizar_prefijo(texto)
    except ipam.PrefijoInvalido as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if str(red) == prefijo.prefijo:
        return prefijo.prefijo
    otro = db.scalar(select(Prefijo).where(Prefijo.prefijo == str(red)))
    if otro is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{red} ya está documentado")
    afuera = [
        d.ip
        for d in db.scalars(select(DireccionIP).where(DireccionIP.prefijo_id == prefijo.id))
        if ipaddress.ip_address(d.ip) not in red
    ]
    if afuera:
        ejemplos = ", ".join(sorted(afuera, key=ipaddress.ip_address)[:3])
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{len(afuera)} IP(s) documentadas quedarían fuera de {red} ({ejemplos}): "
            "libéralas o elige una red que las contenga",
        )
    return str(red)


@router.delete("/prefijos/{prefijo_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_prefijo(prefijo_id: int, usuario: Gestor, db: DB) -> None:
    prefijo = _obtener(db, prefijo_id)
    registrar(db, usuario, "ipam.borrar_prefijo", prefijo.prefijo)
    db.delete(prefijo)


@router.get("/prefijos/{prefijo_id}/ips")
def listar_ips(prefijo_id: int, _: Lector, db: DB) -> list[DireccionSalida]:
    _obtener(db, prefijo_id)
    ips = list(db.scalars(select(DireccionIP).where(DireccionIP.prefijo_id == prefijo_id)))
    ips.sort(key=lambda d: ipaddress.ip_address(d.ip))
    return [DireccionSalida.model_validate(d) for d in ips]


@router.post("/prefijos/{prefijo_id}/ips", status_code=status.HTTP_201_CREATED)
def asignar_ip(
    prefijo_id: int, entrada: DireccionCrear, usuario: Gestor, db: DB
) -> DireccionSalida:
    prefijo = _obtener(db, prefijo_id)
    red = ipam.normalizar_prefijo(prefijo.prefijo)
    ocupadas = {ipaddress.ip_address(ip) for ip in db.scalars(select(DireccionIP.ip))}

    if entrada.ip is None:
        libre = ipam.siguiente_libre(red, ocupadas)
        if libre is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{red} no tiene direcciones libres")
        ip = libre
    else:
        try:
            ip = ipaddress.ip_address(entrada.ip.strip())
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"dirección inválida: {entrada.ip!r}"
            ) from None
        if not ipam.es_asignable(red, ip):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{ip} no es asignable dentro de {red}"
            )
        if ip in ocupadas:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{ip} ya está asignada")
    if entrada.equipo_id is not None and db.get(Equipo, entrada.equipo_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "el equipo no existe")

    direccion = DireccionIP(
        prefijo_id=prefijo.id,
        ip=str(ip),
        descripcion=entrada.descripcion,
        equipo_id=entrada.equipo_id,
        reservada=entrada.reservada,
    )
    db.add(direccion)
    db.flush()
    registrar(db, usuario, "ipam.asignar_ip", direccion.ip, {"prefijo": prefijo.prefijo})
    return DireccionSalida.model_validate(direccion)


@router.delete("/ips/{direccion_id}", status_code=status.HTTP_204_NO_CONTENT)
def liberar_ip(direccion_id: int, usuario: Gestor, db: DB) -> None:
    direccion = db.get(DireccionIP, direccion_id)
    if direccion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dirección no encontrada")
    registrar(db, usuario, "ipam.liberar_ip", direccion.ip)
    db.delete(direccion)


@router.get("/buscar")
def buscar(ip: str, _: Lector, db: DB) -> dict[str, object]:
    """En qué prefijos cae una dirección y si está asignada."""
    try:
        direccion = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "dirección inválida") from None
    contenedores = [
        p for p in db.scalars(select(Prefijo)) if direccion in ipam.normalizar_prefijo(p.prefijo)
    ]
    asignada = db.scalar(select(DireccionIP).where(DireccionIP.ip == str(direccion)))
    return {
        "ip": str(direccion),
        "prefijos": [s.model_dump() for s in _salidas(db, contenedores)],
        "asignacion": DireccionSalida.model_validate(asignada).model_dump() if asignada else None,
    }
