import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, textoDeError } from "../api";
import { FormularioEquipo } from "../componentes/FormularioEquipo";
import { TarjetaHallazgo } from "../componentes/TarjetaHallazgo";
import { NOMBRES_DE_ACCESO } from "../componentes/FormularioEquipo";
import { Campo, Cargando, Encabezado, ErrorOPro, MensajeError, EstadoEnLinea, Modal, Puntaje, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Auditoria, AuditoriaResumen, Dominio, Equipo, EstadoEquipo, Interfaz, Marca, Respaldo, ResultadoImportacion } from "../tipos";
import { bps, duracion, fecha, hace, puede, useDatos } from "../util";

type Pestana = "resumen" | "interfaces" | "hallazgos" | "respaldos" | "documentar" | "snmp";

export function EquipoDetalle() {
  const { id } = useParams();
  const { usuario } = useSesion();
  const navegar = useNavigate();
  const equipo = useDatos<Equipo>(`/equipos/${id}`);
  const { datos: marcas } = useDatos<Marca[]>("/marcas");
  const [pestana, setPestana] = useState<Pestana>("resumen");
  const [editando, setEditando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  if (equipo.cargando && !equipo.datos) return <Cargando />;
  if (!equipo.datos) return <MensajeError mensaje={equipo.error} />;
  const e = equipo.datos;
  const tecnico = puede(usuario?.rol, "usar_credenciales");
  const gestor = puede(usuario?.rol, "gestionar_equipos");
  const pestanas: Pestana[] = [
    "resumen",
    "interfaces",
    "hallazgos",
    "respaldos",
    ...(gestor ? (["documentar"] as Pestana[]) : []),
    ...(tecnico && e.snmp ? (["snmp"] as Pestana[]) : []),
  ];

  async function accion(nombre: string, hacer: () => Promise<string>) {
    setOcupado(nombre);
    setAviso(null);
    try {
      setAviso({ tipo: "ok", texto: await hacer() });
      equipo.recargar();
      setVersion((v) => v + 1);
    } catch (err) {
      setAviso({ tipo: "error", texto: textoDeError(err) });
    } finally {
      setOcupado(null);
    }
  }

  const auditar = () =>
    accion("auditar", async () => {
      const a = await api<Auditoria>(`/equipos/${e.id}/auditar`, { metodo: "POST" });
      if (a.estado === "error") throw new Error(`La auditoría falló: ${a.error}`);
      setPestana("hallazgos");
      return a.hallazgos.length ? `Auditoría lista: ${a.hallazgos.length} hallazgo(s).` : "Auditoría lista: sin hallazgos.";
    });
  const respaldar = () =>
    accion("respaldar", async () => {
      const r = await api<{ cambio: boolean }>(`/equipos/${e.id}/respaldar`, { metodo: "POST" });
      setPestana("respaldos");
      return r.cambio ? "Respaldo nuevo guardado." : "Sin cambios desde el último respaldo.";
    });
  const sondear = () =>
    accion("sondear", async () => {
      const s = await api<EstadoEquipo>(`/equipos/${e.id}/sondear`, { metodo: "POST" });
      if (!s.en_linea) throw new Error(`No responde por SNMP: ${s.error}`);
      return "El equipo respondió por SNMP.";
    });

  return (
    <>
      <div className="tenue"><Link to="/equipos">Equipos</Link> / {e.nombre}</div>
      <Encabezado
        titulo={e.nombre}
        subtitulo={<>{[marcas?.find((m) => m.marca === e.marca)?.nombre ?? e.marca, e.modelo, e.ip_gestion].filter(Boolean).join(" · ")} · <EstadoEnLinea valor={e.snmp ? e.en_linea : null} alcanzable={e.alcanzable} /></>}
        acciones={
          <>
            {tecnico && e.con_adaptador && (
              <button className="boton" disabled={!!ocupado || !e.usuario_ssh} onClick={auditar}>
                {ocupado === "auditar" ? "Auditando…" : "Auditar"}
              </button>
            )}
            {tecnico && e.con_respaldo && (
              <button className="boton" disabled={!!ocupado || !e.usuario_ssh} onClick={respaldar}>
                {ocupado === "respaldar" ? "Respaldando…" : "Respaldar"}
              </button>
            )}
            {tecnico && e.snmp && (
              <button className="boton" disabled={!!ocupado} onClick={sondear}>
                {ocupado === "sondear" ? "Consultando…" : "Sondear"}
              </button>
            )}
            {puede(usuario?.rol, "gestionar_equipos") && (
              <button className="boton" onClick={() => setEditando(true)}>Editar</button>
            )}
          </>
        }
      />
      {aviso && <div className={`aviso ${aviso.tipo}`} role="status">{aviso.texto}</div>}
      {e.con_respaldo && !e.usuario_ssh && (
        <div className="aviso atencion">Falta el usuario de acceso (SSH o API): sin él no se puede auditar ni respaldar.</div>
      )}

      <div className="pestanas" role="tablist">
        {pestanas.map((p) => (
          <button key={p} role="tab" aria-selected={pestana === p} className={pestana === p ? "activo" : ""} onClick={() => setPestana(p)}>
            {{
              resumen: "Resumen",
              interfaces: "Interfaces",
              hallazgos: `Hallazgos${e.hallazgos ? ` (${e.hallazgos})` : ""}`,
              respaldos: "Respaldos",
              documentar: "Documentar",
              snmp: "Explorador SNMP",
            }[p]}
          </button>
        ))}
      </div>

      {pestana === "resumen" && <Resumen equipo={e} version={version} />}
      {pestana === "interfaces" && <Interfaces equipo={e} version={version} gestor={gestor} />}
      {pestana === "hallazgos" && <HallazgosDelEquipo equipo={e} version={version} />}
      {pestana === "respaldos" && <Respaldos equipo={e} version={version} puedeVer={tecnico} />}
      {pestana === "documentar" && <Documentar equipo={e} />}
      {pestana === "snmp" && <ExploradorSnmp equipo={e} />}

      {puede(usuario?.rol, "gestionar_equipos") && (
        <Tarjeta titulo="Zona de peligro">
          <div className="entre">
            <span className="tenue">Borra el equipo con sus auditorías, respaldos e historial.</span>
            <button
              className="boton peligro"
              onClick={async () => {
                if (!window.confirm(`¿Borrar ${e.nombre}? No se puede deshacer.`)) return;
                await api(`/equipos/${e.id}`, { metodo: "DELETE" });
                navegar("/equipos");
              }}
            >
              Borrar equipo
            </button>
          </div>
        </Tarjeta>
      )}

      {editando && (
        <FormularioEquipo
          equipo={e}
          onCerrar={() => setEditando(false)}
          onListo={() => {
            setEditando(false);
            equipo.recargar();
          }}
        />
      )}
    </>
  );
}

function Resumen({ equipo, version }: { equipo: Equipo; version: number }) {
  const estado = useDatos<EstadoEquipo>(equipo.snmp ? `/equipos/${equipo.id}/estado?v=${version}` : null);
  return (
    <div className="grilla">
      <Tarjeta titulo="Monitoreo">
        {!equipo.snmp ? (
          <p className="tenue" style={{ margin: 0 }}>Sin SNMP configurado. Edita el equipo para activar el monitoreo.</p>
        ) : !estado.datos ? (
          <p className="tenue" style={{ margin: 0 }}>Todavía no fue sondeado. Se hace solo cada 5 minutos.</p>
        ) : (
          <div className="pila">
            <div><EstadoEnLinea valor={estado.datos.en_linea} alcanzable={estado.datos.alcanzable} /></div>
            {estado.datos.error && (
              <div className={estado.datos.alcanzable ? "aviso atencion" : "aviso error"}>{estado.datos.error}</div>
            )}
            <div><span className="tenue">Encendido hace </span>{duracion(estado.datos.uptime_segundos)}</div>
            <div><span className="tenue">Último sondeo </span>{hace(estado.datos.ultimo_sondeo)}</div>
          </div>
        )}
      </Tarjeta>
      <Tarjeta titulo="Datos" acciones={<Puntaje valor={equipo.puntaje} conTexto />}>
        <div className="pila">
          {estado.datos?.sys_nombre && <div><span className="tenue">Identity </span>{estado.datos.sys_nombre}</div>}
          {(estado.datos?.modelo || equipo.modelo) && <div><span className="tenue">Modelo </span>{estado.datos?.modelo || equipo.modelo}</div>}
          {estado.datos?.version && <div><span className="tenue">Versión </span>{estado.datos.version}</div>}
          {estado.datos?.ubicacion && <div><span className="tenue">Ubicación </span>{estado.datos.ubicacion}</div>}
          <div><span className="tenue">Acceso </span>{equipo.usuario_ssh ? `${NOMBRES_DE_ACCESO[equipo.acceso]} · ${equipo.usuario_ssh} · puerto ${equipo.puerto_ssh}` : "sin configurar"}</div>
          <div><span className="tenue">SNMP </span>{equipo.snmp ? `v${equipo.snmp.version}${equipo.snmp.usuario ? ` · ${equipo.snmp.usuario}` : ""}` : "sin configurar"}</div>
          <div>
            <span className="tenue">Número de serie </span>{equipo.numero_serie || estado.datos?.serie || "—"}
            {estado.datos?.serie && equipo.numero_serie && estado.datos.serie !== equipo.numero_serie && (
              <span className="pill medio" title="El equipo reporta otra serie: ¿se reemplazó?"> SNMP dice {estado.datos.serie}</span>
            )}
          </div>
          <div><span className="tenue">Alta </span>{fecha(equipo.creado)}</div>
        </div>
      </Tarjeta>
      {estado.datos?.sys_descripcion && (
        <Tarjeta titulo="Descripción del equipo">
          <div className="tenue" style={{ fontSize: 13 }}>{estado.datos.sys_descripcion}</div>
        </Tarjeta>
      )}
    </div>
  );
}

function usoPorcentual(i: Interfaz): number | null {
  if (!i.velocidad_mbps || i.bps_entrada === null || i.bps_salida === null) return null;
  return Math.round((Math.max(i.bps_entrada, i.bps_salida) * 100) / (i.velocidad_mbps * 1e6));
}

function Interfaces({ equipo, version, gestor }: { equipo: Equipo; version: number; gestor: boolean }) {
  const { datos, cargando, recargar } = useDatos<Interfaz[]>(`/equipos/${equipo.id}/interfaces?v=${version}`);
  const [error, setError] = useState<unknown>(null);
  const [soloVigiladas, setSoloVigiladas] = useState(false);

  async function alternar(i: Interfaz) {
    setError(null);
    try {
      if (i.vigilada_id) await api(`/vigiladas/${i.vigilada_id}`, { metodo: "DELETE" });
      else await api(`/equipos/${equipo.id}/vigiladas`, { metodo: "POST", cuerpo: { if_index: i.if_index } });
      recargar();
    } catch (err) {
      setError(err);
    }
  }

  if (cargando && !datos) return <Cargando />;
  const visibles = (datos ?? []).filter((i) => !soloVigiladas || i.vigilada_id);
  return (
    <div className="pila">
      <ErrorOPro error={error} />
      {gestor && !!datos?.length && (
        <div className="entre">
          <span className="tenue" style={{ fontSize: 13 }}>
            Vigila los uplinks y enlaces importantes: mufa avisa si se caen o si pasan del 80 % de su velocidad por 15 minutos.
          </span>
          <label className="casilla"><input type="checkbox" checked={soloVigiladas} onChange={(x) => setSoloVigiladas(x.target.checked)} /> Solo vigiladas</label>
        </div>
      )}
      <Tarjeta sinRelleno>
        {!datos?.length ? (
          <Vacio titulo="Sin datos de interfaces">Aparecen después de dos sondeos SNMP.</Vacio>
        ) : (
          <div className="tabla-caja">
            <table>
              <thead><tr><th>Interfaz</th><th>Estado</th><th>Velocidad</th><th>Entrada</th><th>Salida</th><th>Uso</th><th>Aviso</th></tr></thead>
              <tbody>
                {visibles.map((i) => {
                  const uso = usoPorcentual(i);
                  return (
                    <tr key={i.if_index}>
                      <td style={{ fontWeight: 500 }}>{i.nombre}</td>
                      <td>{i.operativa ? <span className="pill ok">Arriba</span> : <span className="pill gris">Abajo</span>}</td>
                      <td>{i.velocidad_mbps ? bps(i.velocidad_mbps * 1e6) : "—"}</td>
                      <td>{bps(i.bps_entrada)}</td>
                      <td>{bps(i.bps_salida)}</td>
                      <td className={uso !== null && uso >= (i.umbral_saturacion ?? 80) ? "texto-rojo" : "tenue"}>{uso === null ? "—" : `${uso} %`}</td>
                      <td>
                        {gestor ? (
                          <button className={i.vigilada_id ? "boton chico primario" : "boton chico"} onClick={() => void alternar(i)} aria-pressed={!!i.vigilada_id}>
                            {i.vigilada_id ? "Vigilada" : "Vigilar"}
                          </button>
                        ) : i.vigilada_id ? (
                          <span className="pill info">Vigilada</span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
    </div>
  );
}

function ResumenImportacion({ r, que }: { r: ResultadoImportacion; que: string }) {
  return (
    <div className="pila" style={{ gap: 6 }}>
      <div className="aviso ok">
        {r.nuevas} {que} nuevas, {r.actualizadas} ya documentadas (por {r.fuente}).
        {r.prefijos_creados.length > 0 && ` Prefijos creados: ${r.prefijos_creados.join(", ")}.`}
      </div>
      {r.conflictos.length > 0 && (
        <div className="aviso atencion">
          <strong>Para revisar ({r.conflictos.length}):</strong>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{r.conflictos.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function Documentar({ equipo }: { equipo: Equipo }) {
  const dominios = useDatos<Dominio[]>("/vlans/dominios");
  const [dominio, setDominio] = useState("");
  const [ips, setIps] = useState<ResultadoImportacion | null>(null);
  const [vlans, setVlans] = useState<ResultadoImportacion | null>(null);
  const [ocupado, setOcupado] = useState<"ips" | "vlans" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const dominioElegido = dominio || String(dominios.datos?.[0]?.id ?? "");

  async function importar(que: "ips" | "vlans") {
    setOcupado(que);
    setError(null);
    try {
      if (que === "ips") setIps(await api<ResultadoImportacion>(`/equipos/${equipo.id}/importar/ips`, { metodo: "POST" }));
      else setVlans(await api<ResultadoImportacion>(`/equipos/${equipo.id}/importar/vlans`, { metodo: "POST", cuerpo: { dominio_id: Number(dominioElegido) } }));
    } catch (err) {
      setError(err);
    } finally {
      setOcupado(null);
    }
  }

  return (
    <div className="pila">
      <ErrorOPro error={error} />
      <div className="grilla">
        <Tarjeta titulo="IPs al IPAM">
          <div className="pila">
            <p className="tenue" style={{ margin: 0 }}>
              Trae todas las IPs configuradas en {equipo.nombre} (por SNMP), crea los prefijos que falten y guarda cada IP con su interfaz. Si una IP ya está en otro equipo, te la marca como posible duplicado.
            </p>
            <div><button className="boton primario" disabled={!equipo.snmp || !!ocupado} onClick={() => void importar("ips")}>{ocupado === "ips" ? "Importando…" : "Importar IPs"}</button></div>
            {!equipo.snmp && <span className="tenue">Necesita SNMP configurado.</span>}
            {ips && <ResumenImportacion r={ips} que="IPs" />}
          </div>
        </Tarjeta>
        <Tarjeta titulo="VLANs">
          <div className="pila">
            <p className="tenue" style={{ margin: 0 }}>
              Trae las VLANs del equipo con su interfaz y las documenta en un dominio de capa 2. Si un número ya existe con otro nombre, te lo avisa en vez de pisarlo.
            </p>
            {dominios.datos?.length ? (
              <>
                <Campo etiqueta="Dominio de capa 2">
                  <select value={dominioElegido} onChange={(x) => setDominio(x.target.value)}>
                    {dominios.datos.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
                  </select>
                </Campo>
                <div><button className="boton primario" disabled={!!ocupado} onClick={() => void importar("vlans")}>{ocupado === "vlans" ? "Importando…" : "Importar VLANs"}</button></div>
              </>
            ) : (
              <span className="tenue">Primero crea un dominio en <Link to="/vlans">VLANs</Link>.</span>
            )}
            {vlans && <ResumenImportacion r={vlans} que="VLANs" />}
          </div>
        </Tarjeta>
      </div>
    </div>
  );
}

const OIDS_UTILES: { oid: string; texto: string }[] = [
  { oid: "1.3.6.1.2.1.1", texto: "Sistema (nombre, descripción, uptime)" },
  { oid: "1.3.6.1.2.1.31.1.1.1.1", texto: "Nombres de interfaces" },
  { oid: "1.3.6.1.2.1.4.20.1.1", texto: "IPs del equipo" },
  { oid: "1.3.6.1.2.1.4.22.1.2", texto: "Tabla ARP" },
  { oid: "1.3.6.1.4.1.14988.1.1.3", texto: "MikroTik: salud (temperatura, voltaje)" },
  { oid: "1.3.6.1.4.1.14988.1.1.19", texto: "MikroTik: potencia óptica de SFP" },
];

function ExploradorSnmp({ equipo }: { equipo: Equipo }) {
  const [oid, setOid] = useState("1.3.6.1.2.1.1");
  const [filas, setFilas] = useState<{ oid: string; valor: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function recorrer(destino = oid) {
    setOid(destino);
    setCargando(true);
    setError(null);
    try {
      setFilas(await api(`/equipos/${equipo.id}/snmp/recorrer`, { metodo: "POST", cuerpo: { oid: destino.trim() } }));
    } catch (err) {
      setError(textoDeError(err));
      setFilas(null);
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="pila">
      <Tarjeta>
        <form className="fila" onSubmit={(x) => { x.preventDefault(); void recorrer(); }}>
          <input className="mono crece" value={oid} onChange={(x) => setOid(x.target.value)} aria-label="OID" placeholder="1.3.6.1.2.1.1" />
          <button className="boton primario" type="submit" disabled={cargando}>{cargando ? "Consultando…" : "Recorrer"}</button>
        </form>
        <div className="fila" style={{ marginTop: 10, gap: 6 }}>
          {OIDS_UTILES.map((o) => (
            <button key={o.oid} type="button" className="boton chico" onClick={() => void recorrer(o.oid)}>{o.texto}</button>
          ))}
        </div>
      </Tarjeta>
      <MensajeError mensaje={error} />
      {filas && (
        <Tarjeta sinRelleno>
          {filas.length === 0 ? (
            <Vacio titulo="Sin datos bajo ese OID" />
          ) : (
            <div className="tabla-caja" style={{ maxHeight: "60vh", overflowY: "auto" }}>
              <table>
                <thead><tr><th>OID</th><th>Valor</th></tr></thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.oid}><td className="mono" style={{ whiteSpace: "nowrap" }}>{f.oid}</td><td className="mono">{f.valor}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Tarjeta>
      )}
      <p className="tenue" style={{ fontSize: 12, margin: 0 }}>Solo lectura: mufa nunca escribe por SNMP. Máximo 500 filas por consulta.</p>
    </div>
  );
}

function HallazgosDelEquipo({ equipo, version }: { equipo: Equipo; version: number }) {
  const lista = useDatos<AuditoriaResumen[]>(`/auditorias?equipo_id=${equipo.id}&limite=1&v=${version}`);
  const ultima = lista.datos?.[0];
  const detalle = useDatos<Auditoria>(ultima ? `/auditorias/${ultima.id}` : null);
  if (lista.cargando && !lista.datos) return <Cargando />;
  if (!ultima) return <Tarjeta><Vacio titulo="Todavía no se auditó">Se audita solo una vez al día, o usa «Auditar».</Vacio></Tarjeta>;
  const a = detalle.datos;
  return (
    <div className="pila">
      <div className="tenue">
        Última auditoría {hace(ultima.inicio)}
        {a?.estado === "error" && <span className="texto-rojo"> · falló: {a.error}</span>}
      </div>
      {a?.estado === "ok" && a.hallazgos.length === 0 && <Tarjeta><Vacio titulo="Sin hallazgos" /></Tarjeta>}
      {a?.hallazgos.map((h) => <TarjetaHallazgo key={h.id} hallazgo={h} />)}
    </div>
  );
}

function Respaldos({ equipo, version, puedeVer }: { equipo: Equipo; version: number; puedeVer: boolean }) {
  const { datos, cargando } = useDatos<Respaldo[]>(`/equipos/${equipo.id}/respaldos?v=${version}`);
  const [viendo, setViendo] = useState<{ titulo: string; texto: string; diff: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ver(r: Respaldo) {
    try {
      const c = await api<{ contenido: string }>(`/respaldos/${r.id}`);
      setViendo({ titulo: `Respaldo del ${fecha(r.creado)}`, texto: c.contenido, diff: false });
    } catch (err) {
      setError(textoDeError(err));
    }
  }
  async function diferencias(r: Respaldo) {
    try {
      const d = await api<{ diferencias: string }>(`/respaldos/${r.id}/diferencias`);
      setViendo({ titulo: `Qué cambió el ${fecha(r.creado)}`, texto: d.diferencias || "(sin diferencias)", diff: true });
    } catch (err) {
      setError(textoDeError(err));
    }
  }

  if (cargando && !datos) return <Cargando />;
  if (!equipo.con_respaldo) return <Tarjeta><Vacio titulo="Sin respaldos">Esta marca todavía no se puede respaldar: solo se monitorea por SNMP.</Vacio></Tarjeta>;
  return (
    <>
      <MensajeError mensaje={error} />
      <Tarjeta sinRelleno>
        {!datos?.length ? (
          <Vacio titulo="Todavía no hay respaldos">Se respalda solo todos los días (la hora se elige en Respaldos), o usa «Respaldar».</Vacio>
        ) : (
          <div className="tabla-caja">
            <table>
              <thead><tr><th>Versión</th><th>Origen</th><th>Confirmado</th><th>Tamaño</th><th /></tr></thead>
              <tbody>
                {datos.map((r, i) => (
                  <tr key={r.id}>
                    <td>{fecha(r.creado)}</td>
                    <td className="tenue">{r.origen === "programado" ? "Automático" : "Manual"}</td>
                    <td className="tenue">{hace(r.confirmado)}</td>
                    <td className="tenue">{(r.tamano / 1024).toFixed(1)} KB</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {puedeVer && (
                        <>
                          {i < datos.length - 1 && <button className="boton chico" onClick={() => void diferencias(r)}>Qué cambió</button>}{" "}
                          <button className="boton chico" onClick={() => void ver(r)}>Ver</button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
      {viendo && (
        <Modal titulo={viendo.titulo} onCerrar={() => setViendo(null)}>
          <pre className={viendo.diff ? "diff" : ""} style={{ maxHeight: "60vh" }}>
            {viendo.diff
              ? viendo.texto.split("\n").map((l, i) => (
                  <div key={i} className={l.startsWith("+++") || l.startsWith("---") || l.startsWith("@@") ? "cabeza" : l.startsWith("+") ? "mas" : l.startsWith("-") ? "menos" : ""}>
                    {l || " "}
                  </div>
                ))
              : viendo.texto}
          </pre>
        </Modal>
      )}
    </>
  );
}
