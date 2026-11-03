// Ventanas de mantenimiento (mufa Pro): mientras duran, los equipos elegidos no avisan.
import { LOCALE } from "../i18n";
import { useState } from "react";
import { api } from "../api";
import { Campo, Encabezado, Formulario, Modal, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Equipo } from "../tipos";
import { fecha, puede, useDatos } from "../util";

interface Ventana {
  id: string;
  titulo: string;
  inicio: string;
  fin: string;
  equipos: { id: number; nombre: string }[];
  toda_la_red: boolean;
  motivo: string;
  semanal: boolean;
  creada_por: string;
  estado: "activa" | "programada" | "terminada";
  proxima_inicio: string | null;
  proxima_fin: string | null;
}

const ESTADOS: Record<Ventana["estado"], { texto: string; clase: string }> = {
  activa: { texto: "En curso", clase: "medio" },
  programada: { texto: "Programada", clase: "info" },
  terminada: { texto: "Terminada", clase: "gris" },
};

const DIAS_SEMANA = ["domingos", "lunes", "martes", "miércoles", "jueves", "viernes", "sábados"];

/** «2026-11-02T14:30» para un <input type="datetime-local">, en hora local. */
function aLocal(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
}

function cuando(v: Ventana): string {
  if (v.semanal) {
    const inicio = new Date(v.inicio);
    return `Los ${DIAS_SEMANA[inicio.getDay()]} de ${hora(v.inicio)} a ${hora(v.fin)}`;
  }
  return `${fecha(v.inicio)} → ${fecha(v.fin)}`;
}

export function Mantenimiento() {
  const { usuario } = useSesion();
  const gestiona = puede(usuario?.rol, "gestionar_equipos");
  const { datos, recargar } = useDatos<Ventana[]>("/pro/mantenimiento");
  const [editando, setEditando] = useState<Ventana | "nueva" | null>(null);
  const activas = datos?.filter((v) => v.estado === "activa") ?? [];

  return (
    <>
      <Encabezado
        titulo="Mantenimiento"
        subtitulo="Mientras dura una ventana, sus equipos no avisan: ni las alertas ni los avisos al equipo. Todo queda igual en el registro."
        acciones={gestiona && <button className="boton primario" onClick={() => setEditando("nueva")}>Nueva ventana</button>}
      />
      {activas.length > 0 && (
        <div className="aviso atencion" style={{ marginBottom: 14 }}>
          En mantenimiento ahora: {activas.map((v) => v.titulo).join(", ")}. Sus alertas están en silencio.
        </div>
      )}
      <Tarjeta sinRelleno>
        {datos && datos.length === 0 && (
          <Vacio titulo="Sin ventanas de mantenimiento">
            Programa el cambio de un equipo o una tarea que se repite cada semana (reiniciar antenas, actualizar firmware)
            para que el NOC no reciba alertas de algo que ya sabe.
          </Vacio>
        )}
        {datos && datos.length > 0 && (
          <div className="tabla-caja">
            <table>
              <thead><tr><th>Ventana</th><th>Cuándo</th><th>Equipos</th><th>Estado</th><th /></tr></thead>
              <tbody>
                {datos.map((v) => (
                  <tr key={v.id}>
                    <td style={{ fontWeight: 500 }}>
                      {v.titulo}
                      {v.motivo && <div className="tenue" style={{ fontSize: 12, fontWeight: 400 }}>{v.motivo}</div>}
                    </td>
                    <td>
                      {cuando(v)}
                      {v.semanal && v.proxima_inicio && v.estado !== "activa" && (
                        <div className="tenue" style={{ fontSize: 12 }}>Próxima: {fecha(v.proxima_inicio)}</div>
                      )}
                    </td>
                    <td>{v.toda_la_red ? <span className="pill gris">Toda la red</span> : v.equipos.map((e) => e.nombre).join(", ")}</td>
                    <td><span className={`pill ${ESTADOS[v.estado].clase}`}>{ESTADOS[v.estado].texto}</span></td>
                    <td>
                      {gestiona && (
                        <div className="fila" style={{ gap: 6, justifyContent: "flex-end", flexWrap: "wrap" }}>
                          {v.estado === "activa" && (
                            <button className="boton chico" title="Los avisos vuelven desde ahora" onClick={async () => { await api(`/pro/mantenimiento/${v.id}/terminar`, { metodo: "POST" }); recargar(); }}>
                              Terminar ya
                            </button>
                          )}
                          <button className="boton chico" onClick={() => setEditando(v)}>Editar</button>
                          <button className="boton chico peligro" onClick={async () => { if (window.confirm(`¿Borrar «${v.titulo}»?`)) { await api(`/pro/mantenimiento/${v.id}`, { metodo: "DELETE" }); recargar(); } }}>
                            Borrar
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
      {editando && (
        <EditarVentana
          ventana={editando === "nueva" ? null : editando}
          onCerrar={() => setEditando(null)}
          onGuardada={() => { setEditando(null); recargar(); }}
        />
      )}
    </>
  );
}

function EditarVentana({ ventana, onCerrar, onGuardada }: { ventana: Ventana | null; onCerrar: () => void; onGuardada: () => void }) {
  const { datos: equipos } = useDatos<Equipo[]>("/equipos");
  const enUnaHora = new Date(Date.now() + 3600_000).toISOString();
  const [titulo, setTitulo] = useState(ventana?.titulo ?? "");
  const [inicio, setInicio] = useState(aLocal(ventana?.inicio ?? new Date().toISOString()));
  const [fin, setFin] = useState(aLocal(ventana?.fin ?? enUnaHora));
  const [motivo, setMotivo] = useState(ventana?.motivo ?? "");
  const [semanal, setSemanal] = useState(ventana?.semanal ?? false);
  const [todaLaRed, setTodaLaRed] = useState(ventana?.toda_la_red ?? false);
  const [elegidos, setElegidos] = useState<number[]>(ventana?.equipos.map((e) => e.id) ?? []);
  const [filtro, setFiltro] = useState("");
  const visibles = (equipos ?? []).filter((e) => e.nombre.toLowerCase().includes(filtro.toLowerCase()));

  return (
    <Modal titulo={ventana ? "Editar ventana" : "Nueva ventana de mantenimiento"} onCerrar={onCerrar}>
      <Formulario
        textoBoton="Guardar"
        onCancelar={onCerrar}
        onEnviar={async () => {
          if (!todaLaRed && elegidos.length === 0) throw new Error("Elige al menos un equipo, o toda la red.");
          const cuerpo = {
            titulo,
            inicio: new Date(inicio).toISOString(),
            fin: new Date(fin).toISOString(),
            motivo,
            semanal,
            equipo_ids: todaLaRed ? [] : elegidos,
          };
          await api(ventana ? `/pro/mantenimiento/${ventana.id}` : "/pro/mantenimiento", { metodo: ventana ? "PUT" : "POST", cuerpo });
          onGuardada();
        }}
      >
        <Campo etiqueta="Título" ancho>
          <input value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={120} placeholder="Actualizar RouterOS del core" required />
        </Campo>
        <div className="fila">
          <Campo etiqueta="Desde"><input type="datetime-local" value={inicio} onChange={(e) => setInicio(e.target.value)} required /></Campo>
          <Campo etiqueta="Hasta"><input type="datetime-local" value={fin} onChange={(e) => setFin(e.target.value)} required /></Campo>
        </div>
        <label className="casilla"><input type="checkbox" checked={semanal} onChange={(e) => setSemanal(e.target.checked)} /> Repetir cada semana a la misma hora</label>
        <Campo etiqueta="Motivo (opcional)" ancho>
          <input value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={500} placeholder="Para el registro y los informes" />
        </Campo>
        <fieldset className="ancho">
          <legend>Equipos</legend>
          <label className="casilla"><input type="checkbox" checked={todaLaRed} onChange={(e) => setTodaLaRed(e.target.checked)} /> Toda la red</label>
          {!todaLaRed && (
            <>
              <input type="search" placeholder="Buscar equipo…" value={filtro} onChange={(e) => setFiltro(e.target.value)} style={{ margin: "6px 0" }} />
              <div className="pila" style={{ gap: 2, maxHeight: 220, overflowY: "auto" }}>
                {visibles.map((e) => (
                  <label key={e.id} className="casilla">
                    <input
                      type="checkbox"
                      checked={elegidos.includes(e.id)}
                      onChange={(ev) => setElegidos(ev.target.checked ? [...elegidos, e.id] : elegidos.filter((x) => x !== e.id))}
                    />{" "}
                    {e.nombre} <span className="tenue mono" style={{ fontSize: 12 }}>{e.ip_gestion}</span>
                  </label>
                ))}
              </div>
            </>
          )}
        </fieldset>
      </Formulario>
    </Modal>
  );
}
