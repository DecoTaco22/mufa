"""Agente SNMP real (pysnmp) en 127.0.0.1 para probar el sondeo sin un equipo.

Responde con la instrumentación propia de pysnmp: el grupo `system` del
SNMPv2-MIB (sysDescr, sysObjectID, sysUpTime...). No tiene ifTable.
"""

from __future__ import annotations

import asyncio
import socket
import threading

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context

USUARIO = "mufa-sha-aes"
CLAVE_AUTH = "clave-de-autenticacion"
CLAVE_PRIV = "clave-de-privacidad"
COMUNIDAD = "comunidad-de-prueba"


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class AgenteSNMPFalso:
    def __init__(self) -> None:
        self.puerto = _puerto_libre()
        self._listo = threading.Event()
        self._bucle: asyncio.AbstractEventLoop | None = None
        self._hilo = threading.Thread(target=self._correr, daemon=True)
        self._hilo.start()
        if not self._listo.wait(10):
            raise RuntimeError("el agente SNMP de prueba no arrancó")

    def _correr(self) -> None:
        self._bucle = asyncio.new_event_loop()
        asyncio.set_event_loop(self._bucle)
        motor = engine.SnmpEngine()
        config.add_transport(
            motor,
            udp.DOMAIN_NAME,
            udp.UdpTransport().open_server_mode(("127.0.0.1", self.puerto)),
        )
        config.add_v3_user(
            motor,
            USUARIO,
            config.USM_AUTH_HMAC96_SHA,
            CLAVE_AUTH,
            config.USM_PRIV_CFB128_AES,
            CLAVE_PRIV,
        )
        config.add_v1_system(motor, "area-prueba", COMUNIDAD)
        config.add_vacm_user(motor, 3, USUARIO, "authPriv", (1, 3, 6), (1, 3, 6))
        config.add_vacm_user(motor, 2, "area-prueba", "noAuthNoPriv", (1, 3, 6))
        contexto = context.SnmpContext(motor)
        cmdrsp.GetCommandResponder(motor, contexto)
        cmdrsp.NextCommandResponder(motor, contexto)
        cmdrsp.BulkCommandResponder(motor, contexto)
        motor.transport_dispatcher.job_started(1)
        self._bucle.call_soon(self._listo.set)
        try:
            motor.open_dispatcher()  # corre hasta que cerrar() detiene el bucle
        finally:
            motor.close_dispatcher()

    def cerrar(self) -> None:
        if self._bucle is not None:
            self._bucle.call_soon_threadsafe(self._bucle.stop)
        self._hilo.join(5)
