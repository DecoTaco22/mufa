// Mapa de topología (vecinos LLDP, CDP y MikroTik) y modo NOC para la pantalla del NOC.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, textoDeError } from "../api";
import { Cargando, Encabezado, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Panel } from "../tipos";
import { hace, puede, useDatos } from "../util";

export interface NodoMapa {
  id: string;
  nombre: string;
  marca: string;
  ip: string;
  sitio: string;
  estado: "en_linea" | "caido" | "alcanzable" | "sin_snmp" | "desconocido" | "fuera";
  plataforma: string;
}

interface EnlaceMapa {
  desde: string;
  hasta: string;
  interfaz: string;
  puerto: string;
}

interface DatosMapa {
  nodos: NodoMapa[];
  enlaces: EnlaceMapa[];
  actualizado: string | null;
  eventos: { cuando: string; tipo: string; titulo: string; objeto: string }[];
}

export const COLORES: Record<NodoMapa["estado"], { color: string; texto: string }> = {
  en_linea: { color: "var(--ok)", texto: "En línea" },
  caido: { color: "var(--rojo)", texto: "Caído" },
  alcanzable: { color: "var(--nar)", texto: "Encendido, sin SNMP" },
  sin_snmp: { color: "var(--tx3)", texto: "Sin monitoreo" },
  desconocido: { color: "var(--tx3)", texto: "Sin datos" },
  fuera: { color: "transparent", texto: "No está en mufa" },
};

type Punto = { x: number; y: number };
const CLAVE_POSICIONES = "mufa.mapa.posiciones";

function posicionesGuardadas(): Record<string, Punto> {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_POSICIONES) ?? "{}") as Record<string, Punto>;
  } catch {
    return {};
  }
}

function guardarPosiciones(p: Record<string, Punto>) {
  try {
    localStorage.setItem(CLAVE_POSICIONES, JSON.stringify(p));
  } catch {
    // Sin almacenamiento (ventana privada): el mapa se vuelve a acomodar solo.
  }
}

/** Acomoda los nodos: se repelen entre sí y los enlaces los atraen (fuerzas simples). */
function acomodar(nodos: NodoMapa[], enlaces: EnlaceMapa[], fijas: Record<string, Punto>): Record<string, Punto> {
  const p: Record<string, Punto> = {};
  nodos.forEach((n, i) => {
    const angulo = (2 * Math.PI * i) / Math.max(nodos.length, 1);
    const fija = fijas[n.id];
    p[n.id] = fija ? { x: fija.x, y: fija.y } : { x: 400 + 60 * Math.sqrt(nodos.length) * Math.cos(angulo), y: 300 + 60 * Math.sqrt(nodos.length) * Math.sin(angulo) };
  });
  // Distancia ideal entre equipos: con espacio para el nombre debajo de cada uno.
  const k = 210;
  for (let paso = 0; paso < 400; paso++) {
    const fuerza: Record<string, Punto> = Object.fromEntries(nodos.map((n) => [n.id, { x: 0, y: 0 }]));
    for (let i = 0; i < nodos.length; i++) {
      for (let j = i + 1; j < nodos.length; j++) {
        const a = p[nodos[i]!.id]!;
        const b = p[nodos[j]!.id]!;
        const dx = a.x - b.x || 0.01;
        const dy = a.y - b.y || 0.01;
        const d2 = Math.max(dx * dx + dy * dy, 1);
        const f = (k * k) / d2;
        fuerza[nodos[i]!.id]!.x += dx * f / Math.sqrt(d2);
        fuerza[nodos[i]!.id]!.y += dy * f / Math.sqrt(d2);
        fuerza[nodos[j]!.id]!.x -= dx * f / Math.sqrt(d2);
        fuerza[nodos[j]!.id]!.y -= dy * f / Math.sqrt(d2);
      }
    }
    for (const e of enlaces) {
      const a = p[e.desde];
      const b = p[e.hasta];
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const f = (d * d) / k / d;
      fuerza[e.desde]!.x += dx * f;
      fuerza[e.desde]!.y += dy * f;
      fuerza[e.hasta]!.x -= dx * f;
      fuerza[e.hasta]!.y -= dy * f;
    }
    const temperatura = 40 * (1 - paso / 400) + 1;
    for (const n of nodos) {
      if (fijas[n.id]) continue;
      const f = fuerza[n.id]!;
      // Un poco de gravedad al centro: los equipos sueltos no se van lejos.
      f.x += (400 - p[n.id]!.x) * 0.006;
      f.y += (300 - p[n.id]!.y) * 0.006;
      const largo = Math.max(Math.sqrt(f.x * f.x + f.y * f.y), 0.01);
      p[n.id]!.x += (f.x / largo) * Math.min(largo, temperatura);
      p[n.id]!.y += (f.y / largo) * Math.min(largo, temperatura);
    }
  }
  return p;
}

export function DibujoMapa({ datos, compacto = false }: { datos: DatosMapa; compacto?: boolean }) {
  const navegar = useNavigate();
  const [fijas, setFijas] = useState<Record<string, Punto>>(posicionesGuardadas);
  const [arrastrando, setArrastrando] = useState<string | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const posiciones = useMemo(() => acomodar(datos.nodos, datos.enlaces, fijas), [datos, fijas]);

  const xs = Object.values(posiciones).map((p) => p.x);
  const ys = Object.values(posiciones).map((p) => p.y);
  const margen = 70;
  const caja = xs.length
    ? [Math.min(...xs) - margen, Math.min(...ys) - margen, Math.max(...xs) - Math.min(...xs) + 2 * margen, Math.max(...ys) - Math.min(...ys) + 2 * margen]
    : [0, 0, 800, 600];

  function aPunto(evento: React.PointerEvent): Punto | null {
    const el = svg.current;
    const matriz = el?.getScreenCTM();
    if (!el || !matriz) return null;
    const punto = new DOMPoint(evento.clientX, evento.clientY).matrixTransform(matriz.inverse());
    return { x: punto.x, y: punto.y };
  }

  return (
    <svg
      ref={svg}
      className={compacto ? "mapa-svg compacto" : "mapa-svg"}
      viewBox={caja.join(" ")}
      role="img"
      aria-label="Mapa de la red"
      onPointerMove={(e) => {
        if (!arrastrando) return;
        const punto = aPunto(e);
        if (punto) setFijas((f) => ({ ...f, [arrastrando]: punto }));
      }}
      onPointerUp={() => {
        if (arrastrando) guardarPosiciones(fijas);
        setArrastrando(null);
      }}
    >
      {datos.enlaces.map((e) => {
        const a = posiciones[e.desde];
        const b = posiciones[e.hasta];
        if (!a || !b) return null;
        return (
          <g key={`${e.desde}-${e.hasta}`}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="mapa-enlace" />
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="mapa-enlace-zona">
              <title>{`${e.interfaz || "?"} ↔ ${e.puerto || "?"}`}</title>
            </line>
          </g>
        );
      })}
      {datos.nodos.map((n) => {
        const p = posiciones[n.id];
        if (!p) return null;
        const estilo = COLORES[n.estado];
        const enMufa = n.id.startsWith("e");
        return (
          <g
            key={n.id}
            transform={`translate(${p.x} ${p.y})`}
            className={enMufa ? "mapa-nodo clic" : "mapa-nodo"}
            onPointerDown={(e) => {
              if (compacto) return;
              (e.target as Element).setPointerCapture?.(e.pointerId);
              setArrastrando(n.id);
            }}
            onDoubleClick={() => enMufa && navegar(`/equipos/${n.id.slice(1)}`)}
          >
            <title>{[n.nombre, n.ip, n.marca || n.plataforma, n.sitio, estilo.texto].filter(Boolean).join(" · ")}</title>
            <circle r={compacto ? 14 : 18} fill={estilo.color} stroke={enMufa ? "var(--card)" : "var(--tx3)"} strokeWidth={enMufa ? 3 : 2} strokeDasharray={enMufa ? undefined : "4 3"} />
            {n.estado === "caido" && <circle r={compacto ? 22 : 26} className="mapa-pulso" />}
            <text y={compacto ? 30 : 36} textAnchor="middle" className="mapa-etiqueta">{n.nombre}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function Mapa() {
  const { usuario } = useSesion();
  const { datos, cargando, recargar } = useDatos<DatosMapa>("/mapa");
  const [buscando, setBuscando] = useState(false);
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null);
  const diagnostica = puede(usuario?.rol, "diagnosticar");

  async function descubrir() {
    setBuscando(true);
    setMensaje(null);
    try {
      const r = await api<{ equipos: number; vecinos: number; errores: Record<string, string> }>("/mapa/descubrir", { metodo: "POST" });
      const fallas = Object.keys(r.errores);
      setMensaje({
        ok: fallas.length === 0,
        texto: `${r.vecinos} vecinos en ${r.equipos} equipos.${fallas.length ? ` No respondieron: ${fallas.join(", ")}.` : ""}`,
      });
      recargar();
    } catch (e) {
      setMensaje({ ok: false, texto: textoDeError(e) });
    } finally {
      setBuscando(false);
    }
  }

  return (
    <>
      <Encabezado
        titulo="Mapa"
        subtitulo="Qué equipo está conectado con cuál, según los vecinos que cada uno ve (LLDP, CDP y MikroTik)."
        acciones={
          <div className="fila" style={{ gap: 8 }}>
            {diagnostica && (
              <button className="boton" disabled={buscando} onClick={() => void descubrir()}>
                {buscando ? "Leyendo vecinos…" : "Actualizar vecinos"}
              </button>
            )}
            <Link className="boton primario" to="/noc">Modo NOC</Link>
          </div>
        }
      />
      {mensaje && <div className={`aviso ${mensaje.ok ? "ok" : "atencion"}`} style={{ marginBottom: 12 }}>{mensaje.texto}</div>}
      {cargando && !datos ? (
        <Cargando />
      ) : !datos?.enlaces.length ? (
        <Tarjeta>
          <Vacio titulo="Todavía no hay conexiones para dibujar">
            <p className="tenue" style={{ maxWidth: 560, margin: "0 auto" }}>
              Pulsa «Actualizar vecinos»: mufa lee por SNMP qué equipos ve cada uno. Hace falta que tengan LLDP o CDP
              activo (en MikroTik, el descubrimiento de vecinos) y SNMP configurado en mufa.
            </p>
          </Vacio>
        </Tarjeta>
      ) : (
        <Tarjeta sinRelleno>
          <DibujoMapa datos={datos} />
          <div className="mapa-pie">
            {Object.entries(COLORES)
              .filter(([e]) => e !== "desconocido")
              .map(([estado, c]) => (
                <span key={estado} className="mapa-leyenda">
                  <span className={estado === "fuera" ? "punto punto-fuera" : "punto"} style={{ background: c.color }} /> {c.texto}
                </span>
              ))}
            <span className="tenue crece" style={{ textAlign: "right" }}>
              Arrastra los equipos para ordenarlos · doble clic para abrir uno
              {datos.actualizado ? ` · vecinos leídos ${hace(datos.actualizado)}` : ""}
            </span>
          </div>
        </Tarjeta>
      )}
    </>
  );
}

// --- Modo NOC: pantalla completa para el televisor del NOC, se actualiza sola.

export function ModoNoc() {
  const [version, setVersion] = useState(0);
  const { datos: panel } = useDatos<Panel>(`/panel?v=${version}`);
  const { datos: mapa } = useDatos<DatosMapa>(`/mapa?v=${version}`);
  const [ahora, setAhora] = useState(new Date());

  useEffect(() => {
    const datos = window.setInterval(() => setVersion((v) => v + 1), 30_000);
    const reloj = window.setInterval(() => setAhora(new Date()), 1000);
    return () => {
      window.clearInterval(datos);
      window.clearInterval(reloj);
    };
  }, []);

  const caidos = panel?.caidos ?? [];
  return (
    <div className="noc">
      <header className="noc-cabeza">
        <div className="fila" style={{ gap: 10, alignItems: "center" }}>
          <img src="/favicon.svg" alt="" width={34} height={34} />
          <strong style={{ fontSize: 24 }}>mufa · NOC</strong>
        </div>
        <div className="noc-reloj">{ahora.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</div>
        <div className="fila" style={{ gap: 8 }}>
          <button className="boton chico" onClick={() => void document.documentElement.requestFullscreen?.()}>Pantalla completa</button>
          <Link className="boton chico" to="/mapa">Salir</Link>
        </div>
      </header>
      {!panel ? (
        <Cargando />
      ) : (
        <div className="noc-cuerpo">
          <div className="noc-cifras">
            <div className={`noc-cifra ${caidos.length ? "rojo" : "verde"}`}>
              <span>Caídos</span>
              <strong>{caidos.length}</strong>
            </div>
            <div className="noc-cifra">
              <span>En línea</span>
              <strong>{panel.en_linea}<small> / {panel.monitoreados}</small></strong>
            </div>
            <div className={`noc-cifra ${panel.respaldos_al_dia < panel.respaldables ? "naranja" : ""}`}>
              <span>Respaldos al día</span>
              <strong>{panel.respaldos_al_dia}<small> / {panel.respaldables}</small></strong>
            </div>
            <div className="noc-cifra">
              <span>Seguridad</span>
              <strong>{panel.puntaje_red ?? "—"}<small>{panel.puntaje_red !== null ? "/100" : ""}</small></strong>
            </div>
          </div>
          <div className="noc-paneles">
            <section className="noc-panel noc-mapa">
              {mapa && mapa.enlaces.length ? <DibujoMapa datos={mapa} compacto /> : <div className="tenue" style={{ padding: 24 }}>Sin mapa todavía: actualiza los vecinos en la página Mapa.</div>}
            </section>
            <section className="noc-panel">
              <h2>Caídos ahora</h2>
              {caidos.length === 0 ? (
                <div className="noc-todo-bien">Todo en línea</div>
              ) : (
                caidos.map((c) => (
                  <div key={c.equipo_id} className="noc-caido">
                    <strong>{c.nombre}</strong>
                    <span>{c.ultimo_en_linea ? `caído ${hace(c.ultimo_en_linea)}` : "sin datos"}{c.alcanzable ? " · responde ping" : ""}</span>
                  </div>
                ))
              )}
              <h2 style={{ marginTop: 18 }}>Últimos avisos</h2>
              {(mapa?.eventos ?? []).slice(0, 8).map((e, i) => (
                <div key={i} className="noc-evento">
                  <span className="tenue">{new Date(e.cuando).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}</span>
                  <span>{e.titulo}: <strong>{e.objeto}</strong></span>
                </div>
              ))}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
