"""Calculadoras de fibra óptica.

Las reglas de conectores, empalmes y penalidades vienen del material del
curso de mediciones ópticas que acompaña al proyecto:

- Conectores del mismo fabricante (monomodo): 0,20 dB ± 0,15 dB.
- Conectores de fabricantes distintos: 0,35 dB ± 0,25 dB.
- La desviación de n conectores se suma como σ·√n (teorema del límite central).
- Relación de extinción de 10 dB: 1 dB de penalidad (PIN o APD).
  De 3 dB: 5 dB con PIN y 7 dB con APD.
- La dispersión no debería ocupar más del 20 % del periodo de bit.

La atenuación por km (0,35 dB/km a 1310 nm y 0,22 dB/km a 1550 nm) es un
valor típico de fibra monomodo estándar: conviene usar el del fabricante.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

ATENUACION_TIPICA = {1310: 0.35, 1550: 0.22}
CONECTORES = {"mismo": (0.20, 0.15), "mixto": (0.35, 0.25)}
DISPERSION_MAXIMA_DEL_PERIODO = 0.20
DISPERSION_DCF = -100.0  # ps/nm/km


def penalidad_extincion(relacion_db: Literal[10, 3], receptor: Literal["pin", "apd"]) -> float:
    if relacion_db == 10:
        return 1.0
    return 5.0 if receptor == "pin" else 7.0


@dataclass(frozen=True)
class Presupuesto:
    perdida_fibra: float
    perdida_conectores: float
    perdida_empalmes: float
    penalidad: float
    perdida_total: float
    potencia_esperada_rx: float
    margen: float
    cierra: bool
    con_margen_suficiente: bool
    distancia_maxima_km: float


def presupuesto_optico(
    potencia_tx_dbm: float,
    sensibilidad_rx_dbm: float,
    distancia_km: float,
    atenuacion_db_km: float,
    conectores: int,
    tipo_conectores: Literal["mismo", "mixto"],
    empalmes: int,
    perdida_empalme_db: float,
    penalidad_db: float,
    margen_seguridad_db: float,
) -> Presupuesto:
    media, desviacion = CONECTORES[tipo_conectores]
    perdida_conectores = conectores * media + desviacion * math.sqrt(conectores)
    perdida_empalmes = empalmes * perdida_empalme_db
    perdida_fibra = distancia_km * atenuacion_db_km
    total = perdida_fibra + perdida_conectores + perdida_empalmes + penalidad_db
    esperada = potencia_tx_dbm - total
    margen = esperada - sensibilidad_rx_dbm
    disponible_para_fibra = (
        potencia_tx_dbm
        - sensibilidad_rx_dbm
        - margen_seguridad_db
        - perdida_conectores
        - perdida_empalmes
        - penalidad_db
    )
    return Presupuesto(
        perdida_fibra=perdida_fibra,
        perdida_conectores=perdida_conectores,
        perdida_empalmes=perdida_empalmes,
        penalidad=penalidad_db,
        perdida_total=total,
        potencia_esperada_rx=esperada,
        margen=margen,
        cierra=margen >= 0,
        con_margen_suficiente=margen >= margen_seguridad_db,
        distancia_maxima_km=max(0.0, disponible_para_fibra / atenuacion_db_km),
    )


@dataclass(frozen=True)
class Dispersion:
    total_ps: float
    periodo_bit_ps: float
    porcentaje_del_periodo: float
    dentro_del_limite: bool
    dcf_para_compensar_km: float


def dispersion_cromatica(
    coeficiente_ps_nm_km: float, ancho_espectral_nm: float, distancia_km: float, tasa_gbps: float
) -> Dispersion:
    total = coeficiente_ps_nm_km * ancho_espectral_nm * distancia_km
    periodo = 1000 / tasa_gbps
    porcentaje = total / periodo * 100
    return Dispersion(
        total_ps=total,
        periodo_bit_ps=periodo,
        porcentaje_del_periodo=porcentaje,
        dentro_del_limite=porcentaje <= DISPERSION_MAXIMA_DEL_PERIODO * 100,
        dcf_para_compensar_km=coeficiente_ps_nm_km * distancia_km / abs(DISPERSION_DCF),
    )


@dataclass(frozen=True)
class AperturaNumerica:
    apertura: float
    angulo_aceptacion_grados: float


def apertura_numerica(n_nucleo: float, n_revestimiento: float) -> AperturaNumerica:
    """NA = √(n1² − n2²) y el ángulo máximo con que la luz entra al núcleo."""
    if n_nucleo <= n_revestimiento:
        raise ValueError("el índice del núcleo tiene que ser mayor que el del revestimiento")
    apertura = math.sqrt(n_nucleo**2 - n_revestimiento**2)
    return AperturaNumerica(
        apertura=apertura,
        angulo_aceptacion_grados=math.degrees(math.asin(min(1.0, apertura))),
    )
