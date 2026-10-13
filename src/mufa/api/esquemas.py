"""Formatos de entrada y salida de la API.

Las credenciales de los equipos solo entran: ninguna respuesta las
devuelve, ni cifradas.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from mufa.permisos import Rol


class _Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Minúsculas, empieza con letra: tiene que servir también como usuario SSH
# en los equipos (AAA).
Acceso = Literal["ssh", "api", "api-ssl"]

PATRON_USUARIO = r"^[a-z][a-z0-9._-]{2,31}$"
# Seis dígitos de la app, o un código de recuperación "xxxxx-xxxxx".
PATRON_CODIGO = r"^(\d{6}|[a-zA-Z0-9]{5}-[a-zA-Z0-9]{5})$"
PATRON_TOTP = r"^\d{6}$"


class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=254, description="Nombre de usuario o email")
    password: str = Field(min_length=1, max_length=256)
    codigo: str | None = Field(default=None, pattern=PATRON_CODIGO)


class UsuarioSalida(_Salida):
    id: int
    usuario: str
    email: str | None
    nombre: str
    rol: Rol
    activo: bool
    totp_activo: bool


class Yo(UsuarioSalida):
    dos_pasos_requerido: bool


class DosPasosInicio(BaseModel):
    secreto: str
    uri: str


class CodigoDosPasos(BaseModel):
    codigo: str = Field(pattern=PATRON_TOTP)


class CodigosRecuperacion(BaseModel):
    """Se muestran una sola vez: hay que guardarlos en un lugar seguro."""

    codigos_recuperacion: list[str]


class DesactivarDosPasos(BaseModel):
    password: str = Field(max_length=256)
    codigo: str = Field(pattern=PATRON_TOTP)


class LoginSalida(BaseModel):
    # None cuando la sesión va en cookie (app web).
    token: str | None
    expira: datetime
    usuario: UsuarioSalida


class CambioPassword(BaseModel):
    actual: str = Field(max_length=256)
    nueva: str = Field(max_length=256)


class UsuarioCrear(BaseModel):
    usuario: str = Field(pattern=PATRON_USUARIO)
    email: EmailStr | None = None
    nombre: str = Field(min_length=1, max_length=120)
    rol: Rol
    password: str = Field(max_length=256)


class UsuarioActualizar(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    rol: Rol | None = None
    activo: bool | None = None


class NuevaPassword(BaseModel):
    password: str = Field(max_length=256)


class SitioCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str = Field(default="", max_length=2000)


class SitioSalida(_Salida):
    id: int
    nombre: str
    descripcion: str


def _validar_ip(valor: str) -> str:
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        raise ValueError("ip_gestion debe ser una dirección IPv4 o IPv6") from None


class EstadoInicial(BaseModel):
    necesita_admin: bool
    # La app de escritorio (SQLite) puede traer los datos de otra computadora.
    puede_importar: bool = False


class ExportarDatos(BaseModel):
    password: str = Field(max_length=256)
    frase: str = Field(min_length=12, max_length=256)


class ArchivoExportado(BaseModel):
    nombre: str
    contenido: str


class PrimerAdmin(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    usuario: str = Field(pattern=PATRON_USUARIO)
    nombre: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    password: str = Field(max_length=256)


class SnmpConfig(BaseModel):
    """SNMPv3 (authPriv) es lo recomendado; v2c solo para equipos que no soportan v3.

    Al editar, una clave vacía conserva la guardada (las claves nunca vuelven del servidor).
    """

    version: Literal["3", "2c"] = "3"
    puerto: int = Field(default=161, ge=1, le=65535)
    usuario: str = Field(default="", max_length=64)
    clave_auth: str | None = Field(default=None, max_length=256)
    clave_priv: str | None = Field(default=None, max_length=256)
    protocolo_auth: Literal["sha256", "sha"] = "sha256"
    protocolo_priv: Literal["aes", "aes256"] = "aes"
    comunidad: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _completa(self) -> Self:
        if self.version == "3":
            if not self.usuario:
                raise ValueError("SNMPv3 necesita usuario")
            # RFC 3414: las claves de SNMPv3 tienen al menos 8 caracteres.
            for clave in (self.clave_auth, self.clave_priv):
                if clave and len(clave) < 8:
                    raise ValueError("las claves de SNMPv3 tienen al menos 8 caracteres")
        return self


class PruebaSnmp(BaseModel):
    ip_gestion: str
    snmp: SnmpConfig
    # Al editar: de dónde tomar las claves que no se escribieron.
    equipo_id: int | None = None

    @field_validator("ip_gestion")
    @classmethod
    def _ip(cls, valor: str) -> str:
        return _validar_ip(valor)


class ResultadoPruebaSnmp(BaseModel):
    ok: bool
    mensaje: str
    sys_nombre: str = ""
    sys_descripcion: str = ""
    marca_detectada: str = ""
    # Para completar el formulario: lo que el equipo informa de sí mismo.
    modelo: str = ""
    serie: str = ""
    version: str = ""
    ubicacion: str = ""
    # La IP con la que mufa sale hacia el equipo: la que hay que permitir en él.
    ip_origen: str = ""


class SnmpSalida(BaseModel):
    version: str
    puerto: int
    usuario: str
    protocolo_auth: str
    protocolo_priv: str


class EquipoCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    marca: str = Field(min_length=1, max_length=32)
    modelo: str = Field(default="", max_length=120)
    ip_gestion: str
    acceso: Acceso = "ssh"
    puerto_ssh: int = Field(default=22, ge=1, le=65535)
    numero_serie: str = Field(default="", max_length=120)
    sitio_id: int | None = None
    usuario_ssh: str = Field(default="", max_length=120)
    password_ssh: str | None = Field(default=None, max_length=256)
    snmp: SnmpConfig | None = None

    @field_validator("ip_gestion")
    @classmethod
    def _ip(cls, valor: str) -> str:
        return _validar_ip(valor)


class EquipoActualizar(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    modelo: str | None = Field(default=None, max_length=120)
    ip_gestion: str | None = None
    acceso: Acceso | None = None
    puerto_ssh: int | None = Field(default=None, ge=1, le=65535)
    numero_serie: str | None = Field(default=None, max_length=120)
    sitio_id: int | None = None
    usuario_ssh: str | None = Field(default=None, max_length=120)
    password_ssh: str | None = Field(default=None, max_length=256)
    # Reemplaza la configuración SNMP entera; null la desactiva.
    snmp: SnmpConfig | None = None

    @field_validator("ip_gestion")
    @classmethod
    def _ip(cls, valor: str | None) -> str | None:
        return None if valor is None else _validar_ip(valor)


class EquipoSalida(_Salida):
    id: int
    nombre: str
    marca: str
    modelo: str
    ip_gestion: str
    acceso: str
    puerto_ssh: int
    numero_serie: str
    sitio_id: int | None
    usuario_ssh: str
    tiene_credenciales: bool
    snmp: SnmpSalida | None
    creado: datetime
    con_adaptador: bool = False
    con_respaldo: bool = False
    # Del monitoreo y las auditorías: None si todavía no hay datos.
    en_linea: bool | None = None
    alcanzable: bool | None = None
    # Seguridad de 0 a 100 según los hallazgos abiertos; None si nunca se auditó.
    puntaje: int | None = None
    hallazgos: int = 0
    ultimo_respaldo: datetime | None = None


class RespaldoSalida(_Salida):
    id: int
    equipo_id: int
    origen: str
    creado: datetime
    confirmado: datetime
    tamano: int
    hash_normalizado: str


class ResultadoRespaldo(BaseModel):
    respaldo: RespaldoSalida
    cambio: bool


class RespaldoConContenido(RespaldoSalida):
    contenido: str


class Diferencias(BaseModel):
    desde: int
    hasta: int
    diferencias: str


class ProgramaRespaldos(BaseModel):
    activo: bool = True
    hora: str = Field(default="12:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class DestinoEntrada(BaseModel):
    activo: bool = False
    protocolo: Literal["sftp", "ftps", "ftp"] = "sftp"
    host: str = Field(default="", max_length=253)
    puerto: int = Field(default=22, ge=1, le=65535)
    usuario: str = Field(default="", max_length=128)
    # None: se mantiene la guardada. "": se borra.
    password: str | None = Field(default=None, max_length=256)
    carpeta: str = Field(default="/mufa", max_length=200)
    organizar: Literal["por_equipo", "por_dia"] = "por_equipo"
    verificar_certificado: bool = True

    @field_validator("host")
    @classmethod
    def _host(cls, valor: str) -> str:
        valor = valor.strip()
        if valor and not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", valor):
            raise ValueError("escribe solo la IP o el nombre del servidor, sin ftp:// ni carpetas")
        return valor.strip("[]")

    @field_validator("usuario")
    @classmethod
    def _usuario(cls, valor: str) -> str:
        if any(ord(c) < 32 for c in valor):
            raise ValueError("el usuario tiene caracteres no válidos")
        return valor.strip()


class DestinoSalida(BaseModel):
    activo: bool
    protocolo: str
    host: str
    puerto: int
    usuario: str
    tiene_password: bool
    carpeta: str
    organizar: str
    verificar_certificado: bool


class UltimoEnvioSalida(BaseModel):
    cuando: datetime
    ok: bool
    archivos: int
    mensaje: str


class PruebaDestino(BaseModel):
    ok: bool
    mensaje: str
    huella: str = ""


class ResultadoEnvioSalida(BaseModel):
    archivos: int
    rutas: list[str]


class EquipoEnRespaldos(BaseModel):
    id: int
    nombre: str
    marca: str
    # ok, error, sin_acceso (falta usuario), sin_soporte (marca), pendiente (nunca se respaldó)
    estado: str
    ultimo: datetime | None
    versiones: int
    error: str = ""


class ResumenRespaldos(BaseModel):
    programa: ProgramaRespaldos
    proximo: datetime | None
    hora_servidor: datetime
    zona: str
    respaldando: bool
    destino: DestinoSalida
    ultimo_envio: UltimoEnvioSalida | None
    equipos: list[EquipoEnRespaldos]


class EstadoSalida(_Salida):
    equipo_id: int
    en_linea: bool
    alcanzable: bool
    ubicacion: str
    serie: str
    modelo: str
    version: str
    ultimo_sondeo: datetime
    ultimo_en_linea: datetime | None
    error: str
    sys_nombre: str
    sys_descripcion: str
    sys_object_id: str
    marca_detectada: str
    uptime_segundos: int | None


class InterfazSalida(_Salida):
    if_index: int
    nombre: str
    operativa: bool
    velocidad_mbps: int | None
    bps_entrada: float | None
    bps_salida: float | None
    # Si se avisa de esta interfaz (id de la vigilancia) y su umbral.
    vigilada_id: int | None = None
    umbral_saturacion: int | None = None


class VigilarInterfaz(BaseModel):
    if_index: int = Field(ge=0)
    umbral_saturacion: int = Field(default=80, ge=10, le=100)
    minutos_saturacion: int = Field(default=15, ge=5, le=1440)


class VigilanciaActualizar(BaseModel):
    umbral_saturacion: int | None = Field(default=None, ge=10, le=100)
    minutos_saturacion: int | None = Field(default=None, ge=5, le=1440)


class VigilanciaSalida(_Salida):
    id: int
    equipo_id: int
    if_index: int
    nombre: str
    umbral_saturacion: int
    minutos_saturacion: int
    operativa: bool | None
    aviso_saturacion: bool


class ImportarVlans(BaseModel):
    dominio_id: int


class ResultadoImportacionSalida(BaseModel):
    nuevas: int
    actualizadas: int
    prefijos_creados: list[str]
    conflictos: list[str]
    fuente: str


class ResultadoDonde(BaseModel):
    equipo_id: int
    equipo: str
    interfaz: str
    ip: str
    mac: str
    # "arp", "bridge" (MAC aprendida en un puerto) o "ipam" (documentada).
    fuente: str


class RespuestaDonde(BaseModel):
    consulta: str
    resultados: list[ResultadoDonde]
    # Equipos que no se pudieron consultar, con el motivo.
    sin_respuesta: list[str]


class Recorrido(BaseModel):
    oid: str = Field(pattern=r"^\.?\d+(\.\d+)*$", max_length=200)


class FilaSnmp(BaseModel):
    oid: str
    valor: str


class Herramienta(BaseModel):
    destino: str = Field(min_length=1, max_length=253)
    puerto: int | None = Field(default=None, ge=1, le=65535)


class HerramientaEnVivo(BaseModel):
    destino: str = Field(min_length=1, max_length=253)
    # Ping: cuántos paquetes; None = continuo (se corta con Detener o a los 10 minutos).
    cantidad: int | None = Field(default=4, ge=1, le=1000)


class SalidaHerramienta(BaseModel):
    ok: bool
    texto: str
    segundos: float


class EquipoCaido(BaseModel):
    equipo_id: int
    nombre: str
    ultimo_en_linea: datetime | None
    error: str
    # Encendido (responde a ping o TCP) pero sin SNMP.
    alcanzable: bool = False


class ResumenMonitoreo(BaseModel):
    equipos: int
    monitoreados: int
    en_linea: int
    caidos: list[EquipoCaido]


class HallazgoSalida(_Salida):
    id: int
    check_id: str
    severidad: str
    titulo: str
    evidencia: str
    impacto: str
    remediacion: list[str]
    referencia: str


class AuditoriaSalida(_Salida):
    id: int
    equipo_id: int | None
    origen: str
    etiqueta: str
    marca: str
    estado: str
    error: str
    inicio: datetime
    fin: datetime | None
    hallazgos: list[HallazgoSalida]


class AuditoriaResumen(_Salida):
    id: int
    equipo_id: int | None
    origen: str
    etiqueta: str
    marca: str
    estado: str
    inicio: datetime
    cantidad_hallazgos: int


class HallazgoAbierto(BaseModel):
    equipo_id: int
    equipo: str
    auditoria_id: int
    hallazgo: HallazgoSalida


class EventoSalida(_Salida):
    id: int
    cuando: datetime
    usuario_id: int | None
    accion: str
    objeto: str
    detalle: dict[str, Any]


class MarcaSalida(BaseModel):
    marca: str
    nombre: str
    # Con adaptador: además del monitoreo SNMP, auditoría y respaldos por SSH.
    con_adaptador: bool
    con_respaldo: bool = False


class LicenciaSalida(BaseModel):
    plan: str
    cliente: str
    max_equipos: int | None  # None = ilimitados
    equipos_registrados: int
    vence: date | None
    aviso: str
    funciones: list[str]


class LicenciaInstalar(BaseModel):
    licencia: str = Field(min_length=10, max_length=4096)


TipoEvento = Literal[
    "equipo.caido", "equipo.recuperado", "auditoria.critico", "respaldo.cambio", "respaldo.error"
]


class ConfigCorreo(BaseModel):
    servidor: str = Field(min_length=1, max_length=255)
    puerto: int = Field(default=587, ge=1, le=65535)
    usuario: str = Field(default="", max_length=255)
    remitente: str = Field(default="", max_length=255)


class CanalCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    tipo: Literal["telegram", "correo", "webhook"]
    # chat_id de Telegram, dirección de correo o URL del webhook.
    destino: str = Field(min_length=1, max_length=500)
    # Token del bot, contraseña SMTP o clave para firmar el webhook. Nunca se devuelve.
    secreto: str | None = Field(default=None, max_length=500)
    correo: ConfigCorreo | None = None
    eventos: list[TipoEvento] = Field(min_length=1)
    activo: bool = True

    @model_validator(mode="after")
    def _completo(self) -> Self:
        if self.tipo == "telegram" and not self.secreto:
            raise ValueError("Telegram necesita el token del bot en 'secreto'")
        if self.tipo == "correo" and self.correo is None:
            raise ValueError("el correo necesita la configuración del servidor SMTP")
        if self.tipo == "webhook" and not self.destino.startswith(("https://", "http://")):
            raise ValueError("el webhook necesita una URL http(s)")
        return self


class CanalSalida(BaseModel):
    id: int
    nombre: str
    tipo: str
    destino: str
    correo: ConfigCorreo | None
    eventos: list[str]
    activo: bool
    tiene_secreto: bool


class PrefijoCrear(BaseModel):
    prefijo: str = Field(min_length=3, max_length=64, examples=["10.20.4.0/22"])
    descripcion: str = Field(default="", max_length=255)
    sitio_id: int | None = None
    vlan: int | None = Field(default=None, ge=1, le=4094)
    reservado: bool = False


class PrefijoActualizar(BaseModel):
    # Cambiar la red o la máscara: las IPs documentadas tienen que seguir cabiendo.
    prefijo: str | None = Field(default=None, min_length=3, max_length=64)
    descripcion: str | None = Field(default=None, max_length=255)
    sitio_id: int | None = None
    vlan: int | None = Field(default=None, ge=1, le=4094)
    reservado: bool | None = None


class PrefijoSalida(BaseModel):
    id: int
    prefijo: str
    descripcion: str
    sitio_id: int | None
    vlan: int | None
    reservado: bool
    utilizables: int
    asignadas: int
    porcentaje_uso: float | None
    contenido_en: int | None
    # Dónde está la red: los equipos (con su interfaz) que tienen IPs en ella.
    equipos: list[str] = []
    # El equipo principal de la red (el primero con IPs en ella), para agrupar en la app.
    equipo_id: int | None = None
    equipo: str = ""


class DireccionCrear(BaseModel):
    # Sin ip, se asigna la siguiente libre del prefijo.
    ip: str | None = Field(default=None, max_length=64)
    descripcion: str = Field(default="", max_length=255)
    equipo_id: int | None = None
    reservada: bool = False


class DireccionSalida(_Salida):
    id: int
    prefijo_id: int
    ip: str
    descripcion: str
    equipo_id: int | None
    interfaz: str = ""
    reservada: bool


class DominioCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str = Field(default="", max_length=255)


class DominioSalida(_Salida):
    id: int
    nombre: str
    descripcion: str


class VlanEnEquipoEntrada(BaseModel):
    equipo_id: int
    interfaz: str = Field(default="", max_length=255)


class VlanCrear(BaseModel):
    # Sin número, se usa la siguiente libre del dominio a partir de 'desde'.
    numero: int | None = Field(default=None, ge=1, le=4094)
    desde: int = Field(default=2, ge=1, le=4094)
    nombre: str = Field(min_length=1, max_length=64)
    descripcion: str = Field(default="", max_length=255)
    reservada: bool = False
    equipos: list[VlanEnEquipoEntrada] = Field(default=[], max_length=200)


class VlanActualizar(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=64)
    descripcion: str | None = Field(default=None, max_length=255)
    reservada: bool | None = None


class VlanEnEquipoSalida(BaseModel):
    equipo_id: int
    equipo: str
    interfaz: str
    nombre_en_equipo: str


class VlanSalida(_Salida):
    id: int
    dominio_id: int
    numero: int
    nombre: str
    descripcion: str
    reservada: bool
    equipos: list[VlanEnEquipoSalida] = []


class PresupuestoEntrada(BaseModel):
    potencia_tx_dbm: float = Field(ge=-40, le=30)
    sensibilidad_rx_dbm: float = Field(ge=-60, le=10)
    distancia_km: float = Field(ge=0, le=20000)
    longitud_onda_nm: Literal[1310, 1550] = 1550
    # Si se omite, se usa la típica de la longitud de onda.
    atenuacion_db_km: float | None = Field(default=None, gt=0, le=5)
    conectores: int = Field(default=2, ge=0, le=500)
    tipo_conectores: Literal["mismo", "mixto"] = "mismo"
    empalmes: int = Field(default=0, ge=0, le=10000)
    perdida_empalme_db: float = Field(default=0.1, ge=0, le=5)
    relacion_extincion_db: Literal[10, 3] = 10
    receptor: Literal["pin", "apd"] = "pin"
    margen_seguridad_db: float = Field(default=3.0, ge=0, le=30)


class DispersionEntrada(BaseModel):
    coeficiente_ps_nm_km: float = Field(default=17.0, ge=-200, le=200)
    ancho_espectral_nm: float = Field(gt=0, le=100)
    distancia_km: float = Field(gt=0, le=20000)
    tasa_gbps: float = Field(gt=0, le=1600)


class AperturaEntrada(BaseModel):
    n_nucleo: float = Field(gt=1, lt=3)
    n_revestimiento: float = Field(gt=1, lt=3)
