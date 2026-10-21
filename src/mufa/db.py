"""Conexión a la base de datos y tablas.

SQLite para desarrollo e instalaciones chicas; PostgreSQL en producción
(misma definición, solo cambia MUFA_BASE_DATOS).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Engine,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    false,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)


def ahora() -> datetime:
    return datetime.now(UTC)


def como_utc(momento: datetime) -> datetime:
    """SQLite devuelve fechas sin zona horaria: se guardaron en UTC."""
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nombre de usuario: el mismo con el que la persona entra a los equipos por AAA.
    usuario: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    hash_password: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(32))
    activo: Mapped[bool] = mapped_column(default=True)
    creado: Mapped[datetime] = mapped_column(default=ahora)
    # Verificación en dos pasos (TOTP). El secreto va cifrado como las
    # credenciales de los equipos; el último paso usado impide reusar un código.
    totp_secreto_cifrado: Mapped[str | None] = mapped_column(Text)
    totp_activo: Mapped[bool] = mapped_column(default=False)
    totp_ultimo_paso: Mapped[int] = mapped_column(default=0)


class Sesion(Base):
    __tablename__ = "sesiones"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Se guarda el SHA-256 del token, nunca el token: una base filtrada no
    # sirve para entrar.
    hash_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    creada: Mapped[datetime] = mapped_column(default=ahora)
    expira: Mapped[datetime]

    usuario: Mapped[Usuario] = relationship()


class CodigoRecuperacion(Base):
    """Códigos de un solo uso para entrar si se pierde el teléfono del segundo paso."""

    __tablename__ = "codigos_recuperacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 del código: son aleatorios de 50 bits, no hace falta un hash lento.
    hash_codigo: Mapped[str] = mapped_column(String(64))
    usado: Mapped[bool] = mapped_column(default=False)


class Sitio(Base):
    __tablename__ = "sitios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[str] = mapped_column(Text, default="")


class Equipo(Base):
    __tablename__ = "equipos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    marca: Mapped[str] = mapped_column(String(32))
    modelo: Mapped[str] = mapped_column(String(120), default="")
    ip_gestion: Mapped[str] = mapped_column(String(64))
    # Cómo se lee la configuración: "ssh", o en MikroTik "api" / "api-ssl"
    # (equipos que no abren SSH). puerto_ssh es el puerto de ese acceso.
    acceso: Mapped[str] = mapped_column(String(8), default="ssh", server_default="ssh")
    puerto_ssh: Mapped[int] = mapped_column(default=22)
    numero_serie: Mapped[str] = mapped_column(String(120), default="")
    sitio_id: Mapped[int | None] = mapped_column(ForeignKey("sitios.id", ondelete="SET NULL"))
    usuario_ssh: Mapped[str] = mapped_column(String(120), default="")
    password_cifrada: Mapped[str | None] = mapped_column(Text)
    creado: Mapped[datetime] = mapped_column(default=ahora)
    # SNMP para el monitoreo: sirve para cualquier marca, tenga o no
    # adaptador. snmp_version vacío = sin monitoreo. Secretos cifrados.
    snmp_version: Mapped[str] = mapped_column(String(4), default="")
    snmp_protocolo_auth: Mapped[str] = mapped_column(String(8), default="sha256")
    snmp_protocolo_priv: Mapped[str] = mapped_column(String(8), default="aes")
    snmp_puerto: Mapped[int] = mapped_column(default=161)
    snmp_comunidad_cifrada: Mapped[str | None] = mapped_column(Text)
    snmp_usuario: Mapped[str] = mapped_column(String(64), default="")
    snmp_auth_cifrada: Mapped[str | None] = mapped_column(Text)
    snmp_priv_cifrada: Mapped[str | None] = mapped_column(Text)

    sitio: Mapped[Sitio | None] = relationship()


class Respaldo(Base):
    """Una versión de la configuración de un equipo.

    Solo se guarda una versión nueva cuando la configuración cambió: si es
    igual a la anterior, se actualiza `confirmado` (la última vez que se
    vio igual), así se sabe que el respaldo está al día sin duplicarlo.
    """

    __tablename__ = "respaldos"

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    origen: Mapped[str] = mapped_column(String(16))  # "manual" o "programado"
    creado: Mapped[datetime] = mapped_column(default=ahora)
    confirmado: Mapped[datetime] = mapped_column(default=ahora)
    hash_normalizado: Mapped[str] = mapped_column(String(64))
    tamano: Mapped[int]
    # Una configuración puede traer secretos (claves PPP, comunidades SNMP):
    # se guarda cifrada como las credenciales.
    contenido_cifrado: Mapped[str] = mapped_column(Text)


class EstadoEquipo(Base):
    """Último resultado del sondeo SNMP de un equipo."""

    __tablename__ = "estado_equipos"

    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipos.id", ondelete="CASCADE"), primary_key=True
    )
    en_linea: Mapped[bool] = mapped_column(default=False)
    # Sin SNMP pero responde a ping o al puerto de acceso: encendido, mal configurado.
    alcanzable: Mapped[bool] = mapped_column(default=False, server_default=false())
    ultimo_sondeo: Mapped[datetime] = mapped_column(default=ahora)
    ultimo_en_linea: Mapped[datetime | None]
    error: Mapped[str] = mapped_column(Text, default="")
    sys_nombre: Mapped[str] = mapped_column(String(255), default="")
    sys_descripcion: Mapped[str] = mapped_column(Text, default="")
    sys_object_id: Mapped[str] = mapped_column(String(255), default="")
    marca_detectada: Mapped[str] = mapped_column(String(32), default="")
    uptime_segundos: Mapped[int | None]
    # Leído por SNMP: identidad física y software del equipo.
    ubicacion: Mapped[str] = mapped_column(String(255), default="", server_default="")
    serie: Mapped[str] = mapped_column(String(120), default="", server_default="")
    modelo: Mapped[str] = mapped_column(String(120), default="", server_default="")
    version: Mapped[str] = mapped_column(String(120), default="", server_default="")


class MuestraInterfaz(Base):
    """Contadores de una interfaz en un momento: la tasa sale de dos muestras."""

    __tablename__ = "muestras_interfaz"
    __table_args__ = (Index("ix_muestras_equipo_momento", "equipo_id", "momento"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"))
    momento: Mapped[datetime] = mapped_column(default=ahora)
    if_index: Mapped[int]
    nombre: Mapped[str] = mapped_column(String(255))
    operativa: Mapped[bool]
    velocidad_mbps: Mapped[int | None]
    octetos_entrada: Mapped[int] = mapped_column(BigInteger)
    octetos_salida: Mapped[int] = mapped_column(BigInteger)


class TraficoDiario(Base):
    """Resumen de un día de tráfico de una interfaz: el historial largo.

    Las muestras de cada sondeo se borran a los pocos días; esto queda (un
    año en Pro) y es lo que usa la predicción de capacidad. Tasas en bps.
    """

    __tablename__ = "trafico_diario"
    __table_args__ = (UniqueConstraint("equipo_id", "if_index", "dia", name="uq_trafico_diario"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"))
    if_index: Mapped[int]
    dia: Mapped[date] = mapped_column(index=True)
    nombre: Mapped[str] = mapped_column(String(255))
    velocidad_mbps: Mapped[int | None]
    muestras: Mapped[int]
    prom_entrada: Mapped[float]
    prom_salida: Mapped[float]
    p95_entrada: Mapped[float]
    p95_salida: Mapped[float]
    max_entrada: Mapped[float]
    max_salida: Mapped[float]


class Auditoria(Base):
    __tablename__ = "auditorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    origen: Mapped[str] = mapped_column(String(16))  # "ssh", "api" o "archivo"
    etiqueta: Mapped[str] = mapped_column(String(255), default="")
    marca: Mapped[str] = mapped_column(String(32))
    estado: Mapped[str] = mapped_column(String(16), default="en_curso")  # en_curso, ok, error
    error: Mapped[str] = mapped_column(Text, default="")
    inicio: Mapped[datetime] = mapped_column(default=ahora)
    fin: Mapped[datetime | None]

    hallazgos: Mapped[list[HallazgoGuardado]] = relationship(
        back_populates="auditoria", cascade="all, delete-orphan"
    )


class HallazgoGuardado(Base):
    __tablename__ = "hallazgos"

    id: Mapped[int] = mapped_column(primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(ForeignKey("auditorias.id", ondelete="CASCADE"))
    check_id: Mapped[str] = mapped_column(String(64), index=True)
    severidad: Mapped[str] = mapped_column(String(16))
    titulo: Mapped[str] = mapped_column(String(255))
    evidencia: Mapped[str] = mapped_column(Text)
    impacto: Mapped[str] = mapped_column(Text)
    remediacion: Mapped[list[str]] = mapped_column(JSON)
    referencia: Mapped[str] = mapped_column(String(255), default="")

    auditoria: Mapped[Auditoria] = relationship(back_populates="hallazgos")


class Evento(Base):
    """Registro de auditoría de la propia app: quién hizo qué y cuándo."""

    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cuando: Mapped[datetime] = mapped_column(default=ahora, index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    accion: Mapped[str] = mapped_column(String(64))
    objeto: Mapped[str] = mapped_column(String(120), default="")
    detalle: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class CanalAlerta(Base):
    """A dónde avisar: un chat de Telegram, un correo o un webhook."""

    __tablename__ = "canales_alerta"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(16))  # telegram, correo, webhook
    # chat_id de Telegram, dirección de correo o URL del webhook.
    destino: Mapped[str] = mapped_column(String(500))
    # Token del bot, contraseña SMTP o clave para firmar el webhook. Cifrado.
    secreto_cifrado: Mapped[str | None] = mapped_column(Text)
    # Servidor SMTP y remitente (solo correo).
    configuracion: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    eventos: Mapped[list[str]] = mapped_column(JSON, default=list)
    activo: Mapped[bool] = mapped_column(default=True)
    creado: Mapped[datetime] = mapped_column(default=ahora)


class Prefijo(Base):
    """Un bloque de direcciones (IPv4 o IPv6). Pueden anidarse: 10.0.0.0/16 > 10.0.4.0/22."""

    __tablename__ = "prefijos"

    id: Mapped[int] = mapped_column(primary_key=True)
    prefijo: Mapped[str] = mapped_column(String(64), unique=True)
    descripcion: Mapped[str] = mapped_column(String(255), default="")
    sitio_id: Mapped[int | None] = mapped_column(ForeignKey("sitios.id", ondelete="SET NULL"))
    vlan: Mapped[int | None]
    reservado: Mapped[bool] = mapped_column(default=False)
    creado: Mapped[datetime] = mapped_column(default=ahora)


class DireccionIP(Base):
    __tablename__ = "direcciones_ip"

    id: Mapped[int] = mapped_column(primary_key=True)
    prefijo_id: Mapped[int] = mapped_column(
        ForeignKey("prefijos.id", ondelete="CASCADE"), index=True
    )
    ip: Mapped[str] = mapped_column(String(64), unique=True)
    descripcion: Mapped[str] = mapped_column(String(255), default="")
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id", ondelete="SET NULL"))
    # Interfaz del equipo donde está configurada (al importar del equipo).
    interfaz: Mapped[str] = mapped_column(String(255), default="", server_default="")
    reservada: Mapped[bool] = mapped_column(default=False)
    creado: Mapped[datetime] = mapped_column(default=ahora)


class DominioL2(Base):
    """Un dominio de capa 2: donde un número de VLAN tiene que ser único."""

    __tablename__ = "dominios_l2"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[str] = mapped_column(String(255), default="")


class Vlan(Base):
    __tablename__ = "vlans"
    __table_args__ = (UniqueConstraint("dominio_id", "numero", name="uq_vlan_dominio_numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dominio_id: Mapped[int] = mapped_column(ForeignKey("dominios_l2.id", ondelete="CASCADE"))
    numero: Mapped[int]
    nombre: Mapped[str] = mapped_column(String(64))
    descripcion: Mapped[str] = mapped_column(String(255), default="")
    reservada: Mapped[bool] = mapped_column(default=False)
    creado: Mapped[datetime] = mapped_column(default=ahora)


class VlanEnEquipo(Base):
    """En qué equipo (y sobre qué interfaz) está configurada una VLAN documentada."""

    __tablename__ = "vlans_en_equipo"
    __table_args__ = (
        UniqueConstraint("vlan_id", "equipo_id", "interfaz", name="uq_vlan_equipo_interfaz"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vlan_id: Mapped[int] = mapped_column(ForeignKey("vlans.id", ondelete="CASCADE"), index=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"))
    interfaz: Mapped[str] = mapped_column(String(255), default="")
    # Nombre con que la tiene el equipo, si difiere del documentado.
    nombre_en_equipo: Mapped[str] = mapped_column(String(255), default="")
    visto: Mapped[datetime] = mapped_column(default=ahora)


class InterfazVigilada(Base):
    """Interfaz de la que se avisa si se cae o se satura."""

    __tablename__ = "interfaces_vigiladas"
    __table_args__ = (UniqueConstraint("equipo_id", "if_index", name="uq_vigilada_equipo_if"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"))
    if_index: Mapped[int]
    nombre: Mapped[str] = mapped_column(String(255))
    # % de la velocidad de la interfaz a partir del cual se considera saturada.
    umbral_saturacion: Mapped[int] = mapped_column(default=80)
    # Minutos seguidos por encima del umbral antes de avisar.
    minutos_saturacion: Mapped[int] = mapped_column(default=15)
    # Estado conocido, para avisar solo en los cambios.
    operativa: Mapped[bool | None]
    saturada_desde: Mapped[datetime | None]
    aviso_saturacion: Mapped[bool] = mapped_column(default=False)
    creado: Mapped[datetime] = mapped_column(default=ahora)


class Vecino(Base):
    """Un equipo conectado a una interfaz, visto por LLDP, CDP o MikroTik (para el mapa)."""

    __tablename__ = "vecinos"

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"), index=True)
    interfaz: Mapped[str] = mapped_column(String(255), default="")
    remoto_nombre: Mapped[str] = mapped_column(String(255), default="")
    remoto_puerto: Mapped[str] = mapped_column(String(255), default="")
    remoto_ip: Mapped[str] = mapped_column(String(64), default="")
    plataforma: Mapped[str] = mapped_column(String(255), default="")
    fuente: Mapped[str] = mapped_column(String(16))  # lldp, cdp o mikrotik
    visto: Mapped[datetime] = mapped_column(default=ahora)


class Olt(Base):
    """Un equipo que se sondea también como OLT GPON (mufa Pro)."""

    __tablename__ = "olts"

    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipos.id", ondelete="CASCADE"), primary_key=True
    )
    # Qué MIB usa: "huawei" (MA5600T/MA5800) o "zte" (C300/C320).
    perfil: Mapped[str] = mapped_column(String(16))
    # Potencia de recepción de la ONU a partir de la cual se avisa (dBm).
    umbral_rx_dbm: Mapped[float] = mapped_column(default=-27.0)
    ultimo_sondeo: Mapped[datetime | None]
    error: Mapped[str] = mapped_column(Text, default="")
    creado: Mapped[datetime] = mapped_column(default=ahora)


class OnuGpon(Base):
    """El último estado conocido de una ONU, leído de su OLT."""

    __tablename__ = "onus_gpon"
    __table_args__ = (UniqueConstraint("equipo_id", "pon_if_index", "onu_id", name="uq_onu_gpon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"))
    pon_if_index: Mapped[int] = mapped_column(BigInteger)
    onu_id: Mapped[int]
    puerto: Mapped[str] = mapped_column(String(64), default="")
    nombre: Mapped[str] = mapped_column(String(255), default="")
    serie: Mapped[str] = mapped_column(String(64), default="")
    # en_linea, sin_senal (LOS), sin_energia (dying gasp), desconectada, otro
    estado: Mapped[str] = mapped_column(String(16), default="otro")
    causa: Mapped[str] = mapped_column(String(64), default="")
    rx_dbm: Mapped[float | None]
    tx_dbm: Mapped[float | None]
    distancia_m: Mapped[int | None]
    # Cuándo cambió de estado por última vez (para «caída hace 2 h»).
    cambio: Mapped[datetime] = mapped_column(default=ahora)
    visto: Mapped[datetime] = mapped_column(default=ahora)
    # Ya se avisó la señal baja (se vuelve a avisar al recuperarse 1 dB).
    aviso_senal: Mapped[bool] = mapped_column(default=False)


class ContactoNoc(Base):
    """Alguien del equipo (o un grupo) que recibe los avisos de Pro por Telegram."""

    __tablename__ = "contactos_noc"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    # El chat de Telegram, cuando la persona abrió el enlace del bot.
    telegram_chat: Mapped[str | None] = mapped_column(String(64))
    # Código del enlace para unirse (t.me/<bot>?start=<código>).
    codigo: Mapped[str] = mapped_column(String(32), unique=True)
    # Los supervisores reciben lo que nadie tomó a tiempo.
    supervisor: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)
    creado: Mapped[datetime] = mapped_column(default=ahora)


class Guardia(Base):
    """Un turno semanal: quién atiende los avisos esos días a esas horas."""

    __tablename__ = "guardias"

    id: Mapped[int] = mapped_column(primary_key=True)
    contacto_id: Mapped[int] = mapped_column(ForeignKey("contactos_noc.id", ondelete="CASCADE"))
    # Días de la semana: "0" lunes ... "6" domingo, por ejemplo "01234".
    dias: Mapped[str] = mapped_column(String(7))
    # Hora local del servidor, "HH:MM". Si hasta <= desde, el turno cruza la medianoche.
    desde: Mapped[str] = mapped_column(String(5))
    hasta: Mapped[str] = mapped_column(String(5))

    contacto: Mapped[ContactoNoc] = relationship()


class Incidente(Base):
    """Un aviso al equipo: quién lo recibió, quién lo tomó y cuándo se resolvió."""

    __tablename__ = "incidentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int | None] = mapped_column(ForeignKey("eventos.id", ondelete="SET NULL"))
    tipo: Mapped[str] = mapped_column(String(64))
    objeto: Mapped[str] = mapped_column(String(255))
    titulo: Mapped[str] = mapped_column(String(255))
    detalle: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # abierto, tomado, resuelto
    estado: Mapped[str] = mapped_column(String(16), default="abierto", index=True)
    # 0 = avisado a la guardia; 1 = escalado a los supervisores.
    nivel: Mapped[int] = mapped_column(default=0)
    tomado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("contactos_noc.id", ondelete="SET NULL")
    )
    tomado: Mapped[datetime | None]
    creado: Mapped[datetime] = mapped_column(default=ahora)
    resuelto: Mapped[datetime | None]
    # Mensajes enviados: [[chat, id del mensaje], ...] para editarlos al tomarlo o resolverlo.
    mensajes: Mapped[list[list[str]]] = mapped_column(JSON, default=list)

    tomado_por: Mapped[ContactoNoc | None] = relationship()


class AjusteSistema(Base):
    """Valores internos que el servidor necesita recordar entre reinicios."""

    __tablename__ = "ajustes_sistema"

    clave: Mapped[str] = mapped_column(String(64), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)


def crear_motor(url: str) -> Engine:
    if url.startswith("sqlite"):
        motor = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(motor, "connect")
        def _activar_claves_foraneas(conexion: Any, _registro: Any) -> None:
            cursor = conexion.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return motor
    return create_engine(url, pool_pre_ping=True)


def fabrica_de_sesiones(motor: Engine) -> sessionmaker[Session]:
    return sessionmaker(motor, expire_on_commit=False)
