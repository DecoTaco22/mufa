"""IPAM, VLANs y calculadoras de fibra."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mufa import fibra

API = "/api/v1"


def _prefijo(cliente: TestClient, admin: dict[str, str], prefijo: str, **extra: object) -> dict:
    respuesta = cliente.post(
        f"{API}/ipam/prefijos", json={"prefijo": prefijo, **extra}, headers=admin
    )
    assert respuesta.status_code == 201, respuesta.text
    return dict(respuesta.json())


def test_prefijos_anidados_uso_y_siguiente_libre(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    gestion = _prefijo(cliente, admin, "10.20.0.0/16", descripcion="Gestión")
    norte = _prefijo(cliente, admin, "10.20.4.7/30", descripcion="Nodo Norte")  # se normaliza
    assert norte["prefijo"] == "10.20.4.4/30"
    assert norte["contenido_en"] == gestion["id"]
    assert norte["utilizables"] == 2

    # Sin ip: la siguiente libre (la .4 es la red, no es asignable).
    primera = cliente.post(f"{API}/ipam/prefijos/{norte['id']}/ips", json={}, headers=admin).json()
    assert primera["ip"] == "10.20.4.5"
    segunda = cliente.post(
        f"{API}/ipam/prefijos/{norte['id']}/ips", json={"descripcion": "CCR"}, headers=admin
    ).json()
    assert segunda["ip"] == "10.20.4.6"
    lleno = cliente.post(f"{API}/ipam/prefijos/{norte['id']}/ips", json={}, headers=admin)
    assert lleno.status_code == 409

    norte = cliente.get(f"{API}/ipam/prefijos/{norte['id']}", headers=admin).json()
    assert (norte["asignadas"], norte["porcentaje_uso"]) == (2, 100.0)
    # Las direcciones del hijo cuentan también en el padre.
    assert (
        cliente.get(f"{API}/ipam/prefijos/{gestion['id']}", headers=admin).json()["asignadas"] == 2
    )

    busqueda = cliente.get(f"{API}/ipam/buscar?ip=10.20.4.6", headers=admin).json()
    assert {p["prefijo"] for p in busqueda["prefijos"]} == {"10.20.0.0/16", "10.20.4.4/30"}
    assert busqueda["asignacion"]["descripcion"] == "CCR"


def test_ipam_rechaza_duplicados_y_direcciones_fuera(
    cliente: TestClient, admin: dict[str, str]
) -> None:
    red = _prefijo(cliente, admin, "192.168.10.0/24")
    assert (
        cliente.post(
            f"{API}/ipam/prefijos", json={"prefijo": "192.168.10.0/24"}, headers=admin
        ).status_code
        == 409
    )
    assert (
        cliente.post(
            f"{API}/ipam/prefijos", json={"prefijo": "no-es-red"}, headers=admin
        ).status_code
        == 422
    )
    url = f"{API}/ipam/prefijos/{red['id']}/ips"
    assert cliente.post(url, json={"ip": "192.168.11.1"}, headers=admin).status_code == 422
    assert (
        cliente.post(url, json={"ip": "192.168.10.255"}, headers=admin).status_code == 422
    )  # broadcast
    assert cliente.post(url, json={"ip": "192.168.10.1"}, headers=admin).status_code == 201
    assert cliente.post(url, json={"ip": "192.168.10.1"}, headers=admin).status_code == 409


def test_ipv6(cliente: TestClient, admin: dict[str, str]) -> None:
    red = _prefijo(cliente, admin, "2001:db8:100::/48")
    assert red["porcentaje_uso"] is None  # demasiado grande para un porcentaje útil
    ip = cliente.post(f"{API}/ipam/prefijos/{red['id']}/ips", json={}, headers=admin).json()
    assert ip["ip"] == "2001:db8:100::"


def test_vlans_sin_duplicados_por_dominio(cliente: TestClient, admin: dict[str, str]) -> None:
    anillo = cliente.post(
        f"{API}/vlans/dominios", json={"nombre": "Anillo Central"}, headers=admin
    ).json()
    sur = cliente.post(f"{API}/vlans/dominios", json={"nombre": "Nodo Sur"}, headers=admin).json()

    url = f"{API}/vlans/dominios/{anillo['id']}/vlans"
    assert (
        cliente.post(url, json={"numero": 100, "nombre": "GESTION"}, headers=admin).status_code
        == 201
    )
    duplicada = cliente.post(url, json={"numero": 100, "nombre": "PPPOE"}, headers=admin)
    assert duplicada.status_code == 409
    assert "GESTION" in duplicada.json()["detail"]
    # El mismo número en otro dominio de capa 2 no choca.
    otra = cliente.post(
        f"{API}/vlans/dominios/{sur['id']}/vlans",
        json={"numero": 100, "nombre": "PPPOE"},
        headers=admin,
    )
    assert otra.status_code == 201

    libre = cliente.post(url, json={"desde": 100, "nombre": "VOIP"}, headers=admin).json()
    assert libre["numero"] == 101
    assert [v["numero"] for v in cliente.get(url, headers=admin).json()] == [100, 101]


def test_cambiar_la_mascara_de_un_prefijo(cliente: TestClient, admin: dict[str, str]) -> None:
    prefijo = _prefijo(cliente, admin, "192.168.1.0/24")
    url = f"{API}/ipam/prefijos/{prefijo['id']}"
    cliente.post(f"{url}/ips", json={"ip": "192.168.1.200"}, headers=admin)

    ampliado = cliente.patch(url, json={"prefijo": "192.168.0.0/23"}, headers=admin)
    assert ampliado.status_code == 200, ampliado.text
    assert ampliado.json()["prefijo"] == "192.168.0.0/23"

    # La .200 no cabe en un /25: no se pierde en silencio.
    chico = cliente.patch(url, json={"prefijo": "192.168.1.0/25"}, headers=admin)
    assert chico.status_code == 409
    assert "192.168.1.200" in chico.json()["detail"]

    _prefijo(cliente, admin, "10.0.0.0/24")
    repetido = cliente.patch(url, json={"prefijo": "10.0.0.0/24"}, headers=admin)
    assert repetido.status_code == 409

    solo_texto = cliente.patch(url, json={"descripcion": "LAN"}, headers=admin).json()
    assert (solo_texto["prefijo"], solo_texto["descripcion"]) == ("192.168.0.0/23", "LAN")


def test_vlan_en_equipos_a_mano(cliente: TestClient, admin: dict[str, str]) -> None:
    equipo = cliente.post(
        f"{API}/equipos",
        json={"nombre": "CCR Norte", "marca": "mikrotik", "ip_gestion": "10.0.0.1", "snmp": None},
        headers=admin,
    ).json()
    dominio = cliente.post(f"{API}/vlans/dominios", json={"nombre": "Anillo"}, headers=admin).json()
    vlan = cliente.post(
        f"{API}/vlans/dominios/{dominio['id']}/vlans",
        json={
            "numero": 20,
            "nombre": "PPPOE",
            "equipos": [{"equipo_id": equipo["id"], "interfaz": "sfp1"}],
        },
        headers=admin,
    ).json()
    assert [(e["equipo"], e["interfaz"]) for e in vlan["equipos"]] == [("CCR Norte", "sfp1")]

    otra = cliente.post(
        f"{API}/vlans/{vlan['id']}/equipos", json={"equipo_id": equipo["id"]}, headers=admin
    ).json()
    assert len(otra["equipos"]) == 2
    # Repetir lo mismo no duplica.
    otra = cliente.post(
        f"{API}/vlans/{vlan['id']}/equipos", json={"equipo_id": equipo["id"]}, headers=admin
    ).json()
    assert len(otra["equipos"]) == 2

    url = f"{API}/vlans/{vlan['id']}/equipos/{equipo['id']}?interfaz=sfp1"
    assert cliente.delete(url, headers=admin).status_code == 204
    assert cliente.delete(url, headers=admin).status_code == 404
    lista = cliente.get(f"{API}/vlans/dominios/{dominio['id']}/vlans", headers=admin).json()
    assert [e["interfaz"] for e in lista[0]["equipos"]] == [""]
    sin_equipo = cliente.post(
        f"{API}/vlans/{vlan['id']}/equipos", json={"equipo_id": 9999}, headers=admin
    )
    assert sin_equipo.status_code == 422


def test_presupuesto_optico() -> None:
    resultado = fibra.presupuesto_optico(
        potencia_tx_dbm=0,
        sensibilidad_rx_dbm=-24,
        distancia_km=40,
        atenuacion_db_km=0.22,
        conectores=4,
        tipo_conectores="mismo",
        empalmes=12,
        perdida_empalme_db=0.1,
        penalidad_db=fibra.penalidad_extincion(10, "pin"),
        margen_seguridad_db=3,
    )
    assert resultado.perdida_fibra == pytest.approx(8.8)
    assert resultado.perdida_conectores == pytest.approx(4 * 0.2 + 0.15 * 2)  # n·media + σ√n
    assert resultado.perdida_empalmes == pytest.approx(1.2)
    assert resultado.potencia_esperada_rx == pytest.approx(-12.1)
    assert resultado.margen == pytest.approx(11.9)
    assert resultado.con_margen_suficiente


def test_dispersion_ejemplo_del_curso() -> None:
    # 17 ps/nm/km, láser de 6 nm, 10 km: 1020 ps.
    resultado = fibra.dispersion_cromatica(17, 6, 10, tasa_gbps=1)
    assert resultado.total_ps == pytest.approx(1020)
    assert not resultado.dentro_del_limite
    assert resultado.dcf_para_compensar_km == pytest.approx(1.7)


def test_penalidades_de_extincion() -> None:
    assert fibra.penalidad_extincion(10, "apd") == 1
    assert fibra.penalidad_extincion(3, "pin") == 5
    assert fibra.penalidad_extincion(3, "apd") == 7


def test_fibra_por_la_api(cliente: TestClient, admin: dict[str, str]) -> None:
    presupuesto = cliente.post(
        f"{API}/fibra/presupuesto",
        json={"potencia_tx_dbm": 0, "sensibilidad_rx_dbm": -24, "distancia_km": 40},
        headers=admin,
    ).json()
    assert presupuesto["atenuacion_db_km"] == 0.22
    apertura = cliente.post(
        f"{API}/fibra/apertura-numerica",
        json={"n_nucleo": 1.4682, "n_revestimiento": 1.4629},
        headers=admin,
    ).json()
    assert apertura["apertura"] == pytest.approx(0.1247, abs=1e-3)
    invertida = cliente.post(
        f"{API}/fibra/apertura-numerica",
        json={"n_nucleo": 1.46, "n_revestimiento": 1.47},
        headers=admin,
    )
    assert invertida.status_code == 422
