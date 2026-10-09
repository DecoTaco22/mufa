import { Icono } from "../componentes/Icono";
import { useEffect, useMemo, useRef, useState } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal as XTerm } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { Campo, Formulario, Modal, Segmentado } from "../componentes/ui";
import type { Equipo } from "../tipos";
import { useDatos } from "../util";

type Modo = "ssh" | "telnet" | "serial";

type Apertura = {
  modo: Modo;
  equipo_id?: number;
  host?: string;
  puerto?: number | null;
  usuario?: string;
  password?: string | null;
  puerto_serie?: string;
  baudios?: number;
  bits?: number;
  paridad?: string;
  parada?: number;
};

type PreguntaClave = {
  tipo: string;
  huella: string;
  anterior: { tipo: string; huella: string } | null;
  puede_reemplazar: boolean;
};

type Sesion = { id: number; titulo: string; apertura: Apertura; estado: "conectando" | "abierta" | "cerrada" | "error" };

const TEMA = {
  background: "#0b0b0d",
  foreground: "#e5e5ea",
  cursor: "#0a84ff",
  cursorAccent: "#0b0b0d",
  selectionBackground: "rgba(10, 132, 255, 0.35)",
  black: "#1c1c1e", red: "#ff453a", green: "#30d158", yellow: "#ffd60a",
  blue: "#0a84ff", magenta: "#bf5af2", cyan: "#64d2ff", white: "#e5e5ea",
  brightBlack: "#636366", brightRed: "#ff6961", brightGreen: "#4ae17a", brightYellow: "#ffe066",
  brightBlue: "#409cff", brightMagenta: "#da8fff", brightCyan: "#8be4ff", brightWhite: "#ffffff",
};

let siguienteId = 1;

export function Terminal() {
  const { datos: equipos } = useDatos<Equipo[]>("/equipos");
  const [sesiones, setSesiones] = useState<Sesion[]>([]);
  const [activa, setActiva] = useState<number | null>(null);
  const [nueva, setNueva] = useState<{ modo: Modo; equipo?: Equipo } | null>(null);
  const [busqueda, setBusqueda] = useState("");

  const visibles = useMemo(() => {
    const t = busqueda.trim().toLowerCase();
    return (equipos ?? []).filter((e) => !t || e.nombre.toLowerCase().includes(t) || e.ip_gestion.includes(t));
  }, [equipos, busqueda]);

  function abrir(titulo: string, apertura: Apertura) {
    const id = siguienteId++;
    setSesiones((s) => [...s, { id, titulo, apertura, estado: "conectando" }]);
    setActiva(id);
  }

  function cerrar(id: number) {
    setSesiones((s) => {
      const quedan = s.filter((x) => x.id !== id);
      if (activa === id) setActiva(quedan.at(-1)?.id ?? null);
      return quedan;
    });
  }

  const cambiarEstado = (id: number, estado: Sesion["estado"], titulo?: string) =>
    setSesiones((s) => s.map((x) => (x.id === id ? { ...x, estado, titulo: titulo ?? x.titulo } : x)));

  return (
    <div className="term-app">
      <aside className="term-lateral">
        <div className="term-lateral-cabeza">
          <h1>Terminal</h1>
          <button className="boton primario chico" onClick={() => setNueva({ modo: "ssh" })}>+ Nueva</button>
        </div>
        <input className="term-busqueda" placeholder="Buscar equipo" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} aria-label="Buscar equipo" />
        <div className="term-grupo">Equipos</div>
        <div className="term-lista">
          {visibles.map((e) => (
            <div key={e.id} className="term-equipo">
              <button
                className="term-equipo-principal"
                title={`SSH a ${e.nombre}`}
                onDoubleClick={() => abrir(e.nombre, { modo: "ssh", equipo_id: e.id })}
                onClick={() => setNueva({ modo: "ssh", equipo: e })}
              >
                <span className="term-icono" aria-hidden="true">{e.marca === "mikrotik" ? "M" : e.marca.slice(0, 1).toUpperCase()}</span>
                <span className="term-equipo-texto">
                  <strong>{e.nombre}</strong>
                  <span className="mono">{e.ip_gestion}</span>
                </span>
              </button>
              <button className="term-rapido" title="Conectar por SSH con las credenciales guardadas" onClick={() => abrir(e.nombre, { modo: "ssh", equipo_id: e.id })}>SSH</button>
            </div>
          ))}
          {equipos && !visibles.length && <p className="tenue" style={{ fontSize: 13, padding: "0 10px" }}>Sin resultados.</p>}
        </div>
        <div className="term-grupo">Otras conexiones</div>
        <div className="term-lista">
          <button className="term-otra" onClick={() => setNueva({ modo: "ssh" })}><Icono nombre="terminal" /> SSH a una IP</button>
          <button className="term-otra" onClick={() => setNueva({ modo: "telnet" })}><Icono nombre="intercambio" /> Telnet</button>
          <button className="term-otra" onClick={() => setNueva({ modo: "serial" })}><Icono nombre="cable" /> Puerto serie</button>
        </div>
      </aside>

      <section className="term-principal">
        {sesiones.length > 0 && (
          <div className="term-pestanas" role="tablist">
            {sesiones.map((s) => (
              <div key={s.id} role="tab" aria-selected={s.id === activa} className={s.id === activa ? "term-pestana activa" : "term-pestana"} onClick={() => setActiva(s.id)}>
                <span className={`punto ${s.estado}`} aria-hidden="true" />
                <span className="term-pestana-texto">{s.titulo}</span>
                <button aria-label={`Cerrar ${s.titulo}`} onClick={(e) => { e.stopPropagation(); cerrar(s.id); }}>×</button>
              </div>
            ))}
            <button className="term-mas" onClick={() => setNueva({ modo: "ssh" })} aria-label="Nueva conexión"><Icono nombre="mas" /></button>
          </div>
        )}
        <div className="term-escenario">
          {sesiones.length === 0 && (
            <div className="term-vacio">
              <div className="term-vacio-icono" aria-hidden="true"><Icono nombre="terminal" tamano={34} /></div>
              <h2>Conéctate a tus equipos</h2>
              <p className="tenue">SSH, Telnet o consola serie, sin salir de mufa. Elige un equipo de la izquierda: con un clic usa las credenciales que ya guardaste.</p>
              <div className="fila" style={{ justifyContent: "center" }}>
                <button className="boton primario" onClick={() => setNueva({ modo: "ssh" })}>Nueva conexión</button>
                <button className="boton" onClick={() => setNueva({ modo: "serial" })}>Puerto serie</button>
              </div>
              <p className="tenue" style={{ fontSize: 12, marginTop: 18 }}>
                Lo que escribas acá llega al equipo tal cual: es tu sesión. mufa por su cuenta nunca cambia nada en los equipos.
              </p>
            </div>
          )}
          {sesiones.map((s) => (
            <PantallaDeSesion key={s.id} sesion={s} visible={s.id === activa} alCambiar={(estado, titulo) => cambiarEstado(s.id, estado, titulo)} />
          ))}
        </div>
      </section>

      {nueva && (
        <NuevaConexion
          inicial={nueva}
          equipos={equipos ?? []}
          onCerrar={() => setNueva(null)}
          onAbrir={(titulo, apertura) => { setNueva(null); abrir(titulo, apertura); }}
        />
      )}
    </div>
  );
}

function PantallaDeSesion(props: { sesion: Sesion; visible: boolean; alCambiar: (estado: Sesion["estado"], titulo?: string) => void }) {
  const caja = useRef<HTMLDivElement>(null);
  const ajuste = useRef<FitAddon | null>(null);
  const xterm = useRef<XTerm | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const [pregunta, setPregunta] = useState<PreguntaClave | null>(null);
  const { alCambiar } = props;

  function responder(clave: "guardar" | "una_vez" | "reemplazar" | "cancelar") {
    socket.current?.send(JSON.stringify({ clave }));
    setPregunta(null);
    xterm.current?.focus();
  }

  useEffect(() => {
    const term = new XTerm({
      theme: TEMA,
      fontFamily: '"SF Mono", Menlo, Consolas, "Cascadia Mono", monospace',
      fontSize: 13,
      lineHeight: 1.25,
      cursorBlink: true,
      cursorStyle: "bar",
      scrollback: 5000,
      allowProposedApi: false,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(caja.current!);
    fit.fit();
    xterm.current = term;
    ajuste.current = fit;

    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/v1/terminal`);
    ws.binaryType = "arraybuffer";
    socket.current = ws;
    const codificador = new TextEncoder();
    let abierta = false;
    let fallo = false;

    term.writeln(`\x1b[90mConectando…\x1b[0m`);
    ws.onopen = () => ws.send(JSON.stringify({ ...props.sesion.apertura, columnas: term.cols, filas: term.rows }));
    ws.onmessage = (evento) => {
      if (typeof evento.data === "string") {
        const control = JSON.parse(evento.data) as { estado?: string; titulo?: string; error?: string; aviso?: string; confirmar_clave?: PreguntaClave };
        if (control.confirmar_clave) {
          setPregunta(control.confirmar_clave);
          return;
        }
        if (control.error) {
          term.writeln(`\r\n\x1b[31m✗ ${control.error}\x1b[0m`);
          fallo = true;
          alCambiar("error");
        } else if (control.estado === "abierta") {
          abierta = true;
          term.write("\x1b[1A\x1b[2K\r");
          if (control.aviso) term.writeln(`\x1b[33m⚠ ${control.aviso}\x1b[0m`);
          alCambiar("abierta", props.sesion.apertura.modo === "serial" ? control.titulo : undefined);
          term.focus();
        }
        return;
      }
      term.write(new Uint8Array(evento.data as ArrayBuffer));
    };
    ws.onclose = (evento) => {
      if (abierta) {
        term.writeln("\r\n\x1b[90m— Sesión terminada —\x1b[0m");
        alCambiar("cerrada");
      } else if (evento.code === 4401) {
        term.writeln("\r\n\x1b[31m✗ Tu usuario no tiene permiso para usar la terminal, o la sesión venció.\x1b[0m");
        alCambiar("error");
      } else if (!fallo) {
        term.writeln(`\r\n\x1b[31m✗ No se pudo abrir la sesión${evento.reason ? `: ${evento.reason}` : ""}.\x1b[0m`);
        alCambiar("error");
      }
    };
    const entrada = term.onData((datos) => ws.readyState === WebSocket.OPEN && abierta && ws.send(codificador.encode(datos)));
    const tamano = term.onResize(({ cols, rows }) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ columnas: cols, filas: rows })));
    const observador = new ResizeObserver(() => { try { fit.fit(); } catch { /* oculta */ } });
    observador.observe(caja.current!);

    return () => {
      observador.disconnect();
      entrada.dispose();
      tamano.dispose();
      ws.close();
      term.dispose();
    };
    // Una sesión se abre una sola vez: su apertura no cambia.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (props.visible) {
      requestAnimationFrame(() => {
        try { ajuste.current?.fit(); } catch { /* sin tamaño todavía */ }
        xterm.current?.focus();
      });
    }
  }, [props.visible]);

  return (
    <>
      <div className="term-pantalla" ref={caja} style={{ display: props.visible ? "block" : "none" }} />
      {props.visible && pregunta && (
        <div className="clave-capa" role="dialog" aria-modal="true" aria-label="Confirmar la clave del equipo">
          <div className={pregunta.anterior ? "clave-tarjeta peligro" : "clave-tarjeta"}>
            <div className="clave-icono" aria-hidden="true"><Icono nombre={pregunta.anterior ? "alerta" : "llave"} tamano={22} /></div>
            {pregunta.anterior ? (
              <>
                <h3>La clave de este equipo cambió</h3>
                <p>
                  Si reinstalaste el equipo o le cambiaste el firmware es normal. Si no, alguien podría estar
                  haciéndose pasar por él para robar tu contraseña. Ante la duda, cancela y verifica en el equipo.
                </p>
                <dl>
                  <dt>Antes</dt><dd className="mono">{pregunta.anterior.tipo}<br />{pregunta.anterior.huella}</dd>
                  <dt>Ahora</dt><dd className="mono">{pregunta.tipo}<br />{pregunta.huella}</dd>
                </dl>
                <div className="clave-botones">
                  <button className="boton" onClick={() => responder("cancelar")} autoFocus>Cancelar</button>
                  {pregunta.puede_reemplazar ? (
                    <button className="boton peligro" onClick={() => responder("reemplazar")}>Reemplazar la clave</button>
                  ) : (
                    <span className="tenue" style={{ fontSize: 12 }}>Solo un Ingeniero o Admin puede aceptar la clave nueva.</span>
                  )}
                </div>
              </>
            ) : (
              <>
                <h3>¿Confías en este equipo?</h3>
                <p>
                  Es la primera vez que mufa se conecta a él. Compara la huella con la del equipo
                  (en MikroTik: <span className="mono">/ip ssh print</span>; en Cisco: <span className="mono">show crypto key mypubkey</span>).
                </p>
                <dl>
                  <dt>Tipo</dt><dd className="mono">{pregunta.tipo}</dd>
                  <dt>Huella</dt><dd className="mono">{pregunta.huella}</dd>
                </dl>
                <div className="clave-botones">
                  <button className="boton" onClick={() => responder("cancelar")}>Cancelar</button>
                  <button className="boton" onClick={() => responder("una_vez")}>Solo esta vez</button>
                  <button className="boton primario" onClick={() => responder("guardar")} autoFocus>Confiar y guardar</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function NuevaConexion(props: {
  inicial: { modo: Modo; equipo?: Equipo };
  equipos: Equipo[];
  onCerrar: () => void;
  onAbrir: (titulo: string, apertura: Apertura) => void;
}) {
  const [modo, setModo] = useState<Modo>(props.inicial.modo);
  const [equipoId, setEquipoId] = useState(props.inicial.equipo ? String(props.inicial.equipo.id) : "");
  const [host, setHost] = useState("");
  const [puerto, setPuerto] = useState("");
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [puertoSerie, setPuertoSerie] = useState("");
  const [baudios, setBaudios] = useState("115200");
  const [formato, setFormato] = useState("8N1");
  const { datos: puertos, recargar: buscarPuertos, cargando: buscando } = useDatos<{ puerto: string; descripcion: string }[]>(modo === "serial" ? "/terminal/puertos-serie" : null);

  const equipo = props.equipos.find((e) => String(e.id) === equipoId);
  // La contraseña guardada es la del usuario del equipo: con otro usuario hay que escribirla.
  const otroUsuario = Boolean(equipo && usuario.trim() && usuario.trim() !== equipo.usuario_ssh);
  const usaGuardadas = equipo && modo === "ssh" && equipo.tiene_credenciales && !otroUsuario;
  const puertoElegido = puertoSerie || puertos?.[0]?.puerto || "";

  async function abrir() {
    if (modo === "serial") {
      if (!puertoElegido) throw new Error("No hay ningún puerto serie conectado.");
      const [bits, paridad, parada] = [Number(formato[0]), formato[1], Number(formato[2])];
      props.onAbrir(`${puertoElegido}`, { modo, puerto_serie: puertoElegido, baudios: Number(baudios), bits, paridad, parada });
      return;
    }
    const base: Apertura = { modo, puerto: puerto ? Number(puerto) : null, usuario: usuario.trim(), password: password || null };
    if (equipo) props.onAbrir(equipo.nombre, { ...base, equipo_id: equipo.id });
    else props.onAbrir(host.trim(), { ...base, host: host.trim() });
  }

  return (
    <Modal titulo="Nueva conexión" onCerrar={props.onCerrar}>
      <Formulario textoBoton="Conectar" onCancelar={props.onCerrar} onEnviar={abrir}>
        <Segmentado<Modo>
          etiqueta="Tipo de conexión"
          valor={modo}
          onCambio={setModo}
          opciones={[{ valor: "ssh", texto: "SSH" }, { valor: "telnet", texto: "Telnet" }, { valor: "serial", texto: "Puerto serie" }]}
        />
        {modo === "telnet" && <div className="aviso atencion">Telnet manda todo sin cifrar, contraseñas incluidas. Úsalo solo en una red de gestión o con equipos que no tienen SSH.</div>}
        {modo !== "serial" ? (
          <div className="formulario">
            <Campo etiqueta="Equipo">
              <select value={equipoId} onChange={(e) => setEquipoId(e.target.value)}>
                <option value="">Otra IP o nombre…</option>
                {props.equipos.map((e) => <option key={e.id} value={e.id}>{e.nombre} · {e.ip_gestion}</option>)}
              </select>
            </Campo>
            {!equipo && (
              <Campo etiqueta="Host">
                <input className="mono" value={host} onChange={(e) => setHost(e.target.value)} required placeholder="10.20.4.1" autoFocus />
              </Campo>
            )}
            <Campo etiqueta="Puerto" ayuda={modo === "ssh" ? (equipo?.acceso === "ssh" ? `Vacío = ${equipo.puerto_ssh}` : "Vacío = 22. Si tu SSH está en otro puerto, escríbelo") : "Vacío = 23"}>
              <input type="number" min={1} max={65535} value={puerto} onChange={(e) => setPuerto(e.target.value)} />
            </Campo>
            {modo === "ssh" && (
              <>
                <Campo etiqueta="Usuario" ayuda={usaGuardadas ? `Vacío = ${equipo.usuario_ssh}` : undefined}>
                  <input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="off" required={!usaGuardadas} />
                </Campo>
                <Campo etiqueta="Contraseña" ayuda={usaGuardadas ? `Vacío = la guardada de ${equipo.usuario_ssh}` : otroUsuario ? `Escríbela: la guardada es la de ${equipo?.usuario_ssh}` : undefined}>
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required={!usaGuardadas} />
                </Campo>
              </>
            )}
          </div>
        ) : (
          <div className="formulario">
            <Campo etiqueta="Puerto" ayuda={buscando ? "Buscando…" : puertos && !puertos.length ? "No hay cables serie conectados a esta computadora" : undefined}>
              <div className="fila" style={{ flexWrap: "nowrap" }}>
                <select value={puertoElegido} onChange={(e) => setPuertoSerie(e.target.value)} className="crece">
                  {puertos?.map((p) => <option key={p.puerto} value={p.puerto}>{p.puerto} · {p.descripcion}</option>)}
                </select>
                <button type="button" className="boton chico" onClick={() => buscarPuertos()} aria-label="Buscar puertos de nuevo"><Icono nombre="recargar" /></button>
              </div>
            </Campo>
            <Campo etiqueta="Velocidad">
              <select value={baudios} onChange={(e) => setBaudios(e.target.value)}>
                {[9600, 19200, 38400, 57600, 115200].map((b) => <option key={b} value={b}>{b} baudios</option>)}
              </select>
            </Campo>
            <Campo etiqueta="Formato" ayuda="MikroTik y Cisco: 8N1">
              <select value={formato} onChange={(e) => setFormato(e.target.value)}>
                {["8N1", "8E1", "8O1", "7E1", "8N2"].map((f) => <option key={f}>{f}</option>)}
              </select>
            </Campo>
          </div>
        )}
        <p className="tenue" style={{ margin: 0, fontSize: 12 }}>
          Es una sesión tuya: lo que escribas llega al equipo. mufa registra que la abriste y cuánto duró, no lo que escribes.
        </p>
      </Formulario>
    </Modal>
  );
}

