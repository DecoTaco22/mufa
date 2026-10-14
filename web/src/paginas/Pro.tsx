import { Icono, type NombreIcono } from "../componentes/Icono";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router";
import { Cargando, Encabezado } from "../componentes/ui";
import type { Licencia } from "../tipos";
import { useDatos } from "../util";
import { Avisos } from "./Avisos";
import { Capacidad } from "./Capacidad";
import { Informes } from "./Informes";
import { OltGpon } from "./Olt";

// El sitio redirige /apoyar, /fundador y /pro a Ko-fi; así la app no cambia si cambia la cuenta.
export const SITIO = "https://mufa.pages.dev";

type Modulo = {
  titulo: string;
  frase: string;
  resumen: string;
  color: string;
  vista: () => ReactNode;
  beneficios: { icono: NombreIcono; titulo: string; texto: string }[];
  pasos: string[];
  para: string;
};

export const MODULOS: Record<string, Modulo> = {
  avisos: {
    titulo: "Avisos para tu equipo",
    frase: "Que la alerta le llegue a quien la tiene que atender.",
    resumen:
      "En el plan gratis las alertas llegan a un chat. Con Pro, tu bot de Telegram avisa a cada persona del NOC según quién está de turno, con «Lo tomo yo» y escalamiento a los supervisores.",
    color: "#0a84ff",
    vista: VistaAvisos,
    beneficios: [
      { icono: "usuarios", titulo: "Todo tu equipo", texto: "Contactos y grupos de Telegram ilimitados. Cada técnico se une con un enlace del bot." },
      { icono: "reloj", titulo: "Escalamiento", texto: "Si nadie toma la alerta en 10 minutos, se avisa al supervisor. Nada queda sin dueño." },
      { icono: "luna", titulo: "Guardias", texto: "La alerta de las 3 a. m. le llega a quien está de turno, no a todos." },
      { icono: "mano", titulo: "«Lo tomo yo»", texto: "Un botón en Telegram para que el resto sepa que ya hay alguien trabajando en la falla." },
    ],
    pasos: ["Eliges el bot de uno de tus canales de Telegram.", "Cada técnico abre su enlace y queda conectado.", "Defines guardias y supervisores. Listo."],
    para: "ISPs con más de un técnico, o con clientes corporativos que no toleran una caída sin atender.",
  },
  informes: {
    titulo: "Informes en PDF",
    frase: "Demuestra con números lo bien que funciona tu red.",
    resumen:
      "Un informe mensual con tu logo, listo para mandar a tus clientes corporativos, a tu jefe o a tu socio: disponibilidad, caídas, saturación y seguridad, sin armar nada en Excel.",
    color: "#bf5af2",
    vista: VistaInforme,
    beneficios: [
      { icono: "grafica", titulo: "SLA del mes", texto: "Disponibilidad de cada equipo y enlace, comparada con el mes anterior." },
      { icono: "rayo", titulo: "Caídas explicadas", texto: "Cuándo, cuánto duraron y qué se hizo, en una línea de tiempo clara." },
      { icono: "fuego", titulo: "Saturación", texto: "Interfaces al límite y la tendencia de consumo de cada sitio." },
      { icono: "escudo", titulo: "Seguridad", texto: "Puntaje de la red y cómo mejoró: argumento perfecto para renovar contratos." },
    ],
    pasos: ["Subes tu logo.", "Eliges equipos o clientes y la frecuencia.", "mufa lo genera y lo manda por correo el día 1."],
    para: "Quien vende enlaces dedicados o administra redes de terceros y tiene que rendir cuentas.",
  },
  capacidad: {
    titulo: "Predicción de capacidad",
    frase: "Enterarte de que un enlace se queda corto antes que tus clientes.",
    resumen:
      "mufa guarda un año de tráfico y calcula la tendencia de cada interfaz: te avisa cuántas semanas le quedan a un uplink antes de saturarse, para que compres capacidad a tiempo.",
    color: "#30d158",
    vista: VistaCapacidad,
    beneficios: [
      { icono: "prediccion", titulo: "Fecha de saturación", texto: "«Este uplink llega al 80 % en 6 semanas a este ritmo.»" },
      { icono: "calendario", titulo: "Un año de historial", texto: "Compara meses, temporadas y el antes y después de cada cambio." },
      { icono: "reloj", titulo: "Horas pico", texto: "Por interfaz y por sitio, para planificar mantenimientos sin afectar a nadie." },
      { icono: "barras", titulo: "Ranking", texto: "Los enlaces más cargados de la red, ordenados por urgencia." },
    ],
    pasos: ["Activas Pro: el historial pasa de 7 días a 1 año.", "Marcas las interfaces importantes.", "Recibes el aviso con semanas de anticipación."],
    para: "ISPs que crecen y necesitan decidir cuándo y dónde invertir en capacidad.",
  },
  olt: {
    titulo: "OLT GPON",
    frase: "Tus ONU, su señal y sus caídas, junto al resto de la red.",
    resumen:
      "Lee por SNMP tus OLT Huawei y ZTE: el estado de cada ONU por puerto PON, su potencia óptica y las caídas masivas. Sabrás si es un corte de fibra o una ONU antes de que el cliente llame.",
    color: "#ff9f0a",
    vista: VistaOlt,
    beneficios: [
      { icono: "enchufe", titulo: "Cada ONU", texto: "Estado, potencia RX/TX y distancia, por puerto PON." },
      { icono: "tendencia", titulo: "Señal baja", texto: "Aviso cuando una ONU se acerca al límite, antes de que se caiga." },
      { icono: "tijera", titulo: "Corte de fibra", texto: "Si caen todas las ONU de un puerto a la vez, te lo dice así: corte, no falla de equipo." },
      { icono: "candado", titulo: "Solo lectura", texto: "Como todo mufa: consulta la OLT, nunca le cambia nada." },
    ],
    pasos: ["Agregas la OLT con SNMP.", "mufa descubre los puertos PON y las ONU.", "Ves la señal de cada cliente y recibes avisos."],
    para: "ISPs de fibra con OLT Huawei MA5600T/MA5800 o ZTE C300/C320.",
  },
};

// Los módulos que ya existen: con un plan que los incluye se muestran en vez de su presentación.
const DISPONIBLES: Record<string, () => ReactNode> = { avisos: Avisos, capacidad: Capacidad, informes: Informes, olt: OltGpon };

export function PaginaPro() {
  const { modulo = "" } = useParams();
  const { datos: licencia, cargando } = useDatos<Licencia>("/licencia");
  const m = MODULOS[modulo];
  if (!m) return <Encabezado titulo="mufa Pro" />;
  const Modulo = DISPONIBLES[modulo];
  if (Modulo && cargando && !licencia) return <Cargando />;
  if (Modulo && licencia?.funciones.includes(modulo)) return <Modulo />;
  const Vista = m.vista;
  return (
    <div className="pro-pagina" style={{ ["--pro" as string]: m.color }}>
      <section className="pro-hero">
        <div className="pro-hero-texto">
          <span className="insignia-pro">Pro</span>
          <h1>{m.titulo}</h1>
          <p className="pro-frase">{m.frase}</p>
          <p className="tenue">{m.resumen}</p>
          <div className="fila">
            <a className="boton primario" href={`${SITIO}/pro`} target="_blank" rel="noreferrer">Obtener Pro</a>
            <Link className="boton" to="/planes">Ver planes</Link>
          </div>
          <span className="tenue" style={{ fontSize: 12 }}>
            {Modulo ? "Ya disponible en Pro." : "En camino: con Pro lo recibes apenas sale."} La licencia se instala en Ajustes › Plan.
          </span>
        </div>
        <div className="pro-vista" aria-hidden="true"><Vista /></div>
      </section>

      <section className="pro-beneficios">
        {m.beneficios.map((b, i) => (
          <article key={b.titulo} className="pro-beneficio" style={{ animationDelay: `${i * 60}ms` }}>
            <span className="pro-icono"><Icono nombre={b.icono} tamano={20} /></span>
            <h3>{b.titulo}</h3>
            <p className="tenue">{b.texto}</p>
          </article>
        ))}
      </section>

      <section className="pro-dos">
        <div className="pro-bloque">
          <h2>Cómo funciona</h2>
          <ol className="pro-pasos">{m.pasos.map((p) => <li key={p}>{p}</li>)}</ol>
        </div>
        <div className="pro-bloque">
          <h2>Para quién es</h2>
          <p className="tenue">{m.para}</p>
          <h2 style={{ marginTop: 18 }}>Incluido en Pro</h2>
          <div className="pro-otros">
            {Object.entries(MODULOS).filter(([clave]) => clave !== modulo).map(([clave, otro]) => (
              <Link key={clave} to={`/pro/${clave}`} style={{ ["--pro" as string]: otro.color }}>{otro.titulo}</Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

/** Resumen visual de Pro para la página de planes. */
export function ResumenPro() {
  return (
    <section className="pro-resumen">
      <div>
        <span className="insignia-pro">Pro</span>
        <h2>Todo lo del plan gratis, para un ISP que no puede perderse una falla.</h2>
        <p className="tenue">Equipos y usuarios ilimitados, un año de historial y cuatro módulos pensados para operar en equipo.</p>
      </div>
      <div className="pro-resumen-grilla">
        {Object.entries(MODULOS).map(([clave, m]) => {
          const Vista = m.vista;
          return (
            <Link key={clave} to={`/pro/${clave}`} className="pro-tarjeta" style={{ ["--pro" as string]: m.color }}>
              <div className="pro-tarjeta-vista" aria-hidden="true"><Vista /></div>
              <strong>{m.titulo}</strong>
              <span className="tenue">{m.frase}</span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

// --- Vistas previas: maquetas de la interfaz, dibujadas con HTML y SVG.

function VistaAvisos() {
  return (
    <div className="maqueta chat">
      <div className="chat-cabeza"><span className="chat-avatar">m</span><div><strong>mufa NOC</strong><span>bot · 6 miembros</span></div></div>
      <div className="burbuja alerta">
        <strong>🔴 Caído: CCR Nodo Norte</strong>
        <span>10.20.4.1 · sin respuesta hace 2 min</span>
        <div className="burbuja-botones"><span>🙋 Lo tomo yo</span></div>
      </div>
      <div className="burbuja sistema">Ana tomó la alerta · 02:14</div>
      <div className="burbuja ok"><strong>🟢 Recuperado: CCR Nodo Norte</strong><span>Estuvo caído 7 min</span></div>
    </div>
  );
}

function VistaInforme() {
  return (
    <div className="maqueta papel">
      <div className="papel-cabeza"><span className="papel-logo">TU LOGO</span><span>Informe de septiembre</span></div>
      <div className="papel-cifras">
        <div><strong>99,97 %</strong><span>disponibilidad</span></div>
        <div><strong>3</strong><span>caídas</span></div>
        <div><strong>86</strong><span>seguridad</span></div>
      </div>
      <svg viewBox="0 0 200 60" className="papel-grafica">
        <polyline points="0,40 20,35 40,38 60,25 80,30 100,18 120,22 140,12 160,16 180,8 200,10" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />
        <polyline points="0,40 20,35 40,38 60,25 80,30 100,18 120,22 140,12 160,16 180,8 200,10 200,60 0,60" fill="currentColor" opacity=".12" />
      </svg>
      <div className="papel-lineas"><i /><i /><i style={{ width: "60%" }} /></div>
    </div>
  );
}

function VistaCapacidad() {
  return (
    <div className="maqueta grafica">
      <div className="grafica-cabeza"><strong>Uplink Nodo Norte · sfp1</strong><span className="pill medio">Satura en 6 semanas</span></div>
      <svg viewBox="0 0 240 110">
        <line x1="0" y1="22" x2="240" y2="22" stroke="#ff453a" strokeDasharray="4 4" opacity=".7" />
        <text x="4" y="17" fill="#ff6961" fontSize="9">80 % de 1 Gbps</text>
        <polyline points="0,95 20,90 40,92 60,82 80,80 100,72 120,70 140,60" fill="none" stroke="#30d158" strokeWidth="2.5" strokeLinejoin="round" />
        <polyline points="140,60 165,48 190,38 215,27 240,18" fill="none" stroke="#30d158" strokeWidth="2.5" strokeDasharray="5 4" opacity=".7" />
        <circle cx="222" cy="22" r="4" fill="#ff453a" />
        <text x="150" y="104" fill="currentColor" opacity=".5" fontSize="9">hoy</text>
        <text x="200" y="104" fill="currentColor" opacity=".5" fontSize="9">+6 sem</text>
      </svg>
    </div>
  );
}

function VistaOlt() {
  const onus = [
    ["0/1/3:12", "-18,4", "ok"], ["0/1/3:13", "-21,9", "ok"], ["0/1/3:14", "-27,6", "baja"], ["0/1/3:15", "—", "caida"], ["0/1/3:16", "-19,1", "ok"],
  ];
  return (
    <div className="maqueta olt">
      <div className="grafica-cabeza"><strong>OLT Centro · PON 0/1/3</strong><span>32 ONU</span></div>
      {onus.map(([onu, rx, estado]) => (
        <div key={onu} className={`olt-fila ${estado}`}>
          <span className="mono">{onu}</span>
          <span className="olt-barra"><i style={{ width: estado === "caida" ? "0%" : estado === "baja" ? "25%" : "70%" }} /></span>
          <span className="mono">{rx} dBm</span>
        </div>
      ))}
    </div>
  );
}
