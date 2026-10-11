"""Calculadoras de fibra óptica."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from mufa import fibra
from mufa.api.deps import requiere
from mufa.api.esquemas import AperturaEntrada, DispersionEntrada, PresupuestoEntrada
from mufa.db import Usuario
from mufa.permisos import Permiso

router = APIRouter(prefix="/fibra", tags=["fibra"])

Lector = Annotated[Usuario, Depends(requiere(Permiso.VER))]


@router.post("/presupuesto")
def presupuesto(entrada: PresupuestoEntrada, _: Lector) -> dict[str, float | bool]:
    atenuacion = entrada.atenuacion_db_km or fibra.ATENUACION_TIPICA[entrada.longitud_onda_nm]
    resultado = fibra.presupuesto_optico(
        potencia_tx_dbm=entrada.potencia_tx_dbm,
        sensibilidad_rx_dbm=entrada.sensibilidad_rx_dbm,
        distancia_km=entrada.distancia_km,
        atenuacion_db_km=atenuacion,
        conectores=entrada.conectores,
        tipo_conectores=entrada.tipo_conectores,
        empalmes=entrada.empalmes,
        perdida_empalme_db=entrada.perdida_empalme_db,
        penalidad_db=fibra.penalidad_extincion(entrada.relacion_extincion_db, entrada.receptor),
        margen_seguridad_db=entrada.margen_seguridad_db,
    )
    return {"atenuacion_db_km": atenuacion, **asdict(resultado)}


@router.post("/dispersion")
def dispersion(entrada: DispersionEntrada, _: Lector) -> dict[str, float | bool]:
    return asdict(fibra.dispersion_cromatica(**entrada.model_dump()))


@router.post("/apertura-numerica")
def apertura(entrada: AperturaEntrada, _: Lector) -> dict[str, float]:
    try:
        return asdict(fibra.apertura_numerica(entrada.n_nucleo, entrada.n_revestimiento))
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
