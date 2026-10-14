// Predicción de capacidad (mufa Pro): cuándo se queda corto cada enlace.
import { useState } from "react";
import { BarraUso, Cargando, Encabezado, Tarjeta, Vacio } from "../componentes/ui";
import { bps, useDatos } from "../util";

type Estado = "saturada" | "urgente" | "atencion" | "estable" | "aprendiendo";

interface Pronostico {
  equipo_id: number;
  equipo: string;
  if_index: number;
  interfaz: string;
  capacidad_mbps: number;
  uso_actual_pct: number;
  crecimiento_mensual_pct: number | null;
  dias_para_saturar: number | null;
  fecha_saturacion: string | null;
  estado: Estado;
  dias_de_datos: number;
  confianza: number | null;
}

interface Dia {
  dia: string;
  p95_entrada: number;
  p95_salida: number;
  max_entrada: number;
  max_salida: number;
}

interface Historial {
  equipo: string;
  interfaz: string;
  capacidad_mbps: number | null;
  umbral_pct: number;
  dias: Dia[];
  pronostico: Pronostico | null;
}

const MINIMO_DIAS = 14;

const ESTADOS: Record<Estado, { texto: string; clase: string }> = {
  saturada: { texto: "Saturada", clase: "critico" },
  urgente: { texto: "Menos de 2 meses", clase: "alto" },
  atencion: { texto: "Menos de 6 meses", clase: "medio" },
  estable: { texto: "Estable", clase: "ok" },
  aprendiendo: { texto: "Juntando datos", clase: "gris" },
};

function cuando(p: Pronostico): string {
  if (p.estado === "saturada") return "Ya en horas pico";
  if (p.estado === "aprendiendo") return `En ${MINIMO_DIAS - p.dias_de_datos} días hay tendencia`;
  if (p.dias_para_saturar === null) return "No crece";
  if (p.dias_para_saturar > 730) return "En más de 2 años";
  const dias = p.dias_para_saturar;
  const fecha = p.fecha_saturacion ? new Date(`${p.fecha_saturacion}T12:00:00`).toLocaleDateString("es", { day: "numeric", month: "short", year: "numeric" }) : "";
  const plazo = dias <= 1 ? "Mañana" : dias < 14 ? `En ${dias} días` : dias <= 60 ? `En ${Math.round(dias / 7)} semanas` : `En ${Math.round(dias / 30)} meses`;
  return `${plazo} · ${fecha}`;
}

function crecimiento(p: Pronostico): string {
  if (p.crecimiento_mensual_pct === null) return "—";
  const v = p.crecimiento_mensual_pct;
  return `${v > 0 ? "+" : ""}${v.toLocaleString("es", { maximumFractionDigits: 1 })} % al mes`;
}

export function Capacidad() {
  const { datos, cargando } = useDatos<Pronostico[]>("/pro/capacidad");
  const [elegida, setElegida] = useState<Pronostico | null>(null);
  const actual = elegida ?? datos?.find((p) => p.estado !== "aprendiendo") ?? null;
  const cuenta = (e: Estado) => datos?.filter((p) => p.estado === e).length ?? 0;

  return (
    <>
      <Encabezado
        titulo="Capacidad"
        subtitulo="Cuándo se queda corto cada enlace, según la carga en horas pico de los últimos 90 días."
      />
      {cargando && !datos ? (
        <Cargando />
      ) : !datos?.length ? (
        <Tarjeta>
          <Vacio titulo="Todavía no hay historial">
            <p className="tenue" style={{ maxWidth: 520, margin: "0 auto" }}>
              mufa resume una vez por día el tráfico de cada interfaz de los equipos con SNMP. Mañana aparecen los primeros
              datos, y en {MINIMO_DIAS} días, la tendencia de cada enlace.
            </p>
          </Vacio>
        </Tarjeta>
      ) : (
        <div className="pila" style={{ gap: 14 }}>
          <div className="capacidad-resumen">
            {(["saturada", "urgente", "atencion", "estable"] as Estado[]).map((e) => (
              <div key={e} className={`tarjeta capacidad-cifra ${ESTADOS[e].clase}`}>
                <span className="tenue">{ESTADOS[e].texto}</span>
                <strong>{cuenta(e)}</strong>
              </div>
            ))}
          </div>

          {actual && <Detalle key={`${actual.equipo_id}-${actual.if_index}`} pronostico={actual} />}

          <Tarjeta titulo="Enlaces, del más urgente al más tranquilo" sinRelleno>
            <div className="tabla-caja">
              <table>
                <thead>
                  <tr>
                    <th>Se satura</th><th>Equipo · interfaz</th><th>Velocidad</th><th>Uso en horas pico</th><th>Crecimiento</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.map((p) => {
                    const activa = actual?.equipo_id === p.equipo_id && actual?.if_index === p.if_index;
                    return (
                      <tr key={`${p.equipo_id}-${p.if_index}`} className={activa ? "clic activa" : "clic"} onClick={() => setElegida(p)}>
                        <td>
                          <span className={`pill ${ESTADOS[p.estado].clase}`}>{ESTADOS[p.estado].texto}</span>
                          <div className="tenue" style={{ fontSize: 12, marginTop: 4 }}>{cuando(p)}</div>
                        </td>
                        <td style={{ fontWeight: 500 }}>
                          {p.equipo}
                          <div className="tenue mono" style={{ fontWeight: 400 }}>{p.interfaz}</div>
                        </td>
                        <td>{bps(p.capacidad_mbps * 1e6)}</td>
                        <td style={{ minWidth: 160 }}><BarraUso porcentaje={p.uso_actual_pct} /></td>
                        <td className={(p.estado === "urgente" || p.estado === "atencion") ? "texto-alerta" : "tenue"}>{crecimiento(p)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Tarjeta>
          <p className="tenue" style={{ fontSize: 12, margin: 0 }}>
            «Uso en horas pico» es el percentil 95 del día: la carga que el enlace sostiene, sin contar picos de unos minutos.
            Un enlace se considera saturado al pasar el 80 % de su velocidad. La velocidad es la que informa el equipo por SNMP.
          </p>
        </div>
      )}
    </>
  );
}

function Detalle({ pronostico }: { pronostico: Pronostico }) {
  const { datos } = useDatos<Historial>(`/pro/capacidad/${pronostico.equipo_id}/${pronostico.if_index}`);
  return (
    <Tarjeta
      titulo={
        <>
          {pronostico.equipo} <span className="tenue mono" style={{ fontWeight: 400 }}>· {pronostico.interfaz}</span>
        </>
      }
      acciones={<span className={`pill ${ESTADOS[pronostico.estado].clase}`}>{cuando(pronostico)}</span>}
    >
      {!datos ? <Cargando /> : <Grafica historial={datos} />}
      <div className="capacidad-datos">
        <div><span className="tenue">Velocidad</span><strong>{bps(pronostico.capacidad_mbps * 1e6)}</strong></div>
        <div><span className="tenue">Uso en horas pico</span><strong>{pronostico.uso_actual_pct.toLocaleString("es")} %</strong></div>
        <div><span className="tenue">Crecimiento</span><strong>{crecimiento(pronostico)}</strong></div>
        <div>
          <span className="tenue">Confianza</span>
          <strong>{pronostico.confianza === null ? "—" : pronostico.confianza >= 0.7 ? "Alta" : pronostico.confianza >= 0.4 ? "Media" : "Baja"}</strong>
        </div>
      </div>
    </Tarjeta>
  );
}

const ANCHO = 760;
const ALTO = 240;
const MARGEN = { izq: 64, der: 16, arr: 14, aba: 28 };
const DIA_MS = 86_400_000;

function Grafica({ historial }: { historial: Historial }) {
  const puntos = historial.dias.map((d) => ({ t: new Date(`${d.dia}T12:00:00`).getTime(), v: Math.max(d.p95_entrada, d.p95_salida) }));
  const capacidad = (historial.capacidad_mbps ?? 0) * 1e6;
  const umbral = (capacidad * historial.umbral_pct) / 100;
  const p = historial.pronostico;
  const hoy = Date.now();
  // Como en el servidor: la tendencia sale de los últimos 90 días y llega hasta la
  // saturación (o 60 días hacia adelante si no crece).
  const ventana = puntos.filter((pt) => pt.t >= hoy - 90 * DIA_MS);
  const recta = tendencia(ventana);
  const inicioRecta = ventana[0]?.t;
  const unico = puntos.length === 1 ? puntos[0] : undefined;
  const fin = p?.fecha_saturacion && p.estado !== "saturada"
    ? Math.min(new Date(`${p.fecha_saturacion}T12:00:00`).getTime(), hoy + 365 * DIA_MS)
    : hoy + 60 * DIA_MS;
  const t0 = puntos[0]?.t ?? hoy;
  const t1 = Math.max(fin, hoy);
  const vMax = Math.max(capacidad, ...puntos.map((x) => x.v), 1);
  const x = (t: number) => MARGEN.izq + ((t - t0) / Math.max(t1 - t0, DIA_MS)) * (ANCHO - MARGEN.izq - MARGEN.der);
  const y = (v: number) => MARGEN.arr + (1 - v / vMax) * (ALTO - MARGEN.arr - MARGEN.aba);
  const linea = puntos.map((pt, i) => `${i ? "L" : "M"}${x(pt.t).toFixed(1)},${y(pt.v).toFixed(1)}`).join(" ");
  const meses = marcasDeMes(t0, t1);

  return (
    <svg className="grafica-capacidad" viewBox={`0 0 ${ANCHO} ${ALTO}`} role="img" aria-label={`Uso en horas pico de ${historial.interfaz} y su tendencia`}>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}>
          <line x1={MARGEN.izq} x2={ANCHO - MARGEN.der} y1={y(vMax * f)} y2={y(vMax * f)} className="eje" />
          <text x={MARGEN.izq - 8} y={y(vMax * f) + 4} textAnchor="end" className="etiqueta">{bps(vMax * f)}</text>
        </g>
      ))}
      {meses.map((m) => (
        <text key={m.t} x={x(m.t)} y={ALTO - 8} textAnchor="middle" className="etiqueta">{m.texto}</text>
      ))}
      {capacidad > 0 && (
        <>
          <line x1={MARGEN.izq} x2={ANCHO - MARGEN.der} y1={y(umbral)} y2={y(umbral)} className="umbral" />
          <text x={ANCHO - MARGEN.der} y={y(umbral) - 6} textAnchor="end" className="etiqueta umbral-texto">{historial.umbral_pct} %</text>
        </>
      )}
      <line x1={x(hoy)} x2={x(hoy)} y1={MARGEN.arr} y2={ALTO - MARGEN.aba} className="hoy" />
      <text x={x(hoy)} y={MARGEN.arr + 10} textAnchor="middle" className="etiqueta">hoy</text>
      {recta && inicioRecta !== undefined && ventana.length >= MINIMO_DIAS && (
        <line x1={x(inicioRecta)} y1={y(recta(inicioRecta))} x2={x(t1)} y2={y(recta(t1))} className="tendencia" />
      )}
      <path d={linea} className="serie" />
      {unico && <circle cx={x(unico.t)} cy={y(unico.v)} r={3} className="punto" />}
    </svg>
  );
}

function tendencia(puntos: { t: number; v: number }[]): ((t: number) => number) | null {
  if (puntos.length < 2) return null;
  const n = puntos.length;
  const mx = puntos.reduce((s, p) => s + p.t, 0) / n;
  const my = puntos.reduce((s, p) => s + p.v, 0) / n;
  const sxx = puntos.reduce((s, p) => s + (p.t - mx) ** 2, 0);
  if (!sxx) return null;
  const m = puntos.reduce((s, p) => s + (p.t - mx) * (p.v - my), 0) / sxx;
  return (t) => Math.max(0, my + m * (t - mx));
}

function marcasDeMes(t0: number, t1: number): { t: number; texto: string }[] {
  const marcas = [];
  const d = new Date(t0);
  d.setDate(1);
  d.setMonth(d.getMonth() + 1);
  const paso = (t1 - t0) / DIA_MS > 240 ? 2 : 1;
  while (d.getTime() < t1) {
    marcas.push({ t: d.getTime(), texto: d.toLocaleDateString("es", { month: "short" }) });
    d.setMonth(d.getMonth() + paso);
  }
  return marcas;
}
