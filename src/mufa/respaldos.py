"""Respaldos de configuración: versiones solo cuando hay cambios, y diferencias entre ellas."""

from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mufa import marcas
from mufa.cifrado import Cifrador
from mufa.db import AjusteSistema, Equipo, Respaldo, Usuario, ahora
from mufa.servicios import ErrorDeConexion, conectar_y_leer, registrar

# Una configuración grande (mucho BGP, listas de miles de direcciones) puede tardar
# minutos en llegar. Para conectar sigue valiendo el tiempo corto.
TIEMPO_DE_LECTURA = 600.0


@dataclass
class ResultadoRespaldo:
    respaldo: Respaldo
    cambio: bool


def ultimo_respaldo(db: Session, equipo_id: int) -> Respaldo | None:
    return db.scalar(
        select(Respaldo)
        .where(Respaldo.equipo_id == equipo_id)
        .order_by(Respaldo.id.desc())
        .limit(1)
    )


def respaldar_equipo(
    db: Session,
    equipo: Equipo,
    usuario: Usuario | None,
    origen: str,
    cifrador: Cifrador,
    known_hosts: Path,
    timeout: float = 30.0,
    timeout_lectura: float = TIEMPO_DE_LECTURA,
) -> ResultadoRespaldo:
    """Saca la configuración y guarda una versión nueva solo si cambió.

    Lanza ErrorDeConexion (ya registrado como evento) si no se pudo leer, o si llegó
    cortada: un respaldo incompleto nunca reemplaza al anterior.
    """
    adaptador = marcas.respaldador(equipo.marca)
    lector = adaptador.leer_respaldo
    con_secretos = getattr(adaptador, "leer_respaldo_con_secretos", None)
    if con_secretos is not None and leer_programa(db).secretos:
        lector = con_secretos
    try:
        texto = conectar_y_leer(equipo, cifrador, known_hosts, timeout, lector, timeout_lectura)
        if motivo := marcas.falta_en_respaldo(equipo.marca, texto):
            raise ErrorDeConexion(
                f"la configuración llegó incompleta ({motivo}): no se guardó y se conserva "
                "el respaldo anterior"
            )
    except ErrorDeConexion as error:
        registrar(db, usuario, "respaldo.error", equipo.nombre, {"error": str(error)})
        raise

    huella = hashlib.sha256(adaptador.normalizar_respaldo(texto).encode("utf-8")).hexdigest()
    anterior = ultimo_respaldo(db, equipo.id)
    if anterior is not None and anterior.hash_normalizado == huella:
        anterior.confirmado = ahora()
        registrar(db, usuario, "respaldo.sin_cambios", equipo.nombre, {"id": anterior.id})
        return ResultadoRespaldo(respaldo=anterior, cambio=False)

    nuevo = Respaldo(
        equipo_id=equipo.id,
        usuario_id=usuario.id if usuario else None,
        origen=origen,
        hash_normalizado=huella,
        tamano=len(texto.encode("utf-8")),
        contenido_cifrado=cifrador.cifrar(texto),
    )
    db.add(nuevo)
    db.flush()
    registrar(db, usuario, "respaldo.nuevo", equipo.nombre, {"id": nuevo.id, "origen": origen})
    if anterior is not None:
        # Para las alertas: la configuración cambió respecto de la versión anterior.
        registrar(
            db, usuario, "respaldo.cambio", equipo.nombre, {"desde": anterior.id, "hasta": nuevo.id}
        )
    return ResultadoRespaldo(respaldo=nuevo, cambio=True)


@dataclass
class Programa:
    """Cuándo se respalda solo: todos los días a `hora` (hora local del servidor)."""

    activo: bool = True
    hora: str = "12:00"
    # Contraseñas y claves en el respaldo (MikroTik: /export show-sensitive). Sin ellas
    # no se puede restaurar el equipo tal cual. Los respaldos se guardan cifrados.
    secretos: bool = True

    @property
    def hora_del_dia(self) -> time:
        horas, minutos = self.hora.split(":")
        return time(int(horas), int(minutos))


_PROGRAMA = "respaldos.programa"
_ULTIMO_DIA = "respaldos.ultimo_dia"


def _leer_ajuste(db: Session, clave: str) -> str | None:
    fila = db.get(AjusteSistema, clave)
    return fila.valor if fila else None


def _guardar_ajuste(db: Session, clave: str, valor: str) -> None:
    fila = db.get(AjusteSistema, clave)
    if fila is None:
        db.add(AjusteSistema(clave=clave, valor=valor))
    else:
        fila.valor = valor


def leer_programa(db: Session) -> Programa:
    valor = _leer_ajuste(db, _PROGRAMA)
    if not valor:
        return Programa()
    datos = json.loads(valor)
    return Programa(
        activo=bool(datos.get("activo", True)),
        hora=str(datos.get("hora", "12:00")),
        secretos=bool(datos.get("secretos", True)),
    )


def guardar_programa(db: Session, programa: Programa) -> None:
    _guardar_ajuste(db, _PROGRAMA, json.dumps(asdict(programa)))


def toca_respaldar(db: Session, ahora_local: datetime) -> bool:
    """¿Ya pasó la hora de hoy y todavía no se respaldó hoy?

    Si el equipo estaba apagado a la hora programada, respalda apenas arranca.
    """
    programa = leer_programa(db)
    if not programa.activo or ahora_local.time() < programa.hora_del_dia:
        return False
    return _leer_ajuste(db, _ULTIMO_DIA) != ahora_local.date().isoformat()


def marcar_respaldado_hoy(db: Session, ahora_local: datetime) -> None:
    _guardar_ajuste(db, _ULTIMO_DIA, ahora_local.date().isoformat())


def hora_local() -> datetime:
    """La hora del servidor, con su zona (en Docker la fija la variable TZ)."""
    return datetime.now(UTC).astimezone()


def proximo_respaldo(db: Session, ahora_local: datetime) -> datetime | None:
    programa = leer_programa(db)
    if not programa.activo:
        return None
    hoy = datetime.combine(ahora_local.date(), programa.hora_del_dia, ahora_local.tzinfo)
    if toca_respaldar(db, ahora_local) or ahora_local < hoy:
        return max(hoy, ahora_local)
    return hoy + timedelta(days=1)


def contenido(respaldo: Respaldo, cifrador: Cifrador) -> str:
    return cifrador.descifrar(respaldo.contenido_cifrado)


def diferencias(
    marca: str, anterior: str, posterior: str, nombre_anterior: str, nombre_posterior: str
) -> str:
    """Diferencias en formato unificado, sin las líneas que cambian solas (fechas)."""
    try:
        normalizar = marcas.respaldador(marca).normalizar_respaldo
    except marcas.MarcaNoSoportada:
        return ""
    return "\n".join(
        difflib.unified_diff(
            normalizar(anterior).split("\n"),
            normalizar(posterior).split("\n"),
            fromfile=nombre_anterior,
            tofile=nombre_posterior,
            lineterm="",
        )
    )


@dataclass
class Coincidencias:
    equipo: Equipo
    respaldo: Respaldo
    lineas: list[tuple[int, str]]  # (número de línea, texto)
    total: int


def buscar(
    db: Session,
    cifrador: Cifrador,
    texto: str,
    todas_las_versiones: bool = False,
    por_respaldo: int = 30,
) -> list[Coincidencias]:
    """Las líneas que contienen `texto` (sin distinguir mayúsculas) en los respaldos.

    Por defecto busca en la última versión de cada equipo; con todas_las_versiones,
    también en las anteriores (por ejemplo, para saber cuándo apareció una IP).
    """
    buscado = texto.lower()
    consulta = select(Respaldo).order_by(Respaldo.equipo_id, Respaldo.id.desc())
    vistos: set[int] = set()
    resultado: list[Coincidencias] = []
    for respaldo in db.scalars(consulta):
        if not todas_las_versiones and respaldo.equipo_id in vistos:
            continue
        vistos.add(respaldo.equipo_id)
        lineas = [
            (numero, linea.rstrip())
            for numero, linea in enumerate(contenido(respaldo, cifrador).splitlines(), start=1)
            if buscado in linea.lower()
        ]
        if lineas:
            equipo = db.get(Equipo, respaldo.equipo_id)
            if equipo is not None:
                resultado.append(
                    Coincidencias(equipo, respaldo, lineas[:por_respaldo], len(lineas))
                )
    resultado.sort(key=lambda c: (c.equipo.nombre.lower(), -c.respaldo.id))
    return resultado
