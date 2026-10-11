import { Icono } from "../componentes/Icono";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Link } from "react-router";
import { Campo, Cargando, Encabezado, Formulario, MensajeError, Modal, Segmentado, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import { numeroAIpv4, rangoUtilizable } from "../subredes";
import type { Direccion, Equipo, Prefijo, ResultadoImportacion, Sitio } from "../tipos";
import { puede, useDatos } from "../util";

type Grupo = {
  clave: string;
  nombre: string;
  tipo: "equipo" | "sitio" | "ninguno";
  redes: Prefijo[];
  asignadas: number;
  utilizables: number;
  porcentaje: number;
};

const ES_IP = /^(\d{1,3}\.){3}\d{1,3}$|^[0-9a-f:]+:[0-9a-f:]*$/i;

export function Ipam() {
  const { usuario } = useSesion();
  const gestor = puede(usuario?.rol, "gestionar_equipos");
  const { datos, error, cargando, recargar } = useDatos<Prefijo[]>("/ipam/prefijos");
  const { datos: sitios } = useDatos<Sitio[]>("/sitios");
  const [nuevo, setNuevo] = useState(false);
  const [importando, setImportando] = useState(false);
  const [elegido, setElegido] = useState<Prefijo | null>(null);
  const [editando, setEditando] = useState<Prefijo | null>(null);
  const [borrando, setBorrando] = useState<Prefijo | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [enIp, setEnIp] = useState<{ prefijos: Prefijo[]; asignacion: Direccion | null } | null>(null);

  const sitio = (id: number | null) => sitios?.find((s) => s.id === id)?.nombre ?? "—";
  const texto = busqueda.trim();
  const esIp = ES_IP.test(texto);

  // Buscando una IP: en qué prefijos cae y si está asignada, mientras se escribe.
  useEffect(() => {
    if (!esIp) {
      setEnIp(null);
      return;
    }
    const espera = setTimeout(() => {
      api<{ prefijos: Prefijo[]; asignacion: Direccion | null }>(`/ipam/buscar?ip=${encodeURIComponent(texto)}`)
        .then(setEnIp)
        .catch(() => setEnIp(null));
    }, 250);
    return () => clearTimeout(espera);
  }, [texto, esIp]);

  const visibles = useMemo(() => {
    if (!datos) return [];
    if (!texto) return datos;
    if (esIp && enIp) return datos.filter((p) => enIp.prefijos.some((e) => e.id === p.id));
    const t = texto.toLowerCase();
    return datos.filter(
      (p) =>
        p.prefijo.includes(t) ||
        p.descripcion.toLowerCase().includes(t) ||
        sitio(p.sitio_id).toLowerCase().includes(t) ||
        p.equipos.some((e) => e.toLowerCase().includes(t)) ||
        String(p.vlan ?? "") === t,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datos, texto, esIp, enIp, sitios]);

  // Agrupado por equipo (o sitio): a la izquierda cada uno con su % de uso, a la derecha sus redes.
  const grupos = useMemo(() => {
    const mapa = new Map<string, Grupo>();
    for (const p of visibles) {
      const tipo: Grupo["tipo"] = p.equipo ? "equipo" : p.sitio_id !== null ? "sitio" : "ninguno";
      const nombre = p.equipo || (p.sitio_id !== null ? sitio(p.sitio_id) : "Sin ubicar");
      const clave = `${tipo}:${nombre}`;
      const g = mapa.get(clave) ?? { clave, nombre, tipo, redes: [], asignadas: 0, utilizables: 0, porcentaje: 0 };
      g.redes.push(p);
      g.asignadas += p.asignadas;
      g.utilizables += p.utilizables;
      mapa.set(clave, g);
    }
    const lista = [...mapa.values()];
    for (const g of lista) g.porcentaje = g.utilizables ? Math.round((g.asignadas / g.utilizables) * 100) : 0;
    return lista.sort((a, b) => (a.tipo === "ninguno" ? 1 : 0) - (b.tipo === "ninguno" ? 1 : 0) || a.nombre.localeCompare(b.nombre, "es"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibles, sitios]);
  const [grupo, setGrupo] = useState<string | null>(null);
  const grupoActual = grupos.find((g) => g.clave === grupo) ?? grupos[0];

  const totales = (datos ?? []).filter((p) => p.contenido_en === null);
  const enUso = totales.reduce((n, p) => n + p.asignadas, 0);
  const utilizables = totales.reduce((n, p) => n + p.utilizables, 0);

  return (
    <>
      <Encabezado
        titulo="IPAM"
        subtitulo={datos?.length ? `${datos.length} ${datos.length === 1 ? "prefijo" : "prefijos"} · ${enUso.toLocaleString("es")} ${enUso === 1 ? "IP" : "IPs"} en uso · ${(utilizables - enUso).toLocaleString("es")} libres` : "Prefijos y direcciones documentados"}
        acciones={
          gestor && (
            <>
              <button className="boton" onClick={() => setImportando(true)}>Importar de un equipo</button>
              <button className="boton primario" onClick={() => setNuevo(true)}>Nuevo prefijo</button>
            </>
          )
        }
      />
      <div className="buscador">
        <Icono nombre="buscar" className="tenue" />
        <input
          placeholder="Buscar equipo, interfaz, red, descripción, VLAN o una IP…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          aria-label="Buscar en el IPAM"
        />
        {busqueda && <button className="boton-texto" onClick={() => setBusqueda("")} aria-label="Limpiar">×</button>}
      </div>
      {esIp && enIp && (
        <div className={enIp.asignacion ? "aviso atencion" : enIp.prefijos.length ? "aviso ok" : "aviso info"}>
          {!enIp.prefijos.length ? (
            <><strong className="mono">{texto}</strong> no está en ningún prefijo documentado.</>
          ) : enIp.asignacion ? (
            <><strong className="mono">{texto}</strong> está <strong>en uso</strong>: {enIp.asignacion.descripcion || "sin descripción"}{enIp.asignacion.interfaz && ` · ${enIp.asignacion.interfaz}`}. Red: {enIp.prefijos.map((p) => p.prefijo).join(" › ")}.</>
          ) : (
            <><strong className="mono">{texto}</strong> está <strong>libre</strong> en {enIp.prefijos.map((p) => p.prefijo).join(" › ")}.</>
          )}
        </div>
      )}
      <MensajeError mensaje={error} />
      {cargando && !datos ? (
        <Cargando />
      ) : !datos?.length ? (
        <Tarjeta><Vacio titulo="Sin prefijos">Documenta tus bloques de gestión, de clientes y públicos, o impórtalos de un equipo.</Vacio></Tarjeta>
      ) : !visibles.length ? (
        <Tarjeta><Vacio titulo="Nada coincide">Prueba con otra red, descripción, equipo o IP.</Vacio></Tarjeta>
      ) : (
        <div className="maestro-detalle">
          <aside className="grupos" aria-label="Equipos y lugares">
            {grupos.map((g, i) => (
              <button
                key={g.clave}
                className={g.clave === grupoActual?.clave ? "grupo activo" : "grupo"}
                style={{ animationDelay: `${Math.min(i, 12) * 30}ms` }}
                onClick={() => setGrupo(g.clave)}
              >
                <span className="grupo-fila">
                  <span className={`grupo-icono ${g.tipo}`} aria-hidden="true"><Icono nombre={g.tipo === "equipo" ? "equipo" : g.tipo === "sitio" ? "ubicacion" : "pregunta"} /></span>
                  <strong>{g.nombre}</strong>
                  <span className={`grupo-porcentaje ${g.porcentaje >= 85 ? "lleno" : g.porcentaje >= 70 ? "alto" : ""}`}>{g.porcentaje}%</span>
                </span>
                <span className="grupo-barra"><i style={{ width: `${Math.min(100, g.porcentaje)}%` }} /></span>
                <span className="grupo-detalle">{g.redes.length} {g.redes.length === 1 ? "red" : "redes"} · {g.asignadas.toLocaleString("es")} {g.asignadas === 1 ? "IP" : "IPs"} en uso</span>
              </button>
            ))}
          </aside>
          {grupoActual && (
            <section className="detalle-grupo" key={grupoActual.clave}>
              <div className="detalle-grupo-cabeza">
                <div>
                  <span className="tenue" style={{ fontSize: 12 }}>{grupoActual.tipo === "equipo" ? "Equipo" : grupoActual.tipo === "sitio" ? "Sitio" : "Sin equipo ni sitio"}</span>
                  <h2>{grupoActual.nombre}</h2>
                </div>
                <div className="cifras-ipam">
                  <div><strong>{grupoActual.redes.length}</strong><span>{grupoActual.redes.length === 1 ? "red" : "redes"}</span></div>
                  <div className="uso"><strong>{grupoActual.asignadas.toLocaleString("es")}</strong><span>en uso</span></div>
                  <div className="libre"><strong>{(grupoActual.utilizables - grupoActual.asignadas).toLocaleString("es")}</strong><span>libres</span></div>
                </div>
              </div>
              <div className="lista-redes">
                {grupoActual.redes.map((p, i) => {
                  const interfaces = p.equipos.filter((e) => e.startsWith(`${grupoActual.nombre} · `)).map((e) => e.slice(grupoActual.nombre.length + 3));
                  const porcentaje = p.porcentaje_uso ?? 0;
                  return (
                    <div key={p.id} className="fila-red fila-entra" style={{ animationDelay: `${Math.min(i, 15) * 20}ms` }} onClick={() => setElegido(p)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setElegido(p)}>
                      <div className="fila-red-principal">
                        <span className="mono red-prefijo">{p.prefijo}</span>
                        <span className="fila-red-texto">
                          {p.descripcion || <span className="tenue">Sin descripción</span>}
                          {interfaces.length > 0 && <span className="tenue"> · {interfaces.join(", ")}</span>}
                        </span>
                        {p.vlan && <span className="pill">VLAN {p.vlan}</span>}
                        {p.reservado && <span className="pill info">Reservado</span>}
                      </div>
                      <div className="fila-red-uso">
                        <span className="grupo-barra"><i className={porcentaje >= 85 ? "lleno" : porcentaje >= 70 ? "alto" : ""} style={{ width: `${Math.min(100, porcentaje)}%` }} /></span>
                        <span className="tenue">{p.asignadas.toLocaleString("es")} / {p.utilizables.toLocaleString("es")}</span>
                      </div>
                      {gestor && (
                        <span className="acciones-fila" onClick={(e) => e.stopPropagation()}>
                          <button className="boton-icono" title="Editar" aria-label={`Editar ${p.prefijo}`} onClick={() => setEditando(p)}><Icono nombre="editar" /></button>
                          <button className="boton-icono peligro" title="Eliminar" aria-label={`Eliminar ${p.prefijo}`} onClick={() => setBorrando(p)}><Icono nombre="papelera" /></button>
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      )}

      {importando && <ImportarDeEquipo onCerrar={() => { setImportando(false); recargar(); }} />}
      {nuevo && (
        <EditarPrefijo sitios={sitios ?? []} onCerrar={() => setNuevo(false)} onListo={() => { setNuevo(false); recargar(); }} />
      )}
      {editando && (
        <EditarPrefijo prefijo={editando} sitios={sitios ?? []} onCerrar={() => setEditando(null)} onListo={() => { setEditando(null); recargar(); }} />
      )}
      {borrando && (
        <BorrarPrefijo prefijo={borrando} onCerrar={() => setBorrando(null)} onListo={() => { setBorrando(null); recargar(); }} />
      )}
      {elegido && (
        <DireccionesDelPrefijo prefijo={elegido} gestor={gestor} onCerrar={() => { setElegido(null); recargar(); }} />
      )}
    </>
  );
}

function ImportarDeEquipo({ onCerrar }: { onCerrar: () => void }) {
  const { datos: equipos } = useDatos<Equipo[]>("/equipos");
  const conSnmp = (equipos ?? []).filter((e) => e.snmp);
  const [equipo, setEquipo] = useState("");
  const [resultado, setResultado] = useState<ResultadoImportacion | null>(null);
  const [segundos, setSegundos] = useState<number | null>(null);
  const elegido = equipo || String(conSnmp[0]?.id ?? "");

  useEffect(() => {
    if (segundos === null) return;
    const reloj = setInterval(() => setSegundos((s) => (s === null ? null : s + 1)), 1000);
    return () => clearInterval(reloj);
  }, [segundos === null]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Modal titulo="Importar IPs de un equipo" onCerrar={onCerrar}>
      {conSnmp.length === 0 ? (
        <p className="tenue">Ningún equipo tiene SNMP configurado todavía.</p>
      ) : (
        <Formulario
          textoBoton={resultado ? "Importar de nuevo" : "Importar"}
          onCancelar={onCerrar}
          onEnviar={async () => {
            setResultado(null);
            setSegundos(0);
            try {
              setResultado(await api<ResultadoImportacion>(`/equipos/${elegido}/importar/ips`, { metodo: "POST" }));
            } finally {
              setSegundos(null);
            }
          }}
        >
          <p className="tenue" style={{ margin: 0 }}>
            Lee por SNMP (solo lectura) las IPs configuradas en el equipo, crea los prefijos que falten y guarda cada IP con su interfaz. Lo que ya esté documentado en otro equipo se marca para revisar, no se pisa.
          </p>
          <Campo etiqueta="Equipo">
            <select value={elegido} onChange={(e) => setEquipo(e.target.value)} disabled={segundos !== null}>
              {conSnmp.map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
            </select>
          </Campo>
          {segundos !== null && (
            <div className="progreso-lectura" role="status">
              <span className="barra-indeterminada" />
              Leyendo el equipo… {segundos} s. Un router con muchas interfaces puede tardar hasta un minuto.
            </div>
          )}
          {resultado && (
            <>
              <div className="aviso ok">
                {resultado.nuevas} IPs nuevas, {resultado.actualizadas} ya documentadas.
                {resultado.prefijos_creados.length > 0 && ` Prefijos creados: ${resultado.prefijos_creados.length}.`}
              </div>
              {resultado.conflictos.length > 0 && (
                <div className="aviso atencion">
                  <strong>Para revisar:</strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{resultado.conflictos.map((c) => <li key={c}>{c}</li>)}</ul>
                </div>
              )}
            </>
          )}
        </Formulario>
      )}
    </Modal>
  );
}

function EditarPrefijo(props: { prefijo?: Prefijo; sitios: Sitio[]; onCerrar: () => void; onListo: () => void }) {
  const p = props.prefijo;
  const [prefijo, setPrefijo] = useState(p?.prefijo ?? "");
  const [descripcion, setDescripcion] = useState(p?.descripcion ?? "");
  const [sitio, setSitio] = useState(p?.sitio_id?.toString() ?? "");
  const [vlan, setVlan] = useState(p?.vlan?.toString() ?? "");
  const [reservado, setReservado] = useState(p?.reservado ?? false);
  return (
    <Modal titulo={p ? `Editar ${p.prefijo}` : "Nuevo prefijo"} onCerrar={props.onCerrar}>
      <Formulario
        textoBoton="Guardar"
        onCancelar={props.onCerrar}
        onEnviar={async () => {
          const cuerpo = { prefijo, descripcion, sitio_id: sitio ? Number(sitio) : null, vlan: vlan ? Number(vlan) : null, reservado };
          if (p) await api(`/ipam/prefijos/${p.id}`, { metodo: "PATCH", cuerpo });
          else await api("/ipam/prefijos", { metodo: "POST", cuerpo });
          props.onListo();
        }}
      >
        <div className="formulario">
          <Campo etiqueta="Prefijo" ayuda={p ? "Puedes cambiar la red o la máscara si las IPs documentadas siguen cabiendo" : "IPv4 o IPv6, por ejemplo 10.20.4.0/22"}>
            <input className="mono" value={prefijo} onChange={(e) => setPrefijo(e.target.value)} required />
          </Campo>
          <Campo etiqueta="Descripción"><input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} placeholder="Clientes PPPoE Norte" /></Campo>
          <Campo etiqueta="Sitio">
            <select value={sitio} onChange={(e) => setSitio(e.target.value)}>
              <option value="">Sin sitio</option>
              {props.sitios.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="VLAN"><input type="number" min={1} max={4094} value={vlan} onChange={(e) => setVlan(e.target.value)} /></Campo>
          <label className="casilla ancho"><input type="checkbox" checked={reservado} onChange={(e) => setReservado(e.target.checked)} /> Reservado (todavía sin uso)</label>
        </div>
      </Formulario>
    </Modal>
  );
}

function BorrarPrefijo(props: { prefijo: Prefijo; onCerrar: () => void; onListo: () => void }) {
  const p = props.prefijo;
  return (
    <Modal titulo={`Eliminar ${p.prefijo}`} onCerrar={props.onCerrar}>
      <Formulario
        textoBoton="Eliminar prefijo"
        peligro
        onCancelar={props.onCerrar}
        onEnviar={async () => {
          await api(`/ipam/prefijos/${p.id}`, { metodo: "DELETE" });
          props.onListo();
        }}
      >
        <p style={{ margin: 0 }}>
          {p.asignadas > 0
            ? <>Se borra la red y sus <strong>{p.asignadas} direcciones documentadas</strong>. Los prefijos de adentro, si los hay, se mantienen.</>
            : "La red no tiene direcciones documentadas. Los prefijos de adentro, si los hay, se mantienen."}
        </p>
        <p className="tenue" style={{ margin: 0, fontSize: 13 }}>Solo se borra la documentación en mufa: no se toca nada en los equipos.</p>
      </Formulario>
    </Modal>
  );
}

type Vista = "todas" | "uso" | "libres";
const POR_PAGINA = 256;
const MAX_LISTABLE = 65_536;

function DireccionesDelPrefijo(props: { prefijo: Prefijo; gestor: boolean; onCerrar: () => void }) {
  const { datos, recargar } = useDatos<Direccion[]>(`/ipam/prefijos/${props.prefijo.id}/ips`);
  const { datos: equipos } = useDatos<Equipo[]>("/equipos");
  const nombreEquipo = (id: number | null) => equipos?.find((e) => e.id === id)?.nombre;
  const [ip, setIp] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [vista, setVista] = useState<Vista>("todas");
  const [filtro, setFiltro] = useState("");
  const [limite, setLimite] = useState(POR_PAGINA);
  const [recien, setRecien] = useState<string | null>(null);

  const rango = rangoUtilizable(props.prefijo.prefijo);
  const listable = rango !== null && rango[1] - rango[0] + 1 <= MAX_LISTABLE;
  const asignadas = datos?.length ?? props.prefijo.asignadas;
  const libres = props.prefijo.utilizables - asignadas;
  const ocupado = props.prefijo.utilizables ? Math.round((asignadas / props.prefijo.utilizables) * 1000) / 10 : 0;
  const porIp = useMemo(() => new Map((datos ?? []).map((d) => [d.ip, d])), [datos]);

  // IPv4: se listan todas las direcciones de la red, en uso y libres. IPv6 o redes enormes: solo las en uso.
  const filas = useMemo(() => {
    const porIp = new Map((datos ?? []).map((d) => [d.ip, d]));
    const f = filtro.trim().toLowerCase();
    const coincide = (texto: string, d?: Direccion) =>
      !f || texto.includes(f) || (d?.descripcion.toLowerCase().includes(f) ?? false) || (d?.interfaz.toLowerCase().includes(f) ?? false);
    const resultado: { ip: string; d?: Direccion }[] = [];
    if (listable && rango) {
      for (let n = rango[0]; n <= rango[1] && resultado.length < limite; n++) {
        const texto = numeroAIpv4(n);
        const d = porIp.get(texto);
        if (vista === "uso" && !d) continue;
        if (vista === "libres" && d) continue;
        if (coincide(texto, d)) resultado.push({ ip: texto, d });
      }
    } else if (vista !== "libres") {
      for (const d of datos ?? []) if (coincide(d.ip, d) && resultado.length < limite) resultado.push({ ip: d.ip, d });
    }
    return resultado;
  }, [datos, vista, filtro, limite, listable, rango?.[0], rango?.[1]]); // eslint-disable-line react-hooks/exhaustive-deps

  async function asignar(direccion: string | null, texto: string) {
    const nueva = await api<Direccion>(`/ipam/prefijos/${props.prefijo.id}/ips`, { metodo: "POST", cuerpo: { ip: direccion, descripcion: texto } });
    setRecien(nueva.ip);
    setIp("");
    setDescripcion("");
    recargar();
  }

  return (
    <Modal titulo={props.prefijo.prefijo} onCerrar={props.onCerrar}>
      {(props.prefijo.descripcion || props.prefijo.equipos.length > 0) && (
        <div className="red-cabecera">
          {props.prefijo.descripcion && <strong>{props.prefijo.descripcion}</strong>}
          {props.prefijo.equipos.map((e) => <span key={e} className="donde-equipo">{e}</span>)}
          {props.prefijo.vlan && <span className="pill">VLAN {props.prefijo.vlan}</span>}
        </div>
      )}
      <div className="cifras-ipam">
        <div><strong>{props.prefijo.utilizables.toLocaleString("es")}</strong><span>utilizables</span></div>
        <div className="uso"><strong>{asignadas.toLocaleString("es")}</strong><span>en uso</span></div>
        <div className="libre"><strong>{libres.toLocaleString("es")}</strong><span>libres</span></div>
        <div className="porcentaje"><strong>{ocupado}%</strong><span>ocupado</span></div>
      </div>
      <div className="barra-doble" role="img" aria-label={`${asignadas} en uso y ${libres} libres`}>
        <span className="uso" style={{ width: `${asignadas ? Math.max(ocupado, 0.8) : 0}%` }} />
        <span className="libre" />
      </div>
      {rango && (
        <MapaDeDirecciones
          rango={rango}
          usadas={porIp}
          recien={recien}
          alElegirLibre={props.gestor ? (direccion) => setIp(direccion) : undefined}
          alElegirUsada={(direccion) => { setFiltro(direccion); setVista("todas"); }}
          alElegirBloque={(prefijo) => { setFiltro(prefijo); setVista("todas"); }}
        />
      )}
      {props.gestor && (
        <Formulario textoBoton={ip ? "Asignar" : "Asignar la siguiente libre"} onEnviar={() => asignar(ip.trim() || null, descripcion)}>
          <div className="formulario">
            <Campo etiqueta="IP" ayuda="Vacío = la siguiente libre"><input className="mono" value={ip} onChange={(e) => setIp(e.target.value)} /></Campo>
            <Campo etiqueta="Descripción"><input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} placeholder="CCR Nodo Norte" /></Campo>
          </div>
        </Formulario>
      )}
      <div className="entre" style={{ gap: 12, flexWrap: "wrap" }}>
        <Segmentado<Vista>
          etiqueta="Qué direcciones mostrar"
          valor={vista}
          onCambio={(v) => { setVista(v); setLimite(POR_PAGINA); }}
          opciones={[
            { valor: "todas", texto: listable ? "Todas" : "En uso" },
            { valor: "uso", texto: `En uso (${asignadas})` },
            { valor: "libres", texto: "Libres" },
          ]}
        />
        <input className="crece" style={{ minWidth: 180 }} placeholder="Filtrar por IP, descripción o interfaz" value={filtro} onChange={(e) => { setFiltro(e.target.value); setLimite(POR_PAGINA); }} aria-label="Filtrar direcciones" />
      </div>
      {!listable && vista === "libres" ? (
        <p className="tenue">Esta red es demasiado grande para listar las libres. Usa «Asignar la siguiente libre» o escribe una IP.</p>
      ) : !filas.length ? (
        <p className="tenue">{filtro ? "Nada coincide." : vista === "libres" ? "No quedan direcciones libres." : "Sin direcciones asignadas."}</p>
      ) : (
        <div className="tabla-caja" style={{ maxHeight: "46vh", overflowY: "auto" }}>
          <table className="tabla-ips">
            <thead><tr><th>IP</th><th>Estado</th><th>Descripción</th><th>Equipo</th><th /></tr></thead>
            <tbody>
              {filas.map(({ ip: direccion, d }) => (
                <tr key={direccion} className={direccion === recien ? "recien" : d ? "" : "libre"}>
                  <td className="mono">{direccion}</td>
                  <td>{d ? <span className="pill medio">En uso</span> : <span className="pill ok">Libre</span>}</td>
                  <td>{d?.descripcion || <span className="tenue">—</span>}</td>
                  <td>
                    {d?.equipo_id ? (
                      <><Link to={`/equipos/${d.equipo_id}`}>{nombreEquipo(d.equipo_id) ?? "equipo"}</Link>{d.interfaz && <span className="tenue"> · {d.interfaz}</span>}</>
                    ) : (
                      <span className="tenue">—</span>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {props.gestor && (d ? (
                      <button className="boton chico peligro" onClick={async () => { await api(`/ipam/ips/${d.id}`, { metodo: "DELETE" }); recargar(); }}>Liberar</button>
                    ) : (
                      <button className="boton chico" onClick={() => { setIp(direccion); }}>Usar</button>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filas.length >= limite && (
            <div style={{ textAlign: "center", padding: 10 }}>
              <button className="boton chico" onClick={() => setLimite((l) => l + POR_PAGINA)}>Mostrar más</button>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

/** Mapa visual de la red: un cuadro por IP (hasta 1024) o una barra por cada /24. */
function MapaDeDirecciones(props: {
  rango: [number, number];
  usadas: Map<string, Direccion>;
  recien: string | null;
  alElegirLibre?: (ip: string) => void;
  alElegirUsada: (ip: string) => void;
  alElegirBloque: (prefijo: string) => void;
}) {
  const [primera, ultima] = props.rango;
  const total = ultima - primera + 1;
  if (total <= 1024) {
    const cuadros = [];
    for (let n = primera; n <= ultima; n++) {
      const ip = numeroAIpv4(n);
      const d = props.usadas.get(ip);
      cuadros.push(
        <button
          key={ip}
          type="button"
          className={`ip-cuadro ${d ? "usada" : "libre"} ${ip === props.recien ? "recien" : ""}`}
          title={d ? `${ip} · ${d.descripcion || d.interfaz || "en uso"}` : `${ip} · libre${props.alElegirLibre ? " (clic para usarla)" : ""}`}
          onClick={() => (d ? props.alElegirUsada(ip) : props.alElegirLibre?.(ip))}
        />,
      );
    }
    return (
      <div className="mapa-ips">
        <div className={`ip-grilla ${total <= 64 ? "grande" : ""}`}>{cuadros}</div>
        <div className="mapa-leyenda">
          <span><i className="usada" /> En uso</span>
          <span><i className="libre" /> Libre</span>
          <span className="tenue">{numeroAIpv4(primera)} – {numeroAIpv4(ultima)}</span>
        </div>
      </div>
    );
  }
  // Redes grandes: una barra por cada /24, hasta 256 bloques.
  const porBloque = new Map<number, number>();
  for (const ip of props.usadas.keys()) {
    const p = ip.split(".").map(Number);
    const bloque = Math.floor((((p[0] ?? 0) * 256 + (p[1] ?? 0)) * 65536 + (p[2] ?? 0) * 256) / 256);
    porBloque.set(bloque, (porBloque.get(bloque) ?? 0) + 1);
  }
  const bloques: { prefijo: string; usadas: number; total: number }[] = [];
  for (let b = Math.floor(primera / 256) * 256; b <= ultima && bloques.length < 256; b += 256) {
    const desde = Math.max(b, primera);
    const hasta = Math.min(b + 255, ultima);
    bloques.push({ prefijo: numeroAIpv4(b).split(".").slice(0, 3).join("."), usadas: porBloque.get(b / 256) ?? 0, total: hasta - desde + 1 });
  }
  return (
    <div className="mapa-bloques">
      {bloques.map((b) => (
        <button key={b.prefijo} type="button" className="bloque" onClick={() => props.alElegirBloque(`${b.prefijo}.`)} title={`${b.prefijo}.0/24 · ${b.usadas} en uso`}>
          <span className="mono">{b.prefijo}.0/24</span>
          <span className="bloque-barra"><i style={{ width: `${b.usadas ? Math.max((b.usadas / b.total) * 100, 2) : 0}%` }} /></span>
          <span className="tenue">{b.usadas}</span>
        </button>
      ))}
    </div>
  );
}
