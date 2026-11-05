// Página de estado pública (mufa Pro): lo que ven los clientes del ISP, y cómo se configura.
import { LOCALE } from "../i18n";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { api, textoDeError } from "../api";
import { BotonCopiar, Campo, Cargando, Encabezado, Formulario, Tarjeta } from "../componentes/ui";
import type { Equipo } from "../tipos";
import { fecha, useDatos } from "../util";

interface Grupo {
  nombre: string;
  equipo_ids: number[];
}

interface Ajustes {
  activo: boolean;
  titulo: string;
  mensaje: string;
  codigo: string;
  grupos: Grupo[];
}

interface Pagina {
  titulo: string;
  mensaje: string;
  estado: string;
  grupos: { nombre: string; estado: string; disponibilidad: number | null; dias: { dia: string; disponibilidad: number | null }[] }[];
  incidentes: { grupo: string; inicio: string; fin: string | null }[];
  mantenimientos: { titulo: string; grupos: string[]; inicio: string; fin: string; en_curso: boolean }[];
  actualizado: string;
}

type Info = { texto: string; titulo: string; clase: string };
const SIN_DATOS: Info = { texto: "Sin datos", titulo: "Todavía no hay datos", clase: "gris" };
const ESTADOS: Record<string, Info> = {
  operativo: { texto: "Funcionando", titulo: "Todo funciona con normalidad", clase: "ok" },
  parcial: { texto: "Falla parcial", titulo: "Parte del servicio tiene problemas", clase: "medio" },
  caido: { texto: "Sin servicio", titulo: "Hay una falla en el servicio", clase: "critico" },
  mantenimiento: { texto: "Mantenimiento", titulo: "Trabajos de mantenimiento en curso", clase: "info" },
  sin_datos: { texto: "Sin datos", titulo: "Todavía no hay datos", clase: "gris" },
};

function porcentaje(valor: number | null): string {
  if (valor === null) return "—";
  return `${(valor * 100).toLocaleString(LOCALE, { maximumFractionDigits: 2, minimumFractionDigits: 2 })} %`;
}

function claseDia(valor: number | null): string {
  if (valor === null) return "sin";
  if (valor >= 0.999) return "ok";
  if (valor >= 0.98) return "medio";
  return "mal";
}

function duracionEntre(inicio: string, fin: string | null): string {
  const minutos = Math.max(1, Math.round(((fin ? new Date(fin).getTime() : Date.now()) - new Date(inicio).getTime()) / 60000));
  if (minutos < 60) return `${minutos} min`;
  const horas = Math.floor(minutos / 60);
  return minutos % 60 ? `${horas} h ${minutos % 60} min` : `${horas} h`;
}

/** La página en sí: la usan la vista pública y la vista previa del ISP. */
export function VistaEstado({ pagina }: { pagina: Pagina }) {
  const general = ESTADOS[pagina.estado] ?? SIN_DATOS;
  return (
    <div className="estado-publico">
      <h1>{pagina.titulo}</h1>
      <div className={`estado-general ${general.clase}`}>{general.titulo}</div>
      {pagina.mensaje && <div className="aviso info estado-mensaje">{pagina.mensaje}</div>}

      {pagina.mantenimientos.length > 0 && (
        <section>
          <h2>Mantenimientos</h2>
          {pagina.mantenimientos.map((m) => (
            <div key={`${m.titulo}${m.inicio}`} className="estado-item">
              <strong>{m.titulo}</strong> {m.en_curso && <span className="pill info">En curso</span>}
              <div className="tenue">{fecha(m.inicio)} → {fecha(m.fin)} · {m.grupos.join(", ")}</div>
            </div>
          ))}
        </section>
      )}

      <section>
        <h2>Servicio</h2>
        {pagina.grupos.map((g) => {
          const e = ESTADOS[g.estado] ?? SIN_DATOS;
          return (
            <div key={g.nombre} className="estado-grupo">
              <div className="entre">
                <strong>{g.nombre}</strong>
                <span className={`pill ${e.clase}`}>{e.texto}</span>
              </div>
              <div className="estado-dias" aria-label={`Últimos ${g.dias.length} días`}>
                {g.dias.map((d) => (
                  <i key={d.dia} className={claseDia(d.disponibilidad)} title={`${d.dia}: ${porcentaje(d.disponibilidad)}`} />
                ))}
              </div>
              <div className="entre tenue" style={{ fontSize: 12 }}>
                <span>Hace {g.dias.length} días</span>
                <span>{porcentaje(g.disponibilidad)} disponible</span>
                <span>Hoy</span>
              </div>
            </div>
          );
        })}
        {pagina.grupos.length === 0 && <p className="tenue">Todavía no hay zonas configuradas.</p>}
      </section>

      <section>
        <h2>Fallas recientes</h2>
        {pagina.incidentes.length === 0 && <p className="tenue">Sin fallas en los últimos 14 días.</p>}
        {pagina.incidentes.map((i) => (
          <div key={`${i.grupo}${i.inicio}`} className="estado-item">
            <strong>{i.grupo}</strong> {i.fin ? <span className="pill ok">Resuelta</span> : <span className="pill critico">En curso</span>}
            <div className="tenue">{fecha(i.inicio)} · {i.fin ? `duró ${duracionEntre(i.inicio, i.fin)}` : `hace ${duracionEntre(i.inicio, null)}`}</div>
          </div>
        ))}
      </section>
      <p className="tenue estado-pie">Actualizado {fecha(pagina.actualizado)} · con mufa</p>
    </div>
  );
}

/** /estado/:codigo — sin sesión, para los clientes del ISP. Se actualiza sola. */
export function PaginaEstadoPublica() {
  const { codigo = "" } = useParams();
  const [pagina, setPagina] = useState<Pagina | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    const cargar = () =>
      api<Pagina>(`/pro/estado-publico/pagina/${encodeURIComponent(codigo)}`)
        .then((p) => { if (vivo) { setPagina(p); setError(null); document.title = p.titulo; } })
        .catch((e) => { if (vivo) setError(textoDeError(e)); });
    cargar();
    const reloj = window.setInterval(cargar, 60_000);
    return () => { vivo = false; window.clearInterval(reloj); };
  }, [codigo]);
  if (error && !pagina) return <div className="estado-publico"><h1>Página no encontrada</h1><p className="tenue">Revisa la dirección.</p></div>;
  if (!pagina) return <Cargando />;
  return <VistaEstado pagina={pagina} />;
}

/** Ajustes de la página, para el ISP. */
export function EstadoPublico() {
  const ajustes = useDatos<Ajustes>("/pro/estado-publico");
  const previa = useDatos<Pagina>("/pro/estado-publico/vista-previa");
  const recargar = () => { ajustes.recargar(); previa.recargar(); };
  return (
    <>
      <Encabezado
        titulo="Página de estado"
        subtitulo="Una página para tus clientes: si el servicio funciona, las fallas de los últimos días y los mantenimientos que vienen. Menos llamadas al soporte cuando hay una falla."
      />
      <div className="fila" style={{ alignItems: "flex-start" }}>
        <div className="crece">
          {ajustes.datos ? <Configurar key={JSON.stringify(ajustes.datos)} inicial={ajustes.datos} onGuardado={recargar} /> : <Cargando />}
        </div>
        <div className="crece">
          <Tarjeta titulo="Así la ven tus clientes">
            {previa.datos ? <VistaEstado pagina={previa.datos} /> : <Cargando />}
          </Tarjeta>
        </div>
      </div>
    </>
  );
}

function Configurar({ inicial, onGuardado }: { inicial: Ajustes; onGuardado: () => void }) {
  const { datos: equipos } = useDatos<Equipo[]>("/equipos");
  const [activo, setActivo] = useState(inicial.activo);
  const [titulo, setTitulo] = useState(inicial.titulo);
  const [mensaje, setMensaje] = useState(inicial.mensaje);
  const [grupos, setGrupos] = useState<Grupo[]>(inicial.grupos.length ? inicial.grupos : [{ nombre: "", equipo_ids: [] }]);
  const enlace = `${window.location.origin}${import.meta.env.BASE_URL}estado/${inicial.codigo}`;

  const cambiarGrupo = (n: number, cambio: Partial<Grupo>) => setGrupos(grupos.map((g, i) => (i === n ? { ...g, ...cambio } : g)));

  return (
    <Tarjeta titulo="Configuración">
      {inicial.activo && (
        <div className="aviso ok pila" style={{ marginBottom: 12, gap: 6 }}>
          <span>Publicada en:</span>
          <div className="fila" style={{ gap: 6, alignItems: "center" }}>
            <a className="mono" href={enlace} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: "break-all" }}>{enlace}</a>
            <BotonCopiar texto={enlace} />
          </div>
        </div>
      )}
      <Formulario
        textoBoton="Guardar"
        onEnviar={async () => {
          const validos = grupos.filter((g) => g.nombre.trim());
          await api("/pro/estado-publico", { metodo: "PUT", cuerpo: { activo, titulo, mensaje, grupos: validos } });
          onGuardado();
        }}
      >
        <Campo etiqueta="Título" ancho><input value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={120} required /></Campo>
        <Campo etiqueta="Aviso arriba de todo (opcional)" ancho ayuda="Por ejemplo: «Estamos trabajando en una falla de fibra en la zona norte».">
          <textarea value={mensaje} onChange={(e) => setMensaje(e.target.value)} maxLength={1000} rows={2} />
        </Campo>
        <fieldset className="ancho">
          <legend>Zonas o servicios</legend>
          <p className="tenue" style={{ fontSize: 12, marginTop: 0 }}>
            Tus clientes ven el nombre de cada zona, nunca los nombres ni las IPs de los equipos.
          </p>
          {grupos.map((g, n) => (
            <div key={n} className="pila" style={{ gap: 6, marginBottom: 12 }}>
              <div className="fila" style={{ gap: 6 }}>
                <input className="crece" value={g.nombre} placeholder="Zona Norte" maxLength={80} onChange={(e) => cambiarGrupo(n, { nombre: e.target.value })} />
                <button type="button" className="boton chico peligro" onClick={() => setGrupos(grupos.filter((_, i) => i !== n))}>Quitar</button>
              </div>
              <select
                multiple
                value={g.equipo_ids.map(String)}
                onChange={(e) => cambiarGrupo(n, { equipo_ids: Array.from(e.target.selectedOptions, (o) => Number(o.value)) })}
                style={{ minHeight: 90 }}
                aria-label={`Equipos de ${g.nombre || "la zona"}`}
              >
                {(equipos ?? []).map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
              </select>
            </div>
          ))}
          <button type="button" className="boton chico" onClick={() => setGrupos([...grupos, { nombre: "", equipo_ids: [] }])}>Agregar zona</button>
        </fieldset>
        <label className="casilla ancho"><input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Página publicada</label>
      </Formulario>
      <div className="fila" style={{ gap: 8, marginTop: 12, alignItems: "center" }}>
        <button
          className="boton chico"
          title="La dirección anterior deja de funcionar"
          onClick={async () => { if (window.confirm("¿Cambiar la dirección? La anterior deja de funcionar.")) { await api("/pro/estado-publico/nuevo-codigo", { metodo: "POST" }); onGuardado(); } }}
        >
          Cambiar la dirección
        </button>
      </div>
      <p className="tenue" style={{ fontSize: 12, marginBottom: 0 }}>
        La página está en tu servidor de mufa. Para que la vean desde internet, publica solo <span className="mono">/estado/</span>,{" "}
        <span className="mono">/assets/</span> y <span className="mono">/api/v1/pro/estado-publico/pagina/</span> en tu proxy.
        Mantén cerrado el resto de mufa.
      </p>
    </Tarjeta>
  );
}
