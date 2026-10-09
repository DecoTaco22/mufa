"""Sitios y equipos."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from mufa import marcas, monitoreo, servicios, snmp
from mufa.api.deps import DB, Estado, requiere
from mufa.api.esquemas import (
    EquipoActualizar,
    EquipoCrear,
    EquipoSalida,
    SitioCrear,
    SitioSalida,
    SnmpConfig,
    SnmpSalida,
)
from mufa.cifrado import Cifrador
from mufa.db import Equipo, EstadoEquipo, Respaldo, Sitio, Usuario
from mufa.permisos import Permiso
from mufa.servicios import registrar

router = APIRouter(tags=["inventario"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]
Gestor = Annotated[Usuario, Depends(requiere(Permiso.GESTIONAR_EQUIPOS))]


@dataclass
class _Resumenes:
    # equipo_id -> (en línea, alcanzable)
    en_linea: dict[int, tuple[bool, bool]]
    hallazgos: Counter[int]
    respaldos: dict[int, datetime]
    # equipo_id -> puntaje de seguridad, solo de los auditados.
    puntajes: dict[int, int]


def _resumenes(db: DB, ids: list[int] | None = None) -> _Resumenes:
    estados = select(EstadoEquipo.equipo_id, EstadoEquipo.en_linea, EstadoEquipo.alcanzable)
    respaldos = select(Respaldo.equipo_id, func.max(Respaldo.confirmado)).group_by(
        Respaldo.equipo_id
    )
    if ids is not None:
        estados = estados.where(EstadoEquipo.equipo_id.in_(ids))
        respaldos = respaldos.where(Respaldo.equipo_id.in_(ids))
    abiertos = servicios.hallazgos_abiertos(db)
    severidades: dict[int, list[str]] = {}
    for hallazgo, equipo in abiertos:
        severidades.setdefault(equipo.id, []).append(hallazgo.severidad)
    return _Resumenes(
        en_linea={i: (linea, alcanza) for i, linea, alcanza in db.execute(estados)},
        hallazgos=Counter(equipo.id for _, equipo in abiertos),
        respaldos={i: momento for i, momento in db.execute(respaldos)},
        puntajes={
            i: servicios.puntaje(severidades.get(i, [])) for i in servicios.equipos_auditados(db)
        },
    )


def _salida(equipo: Equipo, resumenes: _Resumenes | None = None) -> EquipoSalida:
    if resumenes is None:
        resumenes = _Resumenes(en_linea={}, hallazgos=Counter(), respaldos={}, puntajes={})
    return EquipoSalida(
        con_adaptador=equipo.marca in marcas.ADAPTADORES,
        con_respaldo=equipo.marca in marcas.RESPALDADORES,
        en_linea=estado[0] if (estado := resumenes.en_linea.get(equipo.id)) else None,
        alcanzable=estado[1] if estado else None,
        hallazgos=resumenes.hallazgos[equipo.id],
        puntaje=resumenes.puntajes.get(equipo.id),
        ultimo_respaldo=resumenes.respaldos.get(equipo.id),
        id=equipo.id,
        nombre=equipo.nombre,
        marca=equipo.marca,
        modelo=equipo.modelo,
        ip_gestion=equipo.ip_gestion,
        acceso=equipo.acceso,
        puerto_ssh=equipo.puerto_ssh,
        numero_serie=equipo.numero_serie,
        sitio_id=equipo.sitio_id,
        usuario_ssh=equipo.usuario_ssh,
        tiene_credenciales=equipo.password_cifrada is not None,
        snmp=(
            SnmpSalida(
                version=equipo.snmp_version,
                puerto=equipo.snmp_puerto,
                usuario=equipo.snmp_usuario,
                protocolo_auth=equipo.snmp_protocolo_auth,
                protocolo_priv=equipo.snmp_protocolo_priv,
            )
            if equipo.snmp_version
            else None
        ),
        creado=equipo.creado,
    )


def credenciales_snmp(
    snmp_config: SnmpConfig, previo: Equipo | None, cifrador: Cifrador
) -> snmp.CredencialesSNMP:
    """Las credenciales completas: las claves no escritas se toman de las guardadas en `previo`."""
    guardadas = monitoreo.credenciales(previo, cifrador) if previo is not None else None
    if guardadas is not None and guardadas.version != snmp_config.version:
        guardadas = None
    if snmp_config.version == "3":
        clave_auth = snmp_config.clave_auth or (guardadas.clave_auth if guardadas else "")
        clave_priv = snmp_config.clave_priv or (guardadas.clave_priv if guardadas else "")
        if not clave_auth or not clave_priv:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "SNMPv3 necesita la clave de autenticación y la de cifrado",
            )
        return snmp.CredencialesSNMP(
            version="3",
            puerto=snmp_config.puerto,
            usuario=snmp_config.usuario,
            clave_auth=clave_auth,
            clave_priv=clave_priv,
            protocolo_auth=snmp_config.protocolo_auth,
            protocolo_priv=snmp_config.protocolo_priv,
        )
    comunidad = snmp_config.comunidad or (guardadas.comunidad if guardadas else "")
    if not comunidad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "SNMP v2c necesita comunidad")
    return snmp.CredencialesSNMP(version="2c", puerto=snmp_config.puerto, comunidad=comunidad)


def _aplicar_snmp(equipo: Equipo, snmp_config: SnmpConfig | None, cifrador: Cifrador) -> None:
    """Reemplaza la configuración SNMP del equipo; None la desactiva. Secretos cifrados."""
    cred = credenciales_snmp(snmp_config, equipo, cifrador) if snmp_config else None
    equipo.snmp_version = cred.version if cred else ""
    equipo.snmp_puerto = cred.puerto if cred else 161
    equipo.snmp_usuario = cred.usuario if cred and cred.version == "3" else ""
    equipo.snmp_protocolo_auth = cred.protocolo_auth if cred else "sha256"
    equipo.snmp_protocolo_priv = cred.protocolo_priv if cred else "aes"

    def cifrar(valor: str) -> str | None:
        return cifrador.cifrar(valor) if valor else None

    es_v3 = cred is not None and cred.version == "3"
    equipo.snmp_auth_cifrada = cifrar(cred.clave_auth) if cred and es_v3 else None
    equipo.snmp_priv_cifrada = cifrar(cred.clave_priv) if cred and es_v3 else None
    equipo.snmp_comunidad_cifrada = cifrar(cred.comunidad) if cred and not es_v3 else None


def _validar_acceso(marca: str, acceso: str) -> None:
    if acceso != "ssh" and marca != "mikrotik":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "el acceso por API solo existe en MikroTik"
        )


def obtener_equipo(db: DB, equipo_id: int) -> Equipo:
    equipo = db.get(Equipo, equipo_id)
    if equipo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "equipo no encontrado")
    return equipo


def exigir_adaptador(equipo: Equipo) -> None:
    if equipo.marca not in marcas.ADAPTADORES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"todavía no hay adaptador para {equipo.marca!r}: solo se monitorea por SNMP",
        )


def _validar_sitio(db: DB, sitio_id: int | None) -> None:
    if sitio_id is not None and db.get(Sitio, sitio_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "el sitio no existe")


def _validar_nombre_libre(db: DB, nombre: str, excepto: int | None = None) -> None:
    existente = db.scalar(select(Equipo).where(Equipo.nombre == nombre))
    if existente is not None and existente.id != excepto:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya existe un equipo con ese nombre")


@router.get("/sitios")
def listar_sitios(_: Lector, db: DB) -> list[SitioSalida]:
    return [SitioSalida.model_validate(s) for s in db.scalars(select(Sitio).order_by(Sitio.nombre))]


@router.post("/sitios", status_code=status.HTTP_201_CREATED)
def crear_sitio(entrada: SitioCrear, usuario: Gestor, db: DB) -> SitioSalida:
    if db.scalar(select(Sitio).where(Sitio.nombre == entrada.nombre)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya existe un sitio con ese nombre")
    sitio = Sitio(nombre=entrada.nombre, descripcion=entrada.descripcion)
    db.add(sitio)
    db.flush()
    registrar(db, usuario, "sitio.crear", sitio.nombre)
    return SitioSalida.model_validate(sitio)


@router.get("/equipos")
def listar_equipos(_: Lector, db: DB, sitio_id: int | None = None) -> list[EquipoSalida]:
    consulta = select(Equipo).order_by(Equipo.nombre)
    if sitio_id is not None:
        consulta = consulta.where(Equipo.sitio_id == sitio_id)
    resumenes = _resumenes(db)
    return [_salida(e, resumenes) for e in db.scalars(consulta)]


@router.get("/equipos/{equipo_id}")
def ver_equipo(equipo_id: int, _: Lector, db: DB) -> EquipoSalida:
    return _salida(obtener_equipo(db, equipo_id), _resumenes(db, [equipo_id]))


@router.post("/equipos", status_code=status.HTTP_201_CREATED)
def crear_equipo(entrada: EquipoCrear, usuario: Gestor, db: DB, estado: Estado) -> EquipoSalida:
    if entrada.marca not in marcas.MARCAS_CONOCIDAS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"marca desconocida: {entrada.marca!r}. Opciones: {sorted(marcas.MARCAS_CONOCIDAS)}",
        )
    plan, _aviso = estado.plan()
    if not plan.admite_otro_equipo(db.scalar(select(func.count()).select_from(Equipo)) or 0):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"el plan {plan.nombre} permite hasta {plan.max_equipos} equipos",
        )
    _validar_nombre_libre(db, entrada.nombre)
    _validar_sitio(db, entrada.sitio_id)
    _validar_acceso(entrada.marca, entrada.acceso)

    datos = entrada.model_dump(exclude={"password_ssh", "snmp"})
    equipo = Equipo(**datos)
    if entrada.password_ssh:
        equipo.password_cifrada = estado.cifrador.cifrar(entrada.password_ssh)
    _aplicar_snmp(equipo, entrada.snmp, estado.cifrador)
    db.add(equipo)
    db.flush()
    registrar(db, usuario, "equipo.crear", equipo.nombre, {"marca": equipo.marca})
    return _salida(equipo)


@router.patch("/equipos/{equipo_id}")
def actualizar_equipo(
    equipo_id: int, entrada: EquipoActualizar, usuario: Gestor, db: DB, estado: Estado
) -> EquipoSalida:
    equipo = obtener_equipo(db, equipo_id)
    cambios = entrada.model_dump(exclude_unset=True)
    if "nombre" in cambios:
        _validar_nombre_libre(db, cambios["nombre"], excepto=equipo.id)
    if "sitio_id" in cambios:
        _validar_sitio(db, cambios["sitio_id"])
    if cambios.get("acceso"):
        _validar_acceso(equipo.marca, cambios["acceso"])

    password = cambios.pop("password_ssh", None)
    cambios.pop("snmp", None)
    if "snmp" in entrada.model_fields_set:
        _aplicar_snmp(equipo, entrada.snmp, estado.cifrador)
    for campo, valor in cambios.items():
        if valor is not None or campo == "sitio_id":
            setattr(equipo, campo, valor)
    if "password_ssh" in entrada.model_fields_set:
        equipo.password_cifrada = estado.cifrador.cifrar(password) if password else None

    # Nunca se registra la contraseña, solo que cambió.
    detalle = {"campos": sorted(entrada.model_fields_set)}
    registrar(db, usuario, "equipo.actualizar", equipo.nombre, detalle)
    return _salida(equipo)


@router.delete("/equipos/{equipo_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_equipo(equipo_id: int, usuario: Gestor, db: DB) -> None:
    equipo = obtener_equipo(db, equipo_id)
    registrar(db, usuario, "equipo.borrar", equipo.nombre)
    db.delete(equipo)
