#!/usr/bin/env python3
"""Guarda las respuestas de la API de un servidor con datos de ejemplo: los datos de la demo.

    uv run python scripts/capturar_demo.py http://127.0.0.1:8099 <password> salida.json

El servidor tiene que tener cargados los datos de scripts/datos_demo.py. La demo
del sitio (web, modo «demo») responde con este archivo en vez de llamar a un servidor.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

base, password, salida = sys.argv[1], sys.argv[2], Path(sys.argv[3])
c = httpx.Client(
    base_url=f"{base}/api/v1", headers={"X-Mufa-Cliente": "web", "X-Mufa-Csrf": "1"}, timeout=60
)
assert c.post("/auth/login", json={"usuario": "demo", "password": password}).status_code == 200
datos: dict[str, object] = {}


def tomar(ruta: str) -> object | None:
    r = c.get(ruta)
    if r.status_code != 200:
        print(f"  {r.status_code} {ruta}")
        return None
    datos[ruta] = r.json()
    return datos[ruta]


for ruta in [
    "/auth/yo",
    "/licencia",
    "/panel",
    "/equipos",
    "/marcas",
    "/sitios",
    "/hallazgos",
    "/mapa",
    "/alertas/canales",
    "/alertas/tipos",
    "/eventos?limite=500",
    "/usuarios",
    "/prefijos",
    "/ipam/prefijos",
    "/vlans/dominios",
    "/respaldos",
    "/respaldos/programa",
    "/respaldos/destino",
    "/pro/avisos/ajustes",
    "/pro/avisos/contactos",
    "/pro/avisos/guardias",
    "/pro/avisos/incidentes?limite=30",
    "/pro/capacidad",
    "/pro/consumo/ajustes",
    "/pro/estado-publico",
    "/pro/estado-publico/vista-previa",
    "/pro/estado-publico/pagina/demo",
    "/pro/informes/ajustes",
    "/pro/mantenimiento",
    "/pro/olt",
    "/sistema/actualizacion",
    "/monitoreo/resumen",
]:
    tomar(ruta)

for e in datos.get("/equipos") or []:  # type: ignore[union-attr]
    i = e["id"]
    tomar(f"/equipos/{i}")
    tomar(f"/equipos/{i}/interfaces")
    tomar(f"/equipos/{i}/respaldos")
    tomar(f"/equipos/{i}/vigiladas")
    tomar(f"/equipos/{i}/estado")
    for a in tomar(f"/auditorias?equipo_id={i}&limite=1") or []:  # type: ignore[union-attr]
        tomar(f"/auditorias/{a['id']}")
    for r in datos.get(f"/equipos/{i}/respaldos") or []:  # type: ignore[union-attr]
        tomar(f"/respaldos/{r['id']}")
        tomar(f"/respaldos/{r['id']}/diferencias")
for p in datos.get("/prefijos") or []:  # type: ignore[union-attr]
    tomar(f"/prefijos/{p['id']}")
    tomar(f"/prefijos/{p['id']}/ips")
    tomar(f"/ipam/prefijos/{p['id']}/ips")
for d in datos.get("/vlans/dominios") or []:  # type: ignore[union-attr]
    for v in tomar(f"/vlans/dominios/{d['id']}/vlans") or []:  # type: ignore[union-attr]
        tomar(f"/vlans/{v['id']}/equipos")
for p in datos.get("/pro/capacidad") or []:  # type: ignore[union-attr]
    tomar(f"/pro/capacidad/{p['equipo_id']}/{p['if_index']}")
for dias in (1, 7, 30):
    for cliente in tomar(f"/pro/consumo?dias={dias}") or []:  # type: ignore[union-attr]
        if dias == 1:
            tomar(f"/pro/consumo/{cliente['ip']}?dias=7")
for olt in datos.get("/pro/olt") or []:  # type: ignore[union-attr]
    i = olt["equipo_id"]
    tomar(f"/pro/olt/{i}/puertos")
    tomar(f"/pro/olt/{i}/onus")
    for filtro in (
        "estado=caidas",
        "estado=sin_senal",
        "estado=sin_energia",
        "senal_baja=true",
        "degradando=true",
    ):
        tomar(f"/pro/olt/{i}/onus?{filtro}")
    for p in datos.get(f"/pro/olt/{i}/puertos") or []:  # type: ignore[union-attr]
        tomar(f"/pro/olt/{i}/onus?puerto={p['pon_if_index']}")
ahora = datetime.now(UTC)
for mes in (
    f"{ahora.year}-{ahora.month:02d}",
    f"{ahora.year if ahora.month > 1 else ahora.year - 1}-{(ahora.month - 2) % 12 + 1:02d}",
):
    tomar(f"/pro/informes/resumen?mes={mes}")

# La demo corre las fechas: «hace 2 min» sigue siendo «hace 2 min» semanas después.
datos["_capturado"] = datetime.now(UTC).isoformat()
salida.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{len(datos)} respuestas, {salida.stat().st_size // 1024} KB en {salida}")
