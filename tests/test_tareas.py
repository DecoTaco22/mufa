"""Tareas automáticas: sondeo y respaldo de todos los equipos de una pasada."""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mufa.config import Ajustes
from mufa.db import EstadoEquipo, Respaldo
from mufa.tareas import Programador
from tests.snmp_falso import CLAVE_AUTH, CLAVE_PRIV, USUARIO, AgenteSNMPFalso
from tests.ssh_falso import ServidorSSHFalso

API = "/api/v1"


def test_programador_inactivo_si_los_intervalos_son_cero(ajustes: Ajustes) -> None:
    assert not Programador(ajustes, None, None).activo  # type: ignore[arg-type]
    assert Programador(replace(ajustes, intervalo_respaldo_horas=24), None, None).activo  # type: ignore[arg-type]


def test_sondear_y_respaldar_todos(cliente: TestClient, admin: dict[str, str]) -> None:
    agente = AgenteSNMPFalso()
    router = ServidorSSHFalso(
        lambda c: "/system identity\nset name=r1\n" if c.startswith("/export") else ""
    )
    try:
        con_snmp = {
            "nombre": "Con SNMP",
            "marca": "zte",
            "ip_gestion": "127.0.0.1",
            "snmp": {
                "version": "3",
                "puerto": agente.puerto,
                "usuario": USUARIO,
                "clave_auth": CLAVE_AUTH,
                "clave_priv": CLAVE_PRIV,
                "protocolo_auth": "sha",
            },
        }
        con_ssh = {
            "nombre": "Con SSH",
            "marca": "mikrotik",
            "ip_gestion": "127.0.0.1",
            "puerto_ssh": router.puerto,
            "usuario_ssh": "mufa",
            "password_ssh": "clave-correcta",
        }
        for equipo in (con_snmp, con_ssh):
            assert cliente.post(f"{API}/equipos", json=equipo, headers=admin).status_code == 201

        estado = cliente.app.state.mufa  # type: ignore[attr-defined]
        programador = Programador(estado.ajustes, estado.sesiones, estado.cifrador)
        programador.sondear_todos()
        programador.respaldar_todos()

        with estado.sesiones() as db:
            assert db.scalar(select(func.count()).select_from(EstadoEquipo)) == 1
            assert db.scalar(select(EstadoEquipo.en_linea)) is True
            assert db.scalar(select(func.count()).select_from(Respaldo)) == 1
            assert db.scalar(select(Respaldo.origen)) == "programado"
    finally:
        agente.cerrar()
        router.cerrar()
