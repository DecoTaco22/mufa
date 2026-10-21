import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api, textoDeError, transmitir } from "../api";
import { BotonCopiar, Encabezado, MensajeError, Segmentado, Tarjeta } from "../componentes/ui";
import type { RespuestaDonde, SalidaHerramienta } from "../tipos";
import { calcularSubred, ipv4ANumero, mascaraAPrefijo, mascaraDePrefijo, type Subred } from "../subredes";

type Prueba = "ping" | "traceroute" | "mtr" | "dns" | "puerto";

export function Herramientas() {
  return (
    <>
      <Encabezado titulo="Herramientas" subtitulo="Corren desde el servidor de mufa, dentro de tu red de gestión. Solo consultan: no cambian nada en los equipos." />
      <Terminal />
      <div className="grilla" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
        <Calculadora />
        <DondeEsta />
      </div>
    </>
  );
}

// --- Terminal

type Linea = { texto: string; tipo?: "prompt" | "ok" | "error" | "nota" };
const FIN = "\x1e";
const PUERTOS_COMUNES: [number, string][] = [
  [22, "SSH"], [23, "Telnet"], [80, "HTTP"], [443, "HTTPS"], [8291, "Winbox"], [8728, "API"], [8729, "API-SSL"], [3389, "RDP"],
];

function Terminal() {
  const [prueba, setPrueba] = useState<Prueba>("ping");
  const [destino, setDestino] = useState("");
  const [cantidad, setCantidad] = useState("4");
  const [puerto, setPuerto] = useState("22");
  const [lineas, setLineas] = useState<Linea[]>([
    { texto: "mufa · herramientas de red. Elige una prueba, escribe el destino y pulsa Enter.", tipo: "nota" },
  ]);
  const [corriendo, setCorriendo] = useState(false);
  const corte = useRef<AbortController | null>(null);
  const pantalla = useRef<HTMLDivElement>(null);
  const pegadoAbajo = useRef(true);

  useEffect(() => {
    const el = pantalla.current;
    if (el && pegadoAbajo.current) el.scrollTop = el.scrollHeight;
  }, [lineas]);
  useEffect(() => () => corte.current?.abort(), []);

  const agregar = (...nuevas: Linea[]) => setLineas((l) => [...l, ...nuevas].slice(-2000));

  function comandoVisible(): string {
    const d = destino.trim();
    if (prueba === "ping") return `ping ${cantidad === "continuo" ? "-t " : `-c ${cantidad} `}${d}`;
    if (prueba === "traceroute") return `traceroute ${d}`;
    if (prueba === "mtr") return `mtr --report ${d}`;
    if (prueba === "dns") return `nslookup ${d}`;
    return `tcping ${d} ${puerto}`;
  }

  async function ejecutar() {
    const d = destino.trim();
    if (!d || corriendo) return;
    pegadoAbajo.current = true;
    agregar({ texto: comandoVisible(), tipo: "prompt" });
    setCorriendo(true);
    const control = new AbortController();
    corte.current = control;
    try {
      if (prueba === "ping" || prueba === "traceroute") {
        let resto = "";
        let codigo: string | null = null;
        await transmitir(
          `/herramientas/${prueba}/en-vivo`,
          { destino: d, cantidad: cantidad === "continuo" ? null : Number(cantidad) },
          (pedazo) => {
            let texto = resto + pedazo;
            const fin = texto.indexOf(FIN);
            if (fin !== -1) {
              codigo = texto.slice(fin + 1).trim();
              texto = texto.slice(0, fin);
            }
            const partes = texto.replace(/\r/g, "").split("\n");
            resto = fin === -1 ? (partes.pop() ?? "") : "";
            const llenas = partes.filter((p, i) => p.trim() || (i > 0 && partes[i - 1]?.trim()));
            if (llenas.length) agregar(...llenas.map((t) => ({ texto: t })));
          },
          control.signal,
        );
        if (resto.trim()) agregar({ texto: resto });
        if (codigo !== null) {
          agregar(codigo === "0" ? { texto: "✓ terminado", tipo: "ok" } : { texto: `✗ terminó con código ${codigo}`, tipo: "error" });
        }
      } else {
        if (prueba === "mtr") agregar({ texto: "Buscando los saltos y midiendo cada uno (10 rondas, unos 20 segundos)…", tipo: "nota" });
        const salida = await api<SalidaHerramienta>(`/herramientas/${prueba}`, {
          metodo: "POST",
          cuerpo: { destino: d, puerto: prueba === "puerto" ? Number(puerto) : null },
        });
        agregar(...(salida.texto || "(sin salida)").split("\n").map((t) => ({ texto: t, tipo: salida.ok ? ("ok" as const) : ("error" as const) })));
      }
    } catch (error) {
      if (control.signal.aborted) agregar({ texto: "^C detenido", tipo: "nota" });
      else agregar({ texto: textoDeError(error), tipo: "error" });
    } finally {
      setCorriendo(false);
      corte.current = null;
    }
  }

  const texto = lineas.map((l) => (l.tipo === "prompt" ? `$ ${l.texto}` : l.texto)).join("\n");

  return (
    <section className="terminal-caja">
      <div className="terminal-barra">
        <Segmentado
          etiqueta="Herramienta"
          valor={prueba}
          onCambio={(p) => !corriendo && setPrueba(p)}
          opciones={[
            { valor: "ping", texto: "Ping" },
            { valor: "traceroute", texto: "Traceroute" },
            { valor: "mtr", texto: "MTR" },
            { valor: "dns", texto: "DNS" },
            { valor: "puerto", texto: "Puerto TCP" },
          ]}
        />
        <form className="terminal-form" onSubmit={(e) => { e.preventDefault(); void ejecutar(); }}>
          <input
            className="mono crece"
            value={destino}
            onChange={(e) => setDestino(e.target.value)}
            placeholder={prueba === "dns" ? "mikrotik.com o 1.1.1.1" : "10.20.4.1 o un nombre"}
            aria-label="Destino"
            disabled={corriendo}
            autoComplete="off"
            spellCheck={false}
          />
          {prueba === "ping" && (
            <select value={cantidad} onChange={(e) => setCantidad(e.target.value)} disabled={corriendo} aria-label="Cantidad de paquetes">
              <option value="4">4 paquetes</option>
              <option value="10">10 paquetes</option>
              <option value="100">100 paquetes</option>
              <option value="continuo">Continuo</option>
            </select>
          )}
          {prueba === "puerto" && (
            <select value={puerto} onChange={(e) => setPuerto(e.target.value)} disabled={corriendo} aria-label="Puerto">
              {PUERTOS_COMUNES.map(([n, nombre]) => <option key={n} value={n}>{n} · {nombre}</option>)}
            </select>
          )}
          {corriendo ? (
            <button type="button" className="boton peligro" onClick={() => corte.current?.abort()} disabled={prueba === "dns" || prueba === "puerto"}>Detener</button>
          ) : (
            <button type="submit" className="boton primario" disabled={!destino.trim()}>Ejecutar</button>
          )}
        </form>
      </div>
      <div className="terminal">
        <div className="terminal-titulo">
          <span className="semaforo" aria-hidden="true"><i /><i /><i /></span>
          <span className="mono">mufa — {corriendo ? comandoVisible() : "listo"}</span>
          <span className="terminal-acciones">
            <BotonCopiar texto={texto} />
            <button className="boton-texto" onClick={() => setLineas([])} disabled={corriendo}>Limpiar</button>
          </span>
        </div>
        <div
          className="terminal-pantalla mono"
          ref={pantalla}
          onScroll={(e) => {
            const el = e.currentTarget;
            pegadoAbajo.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
          }}
          role="log"
          aria-live="polite"
        >
          {lineas.map((l, i) => (
            <div key={i} className={`t-linea ${l.tipo ?? ""}`}>
              {l.tipo === "prompt" && <span className="t-prompt">mufa $ </span>}
              {l.texto || " "}
            </div>
          ))}
          <div className="t-linea">
            {!corriendo && <span className="t-prompt">mufa $ </span>}
            <span className={corriendo ? "t-cursor corriendo" : "t-cursor"} />
          </div>
        </div>
      </div>
    </section>
  );
}

// --- Calculadora

type Modo = "mascara" | "subred";

/** "/24", "24", "255.255.255.0" o una wildcard "0.0.0.255" → largo del prefijo. */
function leerPrefijo(texto: string): number | null {
  const t = texto.trim().replace(/^\//, "");
  if (/^\d{1,2}$/.test(t)) {
    const n = Number(t);
    return n <= 32 ? n : null;
  }
  try {
    return mascaraAPrefijo(t);
  } catch {
    try {
      return mascaraAPrefijo(numeroInvertido(t));
    } catch {
      return null;
    }
  }
}

function numeroInvertido(wildcard: string): string {
  const n = 2 ** 32 - 1 - ipv4ANumero(wildcard);
  return [24, 16, 8, 0].map((c) => Math.floor(n / 2 ** c) % 256).join(".");
}

function Calculadora() {
  const [modo, setModo] = useState<Modo>("mascara");
  return (
    <Tarjeta titulo="Calculadora IP">
      <div className="pila">
        <Segmentado<Modo>
          etiqueta="Qué calcular"
          valor={modo}
          onCambio={setModo}
          opciones={[
            { valor: "mascara", texto: "Prefijo ↔ máscara" },
            { valor: "subred", texto: "Subred" },
          ]}
        />
        {modo === "mascara" ? <PrefijoMascara /> : <CalculadoraSubred />}
      </div>
    </Tarjeta>
  );
}

function PrefijoMascara() {
  const [entrada, setEntrada] = useState("/24");
  const bits = leerPrefijo(entrada);
  const datos = bits === null ? null : mascaraDePrefijo(bits);
  return (
    <>
      <input
        className="mono entrada-grande"
        value={entrada}
        onChange={(e) => setEntrada(e.target.value)}
        placeholder="/24, 255.255.255.0 o 0.0.0.255"
        aria-label="Prefijo, máscara o wildcard"
        spellCheck={false}
      />
      {entrada.trim() && datos === null && <div className="tenue">Escribe un prefijo (/0 a /32), una máscara o una wildcard.</div>}
      {datos && bits !== null && (
        <div className="cifras-mascara">
          <Dato etiqueta="Prefijo" valor={`/${bits}`} />
          <Dato etiqueta="Máscara" valor={datos.mascara} destacado />
          <Dato etiqueta="Wildcard" valor={datos.comodin} />
          <Dato etiqueta="Hosts utilizables" valor={datos.hosts.toLocaleString("es")} />
          <Dato etiqueta="Direcciones" valor={datos.total.toLocaleString("es")} />
        </div>
      )}
      <div className="tabla-prefijos" role="group" aria-label="Prefijos comunes">
        {[8, 16, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32].map((n) => (
          <button key={n} type="button" className={n === bits ? "activo" : ""} onClick={() => setEntrada(`/${n}`)}>
            <strong>/{n}</strong>
            <span className="mono">{mascaraDePrefijo(n).mascara}</span>
          </button>
        ))}
      </div>
    </>
  );
}

function Dato(props: { etiqueta: string; valor: string; destacado?: boolean }) {
  return (
    <div className={props.destacado ? "dato-calc destacado" : "dato-calc"}>
      <span>{props.etiqueta}</span>
      <strong className="mono">{props.valor}</strong>
      <BotonCopiar texto={props.valor} />
    </div>
  );
}

function CalculadoraSubred() {
  const [entrada, setEntrada] = useState("192.168.10.0/26");
  let subred: Subred | null = null;
  let error: string | null = null;
  try {
    subred = calcularSubred(entrada);
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }
  return (
    <>
      <input className="mono entrada-grande" value={entrada} onChange={(x) => setEntrada(x.target.value)} aria-label="Red o IP con prefijo" spellCheck={false} />
      <span className="tenue" style={{ fontSize: 12 }}>IPv4 o IPv6: 10.0.0.1/30, 192.168.1.0 255.255.255.0, 2001:db8::/48</span>
      {error && entrada.trim() && <div className="tenue">{error}</div>}
      {subred && (
        <table>
          <tbody>
            {subred.filas.map(([etiqueta, valor]) => (
              <tr key={etiqueta}><td className="tenue" style={{ width: "42%" }}>{etiqueta}</td><td className="mono">{valor}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

// --- ¿Dónde está?

function DondeEsta() {
  const [consulta, setConsulta] = useState("");
  const [respuesta, setRespuesta] = useState<RespuestaDonde | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buscando, setBuscando] = useState(false);

  async function buscar() {
    setBuscando(true);
    setError(null);
    try {
      setRespuesta(await api<RespuestaDonde>(`/donde?q=${encodeURIComponent(consulta.trim())}`));
    } catch (err) {
      setError(textoDeError(err));
      setRespuesta(null);
    } finally {
      setBuscando(false);
    }
  }

  const fuentes = { arp: "Tabla ARP", bridge: "Aprendida en el puerto", ipam: "Documentada en el IPAM" };
  return (
    <Tarjeta titulo="¿Dónde está?">
      <div className="pila">
        <p className="tenue" style={{ margin: 0 }}>Una IP o una MAC: mufa busca en las tablas ARP y de bridge de tus equipos (solo lectura) y te dice en cuál y en qué puerto está.</p>
        <form className="fila" onSubmit={(x) => { x.preventDefault(); void buscar(); }}>
          <input className="crece mono" value={consulta} onChange={(x) => setConsulta(x.target.value)} placeholder="10.20.4.17 o 4C:5E:0C:12:34:56" aria-label="IP o MAC" required />
          <button className="boton primario" type="submit" disabled={buscando}>{buscando ? "Buscando…" : "Buscar"}</button>
        </form>
        {buscando && <span className="barra-indeterminada" />}
        <MensajeError mensaje={error} />
        {respuesta && (
          respuesta.resultados.length === 0 ? (
            <div className="aviso info">No aparece en ningún equipo. Puede estar apagado o no haber pasado tráfico hace rato.</div>
          ) : (
            <div className="tabla-caja">
              <table>
                <thead><tr><th>Equipo</th><th>Interfaz</th><th>IP / MAC</th><th>Cómo</th></tr></thead>
                <tbody>
                  {respuesta.resultados.map((r, i) => (
                    <tr key={i}>
                      <td><Link to={`/equipos/${r.equipo_id}`}>{r.equipo}</Link></td>
                      <td style={{ fontWeight: 500 }}>{r.interfaz || "—"}</td>
                      <td className="mono">{r.ip || r.mac}{r.ip && r.mac ? <div className="tenue">{r.mac}</div> : null}</td>
                      <td className="tenue">{fuentes[r.fuente]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
        {respuesta && respuesta.sin_respuesta.length > 0 && (
          <div className="tenue" style={{ fontSize: 12 }}>No respondieron: {respuesta.sin_respuesta.map((s) => s.split(":")[0]).join(", ")}</div>
        )}
      </div>
    </Tarjeta>
  );
}
