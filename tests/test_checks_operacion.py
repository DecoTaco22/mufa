"""Versiones con CVE, NTP, log remoto y puntaje de seguridad."""

from __future__ import annotations

import pytest

from mufa.checks.versiones import version_numerica
from mufa.engine import evaluar
from mufa.marcas.mikrotik import contexto_desde_texto
from mufa.models import Contexto
from mufa.servicios import puntaje


def _ids(ctx: Contexto) -> set[str]:
    return {h.id for h in evaluar(ctx)}


@pytest.mark.parametrize(
    ("version", "cves"),
    [
        ("6.40.7", {"CVE-2018-14847", "CVE-2023-30799", "CVE-2019-3978"}),
        ("6.48.6", {"CVE-2023-30799"}),
        ("6.48.7", set()),
        ("6.49.6", {"CVE-2023-30799"}),
        ("6.49.10", set()),
        ("7.11.2", {"CVE-2023-41570"}),
        ("7.16", set()),
    ],
)
def test_routeros_con_cve(version: str, cves: set[str]) -> None:
    hallazgos = [
        h for h in evaluar(Contexto(marca="mikrotik", version=version)) if h.id == "MUFA-VER-001"
    ]
    encontradas = {c for c in cves if hallazgos and c in hallazgos[0].evidencia}
    assert encontradas == cves
    assert bool(hallazgos) == bool(cves)


def test_el_peor_cve_define_la_severidad() -> None:
    (hallazgo,) = [h for h in evaluar(Contexto(version="6.40.7")) if h.id == "MUFA-VER-001"]
    assert hallazgo.severidad.value == "crítico"


def test_version_numerica() -> None:
    assert version_numerica("6.48.6 (long-term)") == (6, 48, 6)
    assert version_numerica("7.15rc2") == (7, 15)
    assert version_numerica("") is None


def test_version_desde_la_cabecera_del_export() -> None:
    texto = "# 2026-10-05 12:00:00 by RouterOS 6.48.6\n# software id = X\n/ip dns\nset allow-remote-requests=no\n"
    assert contexto_desde_texto(texto).version == "6.48.6"


def test_ntp_y_log_remoto_de_mikrotik() -> None:
    sin_nada = (
        "/system ntp client\nset enabled=no primary-ntp=0.0.0.0\n"
        "/system logging action\nset 3 remote=0.0.0.0\n"
        "/system logging\nadd topics=info action=memory\n"
    )
    assert {"MUFA-NTP-001", "MUFA-LOG-001"} <= _ids(contexto_desde_texto(sin_nada))

    bien = (
        "/system ntp client\nset enabled=yes servers=10.0.0.1\n"
        "/system logging action\nadd name=syslog target=remote remote=10.0.0.2\n"
        "/system logging\nadd topics=info action=syslog\n"
    )
    assert not {"MUFA-NTP-001", "MUFA-LOG-001"} & _ids(contexto_desde_texto(bien))


def test_un_export_parcial_no_opina_de_ntp_ni_logs() -> None:
    ctx = contexto_desde_texto("/ip dns\nset allow-remote-requests=no\n")
    assert (ctx.ntp_activo, ctx.log_remoto) == (None, None)


def test_puntaje() -> None:
    assert puntaje([]) == 100
    assert puntaje(["crítico"]) == 70
    assert puntaje(["crítico"] * 4) == 0
    assert puntaje(["alto", "medio", "info"]) == 76
