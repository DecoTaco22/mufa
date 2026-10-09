"""Alertas: avisar por Telegram, correo o webhook cuando pasa algo importante.

El despachador lee el registro de eventos (que ya anota caídas, cambios
de configuración, hallazgos críticos...) desde el último que procesó y
avisa a los canales suscritos a cada tipo. Así ninguna parte de mufa
tiene que saber de canales, y un envío que falla no frena nada.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mufa.cifrado import Cifrador
from mufa.db import AjusteSistema, CanalAlerta, Evento

log = logging.getLogger("mufa.alertas")

# Eventos que se pueden avisar, con el título del aviso.
TIPOS: dict[str, str] = {
    "equipo.caido": "Equipo caído",
    "equipo.recuperado": "Equipo recuperado",
    "equipo.reinicio": "Equipo reiniciado",
    "equipo.cambio_serie": "Cambió el número de serie del equipo",
    "interfaz.caida": "Interfaz caída",
    "interfaz.recuperada": "Interfaz recuperada",
    "interfaz.saturada": "Interfaz saturada",
    "interfaz.normal": "Interfaz sin saturación",
    "auditoria.critico": "Hallazgo crítico",
    "respaldo.cambio": "Cambió la configuración de un equipo",
    "respaldo.error": "Falló un respaldo",
}

_CURSOR = "alertas.ultimo_evento"
_TIEMPO_ESPERA = 10.0


@dataclass(frozen=True)
class Mensaje:
    tipo: str
    titulo: str
    objeto: str
    detalle: dict[str, object]
    momento: datetime

    @property
    def texto(self) -> str:
        lineas = [f"[mufa] {self.titulo}: {self.objeto}"]
        lineas += [f"{clave}: {valor}" for clave, valor in self.detalle.items()]
        return "\n".join(lineas)


Enviador = Callable[[CanalAlerta, str | None, Mensaje], None]


def _telegram(canal: CanalAlerta, token: str | None, mensaje: Mensaje) -> None:
    respuesta = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": canal.destino, "text": mensaje.texto},
        timeout=_TIEMPO_ESPERA,
    )
    respuesta.raise_for_status()


def firmar(secreto: str, cuerpo: bytes) -> str:
    """Firma HMAC-SHA256 del cuerpo: quien recibe el webhook comprueba que vino de mufa."""
    return hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()


def _webhook(canal: CanalAlerta, secreto: str | None, mensaje: Mensaje) -> None:
    cuerpo = json.dumps(
        {
            "tipo": mensaje.tipo,
            "titulo": mensaje.titulo,
            "objeto": mensaje.objeto,
            "detalle": mensaje.detalle,
            "momento": mensaje.momento.isoformat(),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    cabeceras = {"Content-Type": "application/json"}
    if secreto:
        cabeceras["X-Mufa-Firma"] = f"sha256={firmar(secreto, cuerpo)}"
    httpx.post(
        canal.destino, content=cuerpo, headers=cabeceras, timeout=_TIEMPO_ESPERA
    ).raise_for_status()


def _correo(canal: CanalAlerta, password: str | None, mensaje: Mensaje) -> None:
    config = canal.configuracion
    correo = EmailMessage()
    correo["Subject"] = f"[mufa] {mensaje.titulo}: {mensaje.objeto}"
    correo["From"] = str(config.get("remitente", config.get("usuario", "")))
    correo["To"] = canal.destino
    correo.set_content(mensaje.texto)
    host, puerto = str(config["servidor"]), int(config.get("puerto", 587))
    contexto = ssl.create_default_context()
    if puerto == 465:
        servidor: smtplib.SMTP = smtplib.SMTP_SSL(
            host, puerto, timeout=_TIEMPO_ESPERA, context=contexto
        )
    else:
        servidor = smtplib.SMTP(host, puerto, timeout=_TIEMPO_ESPERA)
        servidor.starttls(context=contexto)
    with servidor:
        if config.get("usuario"):
            servidor.login(str(config["usuario"]), password or "")
        servidor.send_message(correo)


_ENVIADORES: dict[str, Enviador] = {
    "telegram": _telegram,
    "webhook": _webhook,
    "correo": _correo,
}


def enviar(canal: CanalAlerta, secreto: str | None, mensaje: Mensaje) -> None:
    _ENVIADORES[canal.tipo](canal, secreto, mensaje)


def mensaje_de(evento: Evento) -> Mensaje:
    return Mensaje(
        tipo=evento.accion,
        titulo=TIPOS.get(evento.accion, evento.accion),
        objeto=evento.objeto,
        detalle=dict(evento.detalle),
        momento=evento.cuando,
    )


def _secreto(canal: CanalAlerta, cifrador: Cifrador) -> str | None:
    return cifrador.descifrar(canal.secreto_cifrado) if canal.secreto_cifrado else None


def procesar_pendientes(
    db: Session, cifrador: Cifrador, enviador: Enviador = enviar, lote: int = 200
) -> int:
    """Avisa los eventos nuevos desde la última pasada. Devuelve cuántos avisos salieron."""
    cursor = db.get(AjusteSistema, _CURSOR)
    if cursor is None:
        # Primera vez: no se avisa de todo lo que pasó antes de configurar alertas.
        ultimo = db.scalar(select(func.max(Evento.id))) or 0
        db.add(AjusteSistema(clave=_CURSOR, valor=str(ultimo)))
        db.flush()
        return 0

    eventos = list(
        db.scalars(
            select(Evento).where(Evento.id > int(cursor.valor)).order_by(Evento.id).limit(lote)
        )
    )
    if not eventos:
        return 0
    canales = list(db.scalars(select(CanalAlerta).where(CanalAlerta.activo.is_(True))))
    enviados = 0
    for evento in eventos:
        if evento.accion not in TIPOS:
            continue
        for canal in canales:
            if evento.accion not in canal.eventos:
                continue
            try:
                enviador(canal, _secreto(canal, cifrador), mensaje_de(evento))
                enviados += 1
            except Exception:  # un canal caído no frena a los demás
                log.exception("no se pudo avisar por el canal %s", canal.nombre)
    cursor.valor = str(eventos[-1].id)
    return enviados
