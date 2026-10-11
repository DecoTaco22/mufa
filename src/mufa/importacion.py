"""Importar al IPAM y a las VLANs lo que ya está configurado en los equipos.

La documentación se arma sola a partir de la red real, y cada dato queda
asociado al equipo y la interfaz de donde salió. Lo que choca con lo ya
documentado no se pisa: se informa como conflicto para que lo revise
una persona.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from mufa import ipam
from mufa.db import DireccionIP, DominioL2, Equipo, Prefijo, Vlan, VlanEnEquipo, ahora
from mufa.snmp import DireccionEnEquipo
from mufa.snmp import VlanEnEquipo as VlanLeida


@dataclass
class ResultadoImportacion:
    nuevas: int = 0
    actualizadas: int = 0
    prefijos_creados: list[str] = field(default_factory=list)
    conflictos: list[str] = field(default_factory=list)


def _contenedor_mas_chico(redes: dict[int, ipam.Red], ip: ipam.Direccion) -> int | None:
    candidatos = [(red.prefixlen, pid) for pid, red in redes.items() if ip in red]
    return max(candidatos)[1] if candidatos else None


def importar_direcciones(
    db: Session, equipo: Equipo, direcciones: list[DireccionEnEquipo]
) -> ResultadoImportacion:
    resultado = ResultadoImportacion()
    redes = {p.id: ipam.normalizar_prefijo(p.prefijo) for p in db.scalars(select(Prefijo))}
    por_texto = {str(red): pid for pid, red in redes.items()}

    for leida in direcciones:
        ip = ipaddress.ip_address(leida.ip)
        if ip.is_loopback or ip.is_unspecified or ip.is_link_local:
            continue
        red = ipaddress.ip_network(f"{ip}/{leida.prefijo}", strict=False)

        prefijo_id = por_texto.get(str(red))
        # Una /32 (loopback, punto a punto) va en el prefijo documentado que la contenga.
        if prefijo_id is None and red.num_addresses <= 2:
            prefijo_id = _contenedor_mas_chico(redes, ip)
        if prefijo_id is None:
            prefijo = Prefijo(prefijo=str(red), descripcion=f"Importado de {equipo.nombre}")
            db.add(prefijo)
            db.flush()
            prefijo_id = prefijo.id
            redes[prefijo.id] = red
            por_texto[str(red)] = prefijo.id
            resultado.prefijos_creados.append(str(red))

        existente = db.scalar(select(DireccionIP).where(DireccionIP.ip == str(ip)))
        if existente is not None:
            if existente.equipo_id not in (None, equipo.id):
                otro = db.get(Equipo, existente.equipo_id)
                resultado.conflictos.append(
                    f"{ip} ({leida.interfaz or 'sin interfaz'}) ya está asignada a "
                    f"{otro.nombre if otro else 'otro equipo'}: posible IP duplicada"
                )
                continue
            existente.equipo_id = equipo.id
            existente.interfaz = leida.interfaz[:255]
            if not existente.descripcion:
                existente.descripcion = f"{equipo.nombre} {leida.interfaz}".strip()[:255]
            resultado.actualizadas += 1
            continue

        db.add(
            DireccionIP(
                prefijo_id=prefijo_id,
                ip=str(ip),
                descripcion=f"{equipo.nombre} {leida.interfaz}".strip()[:255],
                equipo_id=equipo.id,
                interfaz=leida.interfaz[:255],
            )
        )
        resultado.nuevas += 1
    db.flush()
    return resultado


def importar_vlans(
    db: Session, equipo: Equipo, dominio: DominioL2, vlans: list[VlanLeida]
) -> ResultadoImportacion:
    resultado = ResultadoImportacion()
    documentadas = {
        v.numero: v for v in db.scalars(select(Vlan).where(Vlan.dominio_id == dominio.id))
    }
    for leida in vlans:
        if not 1 <= leida.numero <= 4094:
            continue
        vlan = documentadas.get(leida.numero)
        if vlan is None:
            vlan = Vlan(
                dominio_id=dominio.id,
                numero=leida.numero,
                nombre=(leida.nombre or f"VLAN {leida.numero}")[:64],
                descripcion=f"Importada de {equipo.nombre}",
            )
            db.add(vlan)
            db.flush()
            documentadas[leida.numero] = vlan
            resultado.nuevas += 1
        elif leida.nombre and leida.nombre != vlan.nombre:
            # El mismo número con otro nombre: dos redes distintas usando una VLAN
            # que debería ser única en el dominio, o un nombre desactualizado.
            resultado.conflictos.append(
                f"VLAN {leida.numero}: en {equipo.nombre} se llama '{leida.nombre}', "
                f"documentada como '{vlan.nombre}'"
            )

        enlace = db.scalar(
            select(VlanEnEquipo).where(
                VlanEnEquipo.vlan_id == vlan.id,
                VlanEnEquipo.equipo_id == equipo.id,
                VlanEnEquipo.interfaz == leida.interfaz[:255],
            )
        )
        if enlace is None:
            db.add(
                VlanEnEquipo(
                    vlan_id=vlan.id,
                    equipo_id=equipo.id,
                    interfaz=leida.interfaz[:255],
                    nombre_en_equipo=leida.nombre[:255],
                )
            )
        else:
            enlace.nombre_en_equipo = leida.nombre[:255]
            enlace.visto = ahora()
            resultado.actualizadas += 1
    db.flush()
    return resultado
