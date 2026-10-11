import { useMemo, useState } from "react";
import { Icono, type NombreIcono } from "../componentes/Icono";
import { Cargando, Encabezado, MensajeError, Tarjeta, Vacio } from "../componentes/ui";
import type { Evento, Rol, Usuario } from "../tipos";
import { NOMBRES_DE_ROL, useDatos } from "../util";

type Tono = "neutro" | "ok" | "atencion" | "peligro";

// Cada acción del registro en palabras, con su ícono. Lo que no esté acá se muestra tal cual.
const ACCIONES: Record<string, [string, NombreIcono, Tono]> = {
  "auth.login": ["Inició sesión", "usuarios", "neutro"],
  "auth.logout": ["Cerró sesión", "usuarios", "neutro"],
  "auth.login_fallido": ["Intento de inicio de sesión fallido", "alerta", "peligro"],
  "auth.codigo_fallido": ["Código de dos pasos incorrecto", "alerta", "peligro"],
  "auth.codigo_recuperacion_usado": ["Usó un código de recuperación", "llave", "atencion"],
  "auth.cambio_password": ["Cambió su contraseña", "candado", "neutro"],
  "auth.2fa_iniciar": ["Empezó a activar los dos pasos", "candado", "neutro"],
  "auth.2fa_activar": ["Activó la verificación en dos pasos", "escudo", "ok"],
  "auth.2fa_desactivar": ["Desactivó la verificación en dos pasos", "escudo", "atencion"],
  "auth.2fa_nuevos_codigos": ["Generó códigos de recuperación nuevos", "llave", "neutro"],
  "usuario.crear": ["Creó un usuario", "usuarios", "ok"],
  "usuario.actualizar": ["Modificó un usuario", "usuarios", "neutro"],
  "usuario.crear_admin_inicial": ["Creó el primer administrador", "usuarios", "ok"],
  "usuario.crear_admin_cli": ["Creó un administrador desde la terminal", "usuarios", "ok"],
  "usuario.restablecer_password": ["Restableció la contraseña de un usuario", "candado", "atencion"],
  "usuario.restablecer_2fa": ["Restableció los dos pasos de un usuario", "escudo", "atencion"],
  "equipo.crear": ["Agregó un equipo", "equipo", "ok"],
  "equipo.actualizar": ["Modificó un equipo", "equipo", "neutro"],
  "equipo.borrar": ["Borró un equipo", "papelera", "atencion"],
  "equipo.caido": ["Equipo caído", "alerta", "peligro"],
  "equipo.recuperado": ["Equipo recuperado", "equipo", "ok"],
  "interfaz.vigilar": ["Empezó a vigilar una interfaz", "grafica", "neutro"],
  "interfaz.dejar_de_vigilar": ["Dejó de vigilar una interfaz", "grafica", "neutro"],
  "interfaz.normal": ["Interfaz normal otra vez", "grafica", "ok"],
  "auditoria.archivo": ["Auditó un archivo", "hallazgos", "neutro"],
  "auditoria.critico": ["Hallazgo crítico", "hallazgos", "peligro"],
  "respaldo.nuevo": ["Respaldo nuevo", "descarga", "ok"],
  "respaldo.sin_cambios": ["Respaldo sin cambios", "descarga", "neutro"],
  "respaldo.error": ["Falló un respaldo", "alerta", "peligro"],
  "respaldo.ver": ["Vio un respaldo", "documento", "neutro"],
  "respaldo.cambio": ["La configuración cambió", "documento", "atencion"],
  "respaldo.todos": ["Respaldó todos los equipos", "descarga", "neutro"],
  "respaldo.programa": ["Cambió el horario de respaldos", "calendario", "neutro"],
  "respaldo.destino": ["Configuró el servidor de copias", "intercambio", "atencion"],
  "respaldo.copia": ["Copió los respaldos al servidor", "intercambio", "ok"],
  "respaldo.copia_error": ["Falló la copia al servidor", "alerta", "peligro"],
  "alerta.crear_canal": ["Agregó un canal de alertas", "campana", "ok"],
  "alerta.editar_canal": ["Modificó un canal de alertas", "campana", "neutro"],
  "alerta.borrar_canal": ["Borró un canal de alertas", "campana", "atencion"],
  "ipam.crear_prefijo": ["Creó una red", "red", "ok"],
  "ipam.actualizar_prefijo": ["Modificó una red", "red", "neutro"],
  "ipam.borrar_prefijo": ["Borró una red", "papelera", "atencion"],
  "ipam.asignar_ip": ["Asignó una IP", "red", "neutro"],
  "ipam.liberar_ip": ["Liberó una IP", "red", "neutro"],
  "ipam.importar": ["Importó IPs de un equipo", "descarga", "ok"],
  "vlan.crear_dominio": ["Creó un dominio de VLANs", "capas", "ok"],
  "vlan.borrar_dominio": ["Borró un dominio de VLANs", "papelera", "atencion"],
  "vlan.crear": ["Creó una VLAN", "capas", "ok"],
  "vlan.actualizar": ["Modificó una VLAN", "capas", "neutro"],
  "vlan.borrar": ["Borró una VLAN", "papelera", "atencion"],
  "vlan.agregar_equipo": ["Asignó una VLAN a un equipo", "capas", "neutro"],
  "vlan.quitar_equipo": ["Quitó una VLAN de un equipo", "capas", "neutro"],
  "vlan.importar": ["Importó VLANs de un equipo", "descarga", "ok"],
  "sitio.crear": ["Creó un sitio", "ubicacion", "ok"],
  "licencia.instalar": ["Instaló una licencia", "estrella", "ok"],
  "terminal.abrir": ["Abrió una terminal", "terminal", "neutro"],
  "terminal.cerrar": ["Cerró una terminal", "terminal", "neutro"],
  "terminal.fallo": ["No pudo abrir una terminal", "terminal", "atencion"],
  "terminal.clave_reemplazada": ["Aceptó la clave nueva de un equipo", "llave", "peligro"],
};

const ETIQUETAS: Record<string, string> = {
  ip: "IP", rol: "Rol", modo: "Modo", motivo: "Motivo", nombre: "Nombre", prefijo: "Red",
  nuevas: "Nuevas", conflictos: "Para revisar", dominio: "Dominio", puerto: "Puerto",
  huellas: "Huellas", equipo: "Equipo", segundos: "Duró",
  archivos: "Archivos", carpeta: "Carpeta", activo: "Activo", error: "Error",
};

function valor(clave: string, v: unknown): string {
  if (clave === "rol" && typeof v === "string") return NOMBRES_DE_ROL[v as Rol] ?? v;
  if (clave === "segundos" && typeof v === "number") {
    return v < 60 ? `${v} s` : v < 3600 ? `${Math.round(v / 60)} min` : `${(v / 3600).toFixed(1)} h`;
  }
  return typeof v === "string" ? v : JSON.stringify(v);
}

function dia(iso: string): string {
  const d = new Date(iso);
  const hoy = new Date();
  const ayer = new Date(hoy.getTime() - 86_400_000);
  if (d.toDateString() === hoy.toDateString()) return "Hoy";
  if (d.toDateString() === ayer.toDateString()) return "Ayer";
  return d.toLocaleDateString("es", { weekday: "long", day: "numeric", month: "long" });
}

export function Registro() {
  const { datos, error, cargando } = useDatos<Evento[]>("/eventos?limite=500");
  const { datos: usuarios } = useDatos<Usuario[]>("/usuarios");
  const [buscar, setBuscar] = useState("");
  const nombre = (id: number | null) => (id === null ? "mufa" : usuarios?.find((u) => u.id === id)?.nombre ?? `#${id}`);

  const grupos = useMemo(() => {
    const f = buscar.trim().toLowerCase();
    const lista = (datos ?? []).filter((e) => {
      if (!f) return true;
      const texto = `${ACCIONES[e.accion]?.[0] ?? e.accion} ${e.accion} ${e.objeto} ${nombre(e.usuario_id)}`.toLowerCase();
      return texto.includes(f);
    });
    const porDia = new Map<string, Evento[]>();
    for (const e of lista) porDia.set(dia(e.cuando), [...(porDia.get(dia(e.cuando)) ?? []), e]);
    return [...porDia.entries()];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datos, buscar, usuarios]);

  return (
    <>
      <Encabezado titulo="Registro de eventos" subtitulo="Quién hizo qué y cuándo. Nunca incluye contraseñas ni lo que se escribe en la terminal." />
      <div className="buscador" style={{ maxWidth: 460 }}>
        <Icono nombre="buscar" className="tenue" />
        <input placeholder="Buscar: inició sesión, terminal, una IP, una persona…" value={buscar} onChange={(e) => setBuscar(e.target.value)} aria-label="Buscar en el registro" />
      </div>
      <MensajeError mensaje={error} />
      {cargando && !datos ? (
        <Cargando />
      ) : !grupos.length ? (
        <Tarjeta><Vacio titulo={buscar ? "Nada coincide" : "Todavía no hay eventos"} /></Tarjeta>
      ) : (
        grupos.map(([titulo, eventos]) => (
          <section key={titulo} className="registro-dia">
            <h2>{titulo}</h2>
            <Tarjeta sinRelleno>
              <ul className="registro-lista">
                {eventos.map((e) => {
                  const [texto, icono, tono] = ACCIONES[e.accion] ?? [e.accion, "lista", "neutro"];
                  const detalles = Object.entries(e.detalle ?? {});
                  return (
                    <li key={e.id} className="registro-fila">
                      <span className={`registro-icono ${tono}`}><Icono nombre={icono} /></span>
                      <div className="registro-cuerpo">
                        <div>
                          <strong>{texto}</strong>
                          {e.objeto && <span className="registro-objeto"> · {e.objeto}</span>}
                        </div>
                        <div className="registro-meta">
                          <span>{nombre(e.usuario_id)}</span>
                          {detalles.map(([k, v]) => (
                            <span key={k} className="registro-dato">{ETIQUETAS[k] ?? k}: {valor(k, v)}</span>
                          ))}
                        </div>
                      </div>
                      <time className="registro-hora" dateTime={e.cuando}>
                        {new Date(e.cuando).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}
                      </time>
                    </li>
                  );
                })}
              </ul>
            </Tarjeta>
          </section>
        ))
      )}
    </>
  );
}
