#!/usr/bin/env python3
"""Llena una base de mufa con una red de ejemplo: la que se ve en la demo del sitio.

    uv run python scripts/datos_demo.py <carpeta-de-datos>

Un ISP ficticio («Fibra Ejemplo») con IPs de documentación y redes privadas:
nada de una red real. Crea la base si no existe; borra lo que hubiera antes.
Deja la contraseña del usuario «demo» en <carpeta>/demo-password.txt.
"""

from __future__ import annotations

import hashlib
import math
import random
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mufa import marcas
from mufa.auth import hashear_password
from mufa.cifrado import Cifrador, cargar_o_crear_clave
from mufa.db import (
    AjusteSistema,
    Auditoria,
    CanalAlerta,
    ConsumoIP,
    ContactoNoc,
    DireccionIP,
    DominioL2,
    Equipo,
    EstadoEquipo,
    Evento,
    Guardia,
    InterfazVigilada,
    MuestraInterfaz,
    Olt,
    OnuGpon,
    PotenciaOnuDiaria,
    Prefijo,
    Respaldo,
    Sitio,
    TraficoDiario,
    Usuario,
    Vecino,
    Vlan,
    VlanEnEquipo,
    crear_motor,
    fabrica_de_sesiones,
)
from mufa.migraciones import actualizar_base
from mufa.pro import estado_publico, mantenimiento
from mufa.servicios import _guardar_resultado

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures"
AHORA = datetime.now(UTC).replace(second=0, microsecond=0)
azar = random.Random(7)

# nombre, marca, modelo, ip, sitio, version, en_linea, configuración de ejemplo
EQUIPOS = [
    (
        "CORE-CENTRO",
        "mikrotik",
        "CCR2116-12G-4S+",
        "10.10.0.1",
        "Centro",
        "7.16.2",
        True,
        "dns_abierto.rsc",
    ),
    ("BORDE-INTERNET", "cisco", "ISR4431", "10.10.0.2", "Centro", "17.9.4a", True, "cisco_ios.txt"),
    (
        "SW-DISTRIBUCION",
        "huawei",
        "S5735-L24T4X",
        "10.10.0.20",
        "Centro",
        "V200R022C00",
        True,
        "huawei_vrp.txt",
    ),
    ("OLT-CENTRO", "huawei", "MA5800-X7", "10.10.0.10", "Centro", "V100R021", True, None),
    (
        "NODO-NORTE",
        "mikrotik",
        "CCR2004-1G-12S+2XS",
        "10.10.1.1",
        "Nodo Norte",
        "6.49.10",
        True,
        "defconf.rsc",
    ),
    (
        "NODO-SUR",
        "mikrotik",
        "RB5009UG+S+",
        "10.10.2.1",
        "Nodo Sur",
        "7.16.2",
        True,
        "dns_cerrado.rsc",
    ),
    (
        "AP-SECTOR-NORTE",
        "ubiquiti",
        "Rocket 5AC Prism",
        "10.10.1.20",
        "Nodo Norte",
        "8.7.11",
        False,
        None,
    ),
    ("RT-CLIENTE-CORP", "mikrotik", "hEX S", "10.10.3.1", "Nodo Sur", "7.15.3", True, None),
]
CLIENTES = [
    "Ferretería El Sol",
    "Hotel Las Palmas",
    "Clínica San Juan",
    "Colegio Bilingüe Montessori",
    "Café La Esquina",
    "Juan Pérez · 50M",
    "María López · 20M",
    "Panadería Rosita",
    "Farmacia Popular",
    "Bufete Méndez",
    "Escuela Rural Aldea Norte",
    "Taller Mecánico Ruiz",
    "Agroservicio El Campo",
    "Restaurante Don Pepe",
    "Carlos Gómez · 100M",
    "Ana Morales · 30M",
    "Gasolinera Central",
    "Óptica Visión",
    "Lavandería Express",
    "Pedro Castillo · 20M",
]


def hace(**delta: float) -> datetime:
    return AHORA - timedelta(**delta)


def main(carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / "mufa.db"
    if base.exists():
        base.unlink()
    url = f"sqlite:///{base.as_posix()}"
    actualizar_base(url)
    cifrador = Cifrador(cargar_o_crear_clave(carpeta / "secreto.key"))
    sesiones = fabrica_de_sesiones(crear_motor(url))
    password = "Demo-" + secrets.token_urlsafe(12)
    (carpeta / "demo-password.txt").write_text(password, encoding="utf-8")

    with sesiones() as db:
        usuarios = {}
        for usuario, nombre, rol in [
            ("demo", "Diego (demo)", "admin"),
            ("ana", "Ana Pérez", "tecnico_n2"),
            ("carlos", "Carlos NOC", "agente_n1"),
            ("gerencia", "Gerencia", "lectura"),
        ]:
            u = Usuario(
                usuario=usuario,
                nombre=nombre,
                rol=rol,
                hash_password=hashear_password(
                    password if usuario == "demo" else secrets.token_urlsafe(16)
                ),
                creado=hace(days=60),
            )
            db.add(u)
            usuarios[usuario] = u
        sitios = {}
        for nombre, desc in [
            ("Centro", "Data center principal"),
            ("Nodo Norte", "Torre cerro norte"),
            ("Nodo Sur", "Torre colonia sur"),
        ]:
            sitios[nombre] = Sitio(nombre=nombre, descripcion=desc)
            db.add(sitios[nombre])
        db.flush()

        equipos: dict[str, Equipo] = {}
        for nombre, marca, modelo, ip, sitio, version, en_linea, fixture in EQUIPOS:
            e = Equipo(
                nombre=nombre,
                marca=marca,
                modelo=modelo,
                ip_gestion=ip,
                sitio_id=sitios[sitio].id,
                usuario_ssh="mufa-lectura" if marca in marcas.RESPALDADORES else "",
                password_cifrada=cifrador.cifrar("demo") if marca in marcas.RESPALDADORES else None,
                snmp_version="3",
                snmp_usuario="mufa",
                snmp_auth_cifrada=cifrador.cifrar("demo-auth"),
                snmp_priv_cifrada=cifrador.cifrar("demo-priv"),
                numero_serie=f"{marca[:2].upper()}{azar.randrange(10**8):08d}",
                creado=hace(days=120),
            )
            db.add(e)
            db.flush()
            equipos[nombre] = e
            db.add(
                EstadoEquipo(
                    equipo_id=e.id,
                    en_linea=en_linea,
                    alcanzable=en_linea,
                    ultimo_sondeo=hace(minutes=2),
                    ultimo_en_linea=hace(minutes=2) if en_linea else hace(hours=3),
                    error="" if en_linea else "Sin respuesta SNMP (tiempo agotado)",
                    sys_nombre=nombre,
                    sys_descripcion=f"{marca} {modelo}",
                    marca_detectada=marca,
                    uptime_segundos=azar.randrange(3, 90) * 86400 if en_linea else None,
                    ubicacion=sitio,
                    serie=e.numero_serie,
                    modelo=modelo,
                    version=version,
                )
            )
            if fixture:
                texto = (FIXTURES / fixture).read_text(encoding="utf-8")
                a = Auditoria(
                    equipo_id=e.id,
                    origen="ssh",
                    etiqueta=nombre,
                    marca=marca,
                    inicio=hace(hours=5),
                    usuario_id=None,
                )
                db.add(a)
                _guardar_resultado(a, marcas.obtener(marca).contexto_desde_texto(texto))
                a.fin = hace(hours=5)
                # Dos versiones de la configuración: ayer se cambió algo.
                previa = texto.replace("\n", "\n", 1)
                cambio = {
                    "mikrotik": '\n/ip firewall address-list\nadd address=198.51.100.0/24 list=bloqueados comment="ataque SSH"\n',
                    "cisco": "\n!\nip route 0.0.0.0 0.0.0.0 203.0.113.1 name RESPALDO\n",
                    "huawei": "\n#\nvlan batch 100 200 300\n",
                }[marca]
                for i, contenido in enumerate([previa, texto + cambio]):
                    normal = marcas.respaldador(marca).normalizar_respaldo(contenido)
                    db.add(
                        Respaldo(
                            equipo_id=e.id,
                            origen="programado",
                            creado=hace(days=6 - 5 * i),
                            confirmado=hace(hours=12),
                            hash_normalizado=hashlib.sha256(normal.encode()).hexdigest(),
                            tamano=len(contenido),
                            contenido_cifrado=cifrador.cifrar(contenido),
                        )
                    )
        db.flush()

        # Tráfico de las últimas 24 h (muestras cada 5 minutos).
        interfaces = {
            "CORE-CENTRO": [
                (1, "sfp-sfpplus1 · Internet", 10000, 6200),
                (2, "sfp-sfpplus2 · Nodo Norte", 10000, 2600),
                (3, "sfp-sfpplus3 · Nodo Sur", 10000, 1900),
            ],
            "NODO-NORTE": [
                (1, "sfp-sfpplus1 · Core", 10000, 2600),
                (2, "ether2 · AP Sector", 1000, 610),
            ],
            "NODO-SUR": [
                (1, "sfp-sfpplus1 · Core", 10000, 1900),
                (2, "ether3 · Cliente corp", 1000, 120),
            ],
            "BORDE-INTERNET": [(1, "Te0/0/0 · ISP mayorista", 10000, 6300)],
        }
        for nombre, lista in interfaces.items():
            e = equipos[nombre]
            for if_index, if_nombre, velocidad, pico_mbps in lista:
                entrada = salida = 0
                for paso in range(288, -1, -1):
                    momento = AHORA - timedelta(minutes=5 * paso)
                    hora = momento.hour + momento.minute / 60
                    curva = 0.35 + 0.65 * max(0.0, math.sin((hora - 7) / 24 * 2 * math.pi)) ** 1.5
                    mbps = pico_mbps * curva * azar.uniform(0.92, 1.08)
                    entrada += int(mbps * 1e6 / 8 * 300)
                    salida += int(mbps * 0.18 * 1e6 / 8 * 300)
                    db.add(
                        MuestraInterfaz(
                            equipo_id=e.id,
                            momento=momento,
                            if_index=if_index,
                            nombre=if_nombre,
                            operativa=True,
                            velocidad_mbps=velocidad,
                            octetos_entrada=entrada,
                            octetos_salida=salida,
                        )
                    )
                if if_index == 1:
                    db.add(
                        InterfazVigilada(
                            equipo_id=e.id, if_index=if_index, nombre=if_nombre, operativa=True
                        )
                    )
                # Un año de resumen diario para la predicción de capacidad (crece ~4 % al mes).
                for dia in range(120, 0, -1):
                    factor = (1.04 ** (-(dia / 30))) * azar.uniform(0.95, 1.05)
                    p95 = pico_mbps * 1e6 * factor
                    db.add(
                        TraficoDiario(
                            equipo_id=e.id,
                            if_index=if_index,
                            dia=(AHORA - timedelta(days=dia)).date(),
                            nombre=if_nombre,
                            velocidad_mbps=velocidad,
                            muestras=288,
                            prom_entrada=p95 * 0.55,
                            prom_salida=p95 * 0.1,
                            p95_entrada=p95,
                            p95_salida=p95 * 0.18,
                            max_entrada=p95 * 1.12,
                            max_salida=p95 * 0.22,
                        )
                    )

        # Vecinos para el mapa.
        for desde, interfaz, hasta, puerto in [
            ("CORE-CENTRO", "sfp-sfpplus1", "BORDE-INTERNET", "Te0/0/1"),
            ("CORE-CENTRO", "sfp-sfpplus2", "NODO-NORTE", "sfp-sfpplus1"),
            ("CORE-CENTRO", "sfp-sfpplus3", "NODO-SUR", "sfp-sfpplus1"),
            ("CORE-CENTRO", "sfp-sfpplus4", "SW-DISTRIBUCION", "XGigabitEthernet0/0/1"),
            ("SW-DISTRIBUCION", "XGigabitEthernet0/0/2", "OLT-CENTRO", "0/9/0"),
            ("NODO-NORTE", "ether2", "AP-SECTOR-NORTE", "eth0"),
            ("NODO-SUR", "ether3", "RT-CLIENTE-CORP", "ether1"),
            ("NODO-SUR", "ether4", "SW-ACCESO-SUR-03", "Gi0/24"),
        ]:
            remoto = equipos.get(hasta)
            db.add(
                Vecino(
                    equipo_id=equipos[desde].id,
                    interfaz=interfaz,
                    remoto_nombre=hasta,
                    remoto_puerto=puerto,
                    remoto_ip=remoto.ip_gestion if remoto else "10.10.2.33",
                    plataforma="",
                    fuente="lldp",
                    visto=hace(hours=3),
                )
            )

        # IPAM.
        prefijos = {}
        for p, desc, sitio, vlan in [
            ("10.10.0.0/16", "Gestión de equipos", "Centro", 10),
            ("100.64.0.0/22", "Clientes PPPoE · Norte", "Nodo Norte", 100),
            ("100.64.4.0/22", "Clientes PPPoE · Sur", "Nodo Sur", 200),
            ("203.0.113.0/27", "IPs públicas · clientes corporativos", "Centro", 300),
        ]:
            prefijos[p] = Prefijo(
                prefijo=p,
                descripcion=desc,
                sitio_id=sitios[sitio].id,
                vlan=vlan,
                creado=hace(days=90),
            )
            db.add(prefijos[p])
        db.flush()
        for e in equipos.values():
            db.add(
                DireccionIP(
                    prefijo_id=prefijos["10.10.0.0/16"].id,
                    ip=e.ip_gestion,
                    descripcion=f"Gestión {e.nombre}",
                    equipo_id=e.id,
                    interfaz="vlan10-gestion",
                )
            )
        ips_clientes = []
        for i, cliente in enumerate(CLIENTES):
            if i < 4:
                ip, p = f"203.0.113.{i + 2}", "203.0.113.0/27"
            elif i % 2:
                ip, p = f"100.64.{1 + i // 8}.{10 + i}", "100.64.0.0/22"
            else:
                ip, p = f"100.64.{5 + i // 8}.{10 + i}", "100.64.4.0/22"
            ips_clientes.append(ip)
            db.add(DireccionIP(prefijo_id=prefijos[p].id, ip=ip, descripcion=cliente))

        # VLANs.
        dominio = DominioL2(nombre="Anillo central", descripcion="Core, nodos y distribución")
        db.add(dominio)
        db.flush()
        for numero, nombre, desc, en in [
            (
                10,
                "GESTION",
                "Gestión de equipos",
                ["CORE-CENTRO", "NODO-NORTE", "NODO-SUR", "SW-DISTRIBUCION"],
            ),
            (100, "PPPOE-NORTE", "Clientes residenciales norte", ["CORE-CENTRO", "NODO-NORTE"]),
            (200, "PPPOE-SUR", "Clientes residenciales sur", ["CORE-CENTRO", "NODO-SUR"]),
            (
                300,
                "CORPORATIVO",
                "Enlaces dedicados",
                ["CORE-CENTRO", "SW-DISTRIBUCION", "NODO-SUR"],
            ),
            (400, "GPON-DATOS", "Servicio FTTH", ["SW-DISTRIBUCION", "OLT-CENTRO"]),
        ]:
            v = Vlan(dominio_id=dominio.id, numero=numero, nombre=nombre, descripcion=desc)
            db.add(v)
            db.flush()
            for nombre_eq in en:
                db.add(
                    VlanEnEquipo(
                        vlan_id=v.id, equipo_id=equipos[nombre_eq].id, interfaz="bridge-troncal"
                    )
                )

        # OLT con sus ONU.
        olt_eq = equipos["OLT-CENTRO"]
        db.add(
            Olt(
                equipo_id=olt_eq.id,
                perfil="huawei",
                umbral_rx_dbm=-27.0,
                ultimo_sondeo=hace(minutes=8),
                error="",
            )
        )
        onus = []
        for puerto in range(4):
            for n in range(16):
                rx = azar.uniform(-24.5, -17.0)
                estado, causa = "en_linea", ""
                if puerto == 2 and n < 9:
                    estado, causa, rx = "sin_senal", "pérdida de señal (LOS)", None
                elif (puerto, n) in {(0, 5), (3, 11)}:
                    rx = -27.9
                elif (puerto, n) == (1, 3):
                    estado, causa, rx = "sin_energia", "sin energía (dying gasp)", None
                onu = OnuGpon(
                    equipo_id=olt_eq.id,
                    pon_if_index=4194304000 + puerto * 256,
                    onu_id=n,
                    puerto=f"GPON 0/9/{puerto}",
                    nombre=CLIENTES[(puerto * 16 + n) % len(CLIENTES)]
                    if n < 6
                    else f"Cliente FTTH {puerto}-{n}",
                    serie=f"HWTC{azar.randrange(16**8):08X}",
                    estado=estado,
                    causa=causa,
                    rx_dbm=rx,
                    tx_dbm=2.1 if rx else None,
                    distancia_m=azar.randrange(400, 9000),
                    cambio=hace(minutes=40)
                    if estado == "sin_senal"
                    else hace(days=azar.randrange(1, 30)),
                    visto=hace(minutes=8),
                    aviso_senal=rx is not None and rx < -27,
                    aviso_tendencia=(puerto, n) == (1, 7),
                )
                db.add(onu)
                onus.append(onu)
        db.flush()
        degradando = next(o for o in onus if o.aviso_tendencia)
        for d in range(45, 0, -1):
            valor = -20.5 - 0.11 * (45 - d) + azar.uniform(-0.15, 0.15)
            db.add(
                PotenciaOnuDiaria(
                    onu_id=degradando.id,
                    dia=(AHORA - timedelta(days=d)).date(),
                    muestras=96,
                    suma_rx=valor * 96,
                    min_rx=valor - 0.3,
                )
            )
        degradando.rx_dbm = -25.4

        # Consumo por cliente (NetFlow), 14 días hora por hora.
        for i, ip in enumerate(ips_clientes):
            peso = 1 / (1 + i * 0.35)
            for h in range(14 * 24, 0, -1):
                momento = (AHORA - timedelta(hours=h)).replace(minute=0)
                curva = 0.25 + max(0.0, math.sin((momento.hour - 8) / 24 * 2 * math.pi))
                bajada = int(peso * curva * 3.2e9 * azar.uniform(0.7, 1.3))
                db.add(
                    ConsumoIP(
                        ip=ip,
                        hora=momento,
                        bajada=bajada,
                        subida=int(bajada * azar.uniform(0.08, 0.2)),
                    )
                )

        # Registro de eventos: caídas, cambios, accesos.
        eventos = [
            (hace(days=12, hours=3), "equipo.caido", "NODO-SUR", {"error": "sin respuesta"}),
            (hace(days=12, hours=2, minutes=20), "equipo.recuperado", "NODO-SUR", {}),
            (
                hace(days=4, hours=6),
                "interfaz.saturada",
                "CORE-CENTRO · sfp-sfpplus1 · Internet",
                {"uso": "86 % de 10000 Mbps"},
            ),
            (
                hace(days=4, hours=5),
                "interfaz.normal",
                "CORE-CENTRO · sfp-sfpplus1 · Internet",
                {"uso": "61 %"},
            ),
            (hace(days=1, hours=9), "respaldo.cambio", "CORE-CENTRO", {"líneas": "+3"}),
            (hace(days=1, hours=9), "respaldo.cambio", "BORDE-INTERNET", {"líneas": "+2"}),
            (
                hace(hours=5),
                "auditoria.critico",
                "CORE-CENTRO",
                {"hallazgo": "Resolutor DNS abierto a internet"},
            ),
            (hace(hours=3), "equipo.caido", "AP-SECTOR-NORTE", {"error": "sin respuesta"}),
            (
                hace(minutes=40),
                "olt.corte_pon",
                "OLT-CENTRO · GPON 0/9/2",
                {"onu caídas": "9 de 16", "motivo": "pérdida de señal: posible corte de fibra"},
            ),
            (
                hace(days=2),
                "onu.senal_degradando",
                "OLT-CENTRO · GPON 0/9/1 · Cliente FTTH 1-7",
                {"pierde": "3.3 dB por mes"},
            ),
        ]
        for cuando, accion, objeto, detalle in eventos:
            db.add(Evento(cuando=cuando, accion=accion, objeto=objeto, detalle=detalle))
        for i, u in enumerate(usuarios.values()):
            db.add(
                Evento(
                    cuando=hace(hours=1 + i * 7),
                    usuario_id=u.id,
                    accion="auth.login",
                    objeto=u.usuario,
                    detalle={},
                )
            )
        db.add(
            Evento(
                cuando=hace(hours=26),
                usuario_id=usuarios["ana"].id,
                accion="terminal.abrir",
                objeto="NODO-NORTE",
                detalle={"protocolo": "ssh"},
            )
        )

        # Alertas y avisos al equipo.
        db.add(
            CanalAlerta(
                nombre="NOC Telegram",
                tipo="telegram",
                destino="-1001234567890",
                secreto_cifrado=cifrador.cifrar("123:token-de-ejemplo"),
                eventos=[
                    "equipo.caido",
                    "equipo.recuperado",
                    "interfaz.saturada",
                    "olt.corte_pon",
                    "auditoria.critico",
                ],
            )
        )
        for nombre, sup in [("Ana Pérez", False), ("Carlos NOC", False), ("Jefe de red", True)]:
            c = ContactoNoc(
                nombre=nombre,
                codigo=secrets.token_hex(5),
                supervisor=sup,
                telegram_chat="100" + str(azar.randrange(10**6)),
            )
            db.add(c)
            db.flush()
            if not sup:
                db.add(
                    Guardia(
                        contacto_id=c.id,
                        dias="01234" if nombre.startswith("Ana") else "56",
                        desde="07:00",
                        hasta="19:00",
                    )
                )

        # Mantenimiento y página de estado.
        # Horas redondas en Guatemala (UTC-6): 04:00 es 10:00 UTC.
        en_dos_dias = (AHORA + timedelta(days=2)).replace(hour=10, minute=0)
        domingo = (AHORA - timedelta(days=(AHORA.weekday() + 1) % 7)).replace(hour=9, minute=0)
        mantenimiento.guardar(
            db,
            [
                mantenimiento.Ventana(
                    id="m1",
                    titulo="Actualizar RouterOS de los nodos",
                    inicio=en_dos_dias,
                    fin=en_dos_dias + timedelta(hours=2),
                    equipo_ids=[equipos["NODO-NORTE"].id, equipos["NODO-SUR"].id],
                    motivo="RouterOS 7.16.2",
                    creada_por="Diego (demo)",
                ),
                mantenimiento.Ventana(
                    id="m2",
                    titulo="Reinicio semanal de antenas",
                    inicio=domingo,
                    fin=domingo + timedelta(hours=2),
                    equipo_ids=[equipos["AP-SECTOR-NORTE"].id],
                    semanal=True,
                    creada_por="Diego (demo)",
                ),
            ],
            AHORA,
        )
        estado_publico.guardar(
            db,
            estado_publico.AjustesEstado(
                activo=True,
                titulo="Estado del servicio · Fibra Ejemplo",
                codigo="demo",
                grupos=[
                    estado_publico.Grupo(
                        "Zona Centro (fibra)", [equipos["CORE-CENTRO"].id, equipos["OLT-CENTRO"].id]
                    ),
                    estado_publico.Grupo(
                        "Zona Norte", [equipos["NODO-NORTE"].id, equipos["AP-SECTOR-NORTE"].id]
                    ),
                    estado_publico.Grupo("Zona Sur", [equipos["NODO-SUR"].id]),
                ],
            ),
        )
        db.add(
            AjusteSistema(
                clave="consumo.ajustes",
                valor='{"activo": true, "puerto": 2055, "redes": ["100.64.0.0/16", "203.0.113.0/27"]}',
            )
        )
        db.add(
            AjusteSistema(
                clave="avisos.ajustes",
                valor='{"activo": true, "canal_id": 1, "minutos_escalar": 10, "eventos": ["equipo.caido", "interfaz.caida", "olt.corte_pon"]}',
            )
        )
        db.commit()
    print(f"datos de ejemplo en {base}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
