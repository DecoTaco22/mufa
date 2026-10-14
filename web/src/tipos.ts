// Formas de las respuestas de la API (ver src/mufa/api/esquemas.py).

export type Rol = "lectura" | "agente_n1" | "tecnico_n2" | "ingeniero_n3" | "senior" | "admin";

export interface Usuario {
  id: number;
  usuario: string;
  email: string | null;
  nombre: string;
  rol: Rol;
  activo: boolean;
  totp_activo: boolean;
}

export interface Yo extends Usuario {
  dos_pasos_requerido: boolean;
}

export interface Snmp {
  version: string;
  puerto: number;
  usuario: string;
  protocolo_auth: string;
  protocolo_priv: string;
}

export interface Equipo {
  id: number;
  nombre: string;
  marca: string;
  modelo: string;
  ip_gestion: string;
  acceso: Acceso;
  puerto_ssh: number;
  numero_serie: string;
  sitio_id: number | null;
  usuario_ssh: string;
  tiene_credenciales: boolean;
  snmp: Snmp | null;
  creado: string;
  con_adaptador: boolean;
  con_respaldo: boolean;
  en_linea: boolean | null;
  alcanzable: boolean | null;
  puntaje: number | null;
  hallazgos: number;
  ultimo_respaldo: string | null;
}

export interface Marca {
  marca: string;
  nombre: string;
  con_adaptador: boolean;
  con_respaldo?: boolean;
}

export interface Sitio {
  id: number;
  nombre: string;
  descripcion: string;
}

export interface Hallazgo {
  id: number;
  check_id: string;
  severidad: "crítico" | "alto" | "medio" | "info";
  titulo: string;
  evidencia: string;
  impacto: string;
  remediacion: string[];
  referencia: string;
}

export interface HallazgoAbierto {
  equipo_id: number;
  equipo: string;
  auditoria_id: number;
  hallazgo: Hallazgo;
}

export interface Auditoria {
  id: number;
  equipo_id: number | null;
  origen: string;
  etiqueta: string;
  marca: string;
  estado: "en_curso" | "ok" | "error";
  error: string;
  inicio: string;
  fin: string | null;
  hallazgos: Hallazgo[];
}

export interface AuditoriaResumen {
  id: number;
  equipo_id: number | null;
  origen: string;
  etiqueta: string;
  marca: string;
  estado: string;
  inicio: string;
  cantidad_hallazgos: number;
}

export interface Respaldo {
  id: number;
  equipo_id: number;
  origen: string;
  creado: string;
  confirmado: string;
  tamano: number;
  hash_normalizado: string;
}

export interface EstadoEquipo {
  equipo_id: number;
  en_linea: boolean;
  alcanzable: boolean;
  ultimo_sondeo: string;
  ultimo_en_linea: string | null;
  error: string;
  sys_nombre: string;
  sys_descripcion: string;
  sys_object_id: string;
  marca_detectada: string;
  uptime_segundos: number | null;
  ubicacion: string;
  serie: string;
  modelo: string;
  version: string;
}

export interface Interfaz {
  if_index: number;
  nombre: string;
  operativa: boolean;
  velocidad_mbps: number | null;
  bps_entrada: number | null;
  bps_salida: number | null;
  vigilada_id: number | null;
  umbral_saturacion: number | null;
}

export interface EquipoCaido {
  equipo_id: number;
  nombre: string;
  ultimo_en_linea: string | null;
  error: string;
  alcanzable: boolean;
}

export interface Panel {
  equipos: number;
  max_equipos: number | null;
  plan: string;
  monitoreados: number;
  en_linea: number;
  caidos: EquipoCaido[];
  hallazgos_por_severidad: Record<string, number>;
  puntaje_red: number | null;
  hallazgos_principales: HallazgoAbierto[];
  respaldables: number;
  respaldos_al_dia: number;
  canales_de_alerta: number;
}

export interface Prefijo {
  id: number;
  prefijo: string;
  descripcion: string;
  sitio_id: number | null;
  vlan: number | null;
  reservado: boolean;
  utilizables: number;
  asignadas: number;
  porcentaje_uso: number | null;
  contenido_en: number | null;
  equipos: string[];
  equipo_id: number | null;
  equipo: string;
}

export interface Direccion {
  id: number;
  prefijo_id: number;
  ip: string;
  descripcion: string;
  equipo_id: number | null;
  interfaz: string;
  reservada: boolean;
}

export interface Dominio {
  id: number;
  nombre: string;
  descripcion: string;
}

export interface Vlan {
  id: number;
  dominio_id: number;
  numero: number;
  nombre: string;
  descripcion: string;
  reservada: boolean;
  equipos: { equipo_id: number; equipo: string; interfaz: string; nombre_en_equipo: string }[];
}

export interface Canal {
  id: number;
  nombre: string;
  tipo: "telegram" | "correo" | "webhook";
  destino: string;
  correo: { servidor: string; puerto: number; usuario: string; remitente: string } | null;
  eventos: string[];
  activo: boolean;
  tiene_secreto: boolean;
}

export interface Evento {
  id: number;
  cuando: string;
  usuario_id: number | null;
  accion: string;
  objeto: string;
  detalle: Record<string, unknown>;
}

export interface Actualizacion {
  version_actual: string;
  modo: "instalador" | "macos" | "portatil" | "tienda" | "servidor" | "codigo";
  buscar: boolean;
  revisada: string | null;
  nueva: { version: string; publicada: string | null; notas: string } | null;
  puede_instalar: boolean;
  estado: "" | "descargando" | "instalando";
  error: string;
  pasos: string;
  url_versiones: string;
}

export interface Licencia {
  plan: string;
  cliente: string;
  max_equipos: number | null;
  equipos_registrados: number;
  vence: string | null;
  aviso: string;
  funciones: string[];
}

export type Acceso = "ssh" | "api" | "api-ssl";

export interface ResultadoPruebaSnmp {
  ok: boolean;
  mensaje: string;
  sys_nombre: string;
  sys_descripcion: string;
  marca_detectada: string;
  modelo: string;
  serie: string;
  version: string;
  ubicacion: string;
  ip_origen: string;
}

export interface ResultadoImportacion {
  nuevas: number;
  actualizadas: number;
  prefijos_creados: string[];
  conflictos: string[];
  fuente: string;
}

export interface ResultadoDonde {
  equipo_id: number;
  equipo: string;
  interfaz: string;
  ip: string;
  mac: string;
  fuente: "arp" | "bridge" | "ipam";
}

export interface RespuestaDonde {
  consulta: string;
  resultados: ResultadoDonde[];
  sin_respuesta: string[];
}

export interface SalidaHerramienta {
  ok: boolean;
  texto: string;
  segundos: number;
}
