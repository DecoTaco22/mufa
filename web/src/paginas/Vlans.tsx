import { Icono } from "../componentes/Icono";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { Campo, Cargando, Encabezado, Formulario, MensajeError, Modal, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Dominio, Equipo, Vlan } from "../tipos";
import { puede, useDatos } from "../util";

type GrupoVlan = { clave: string; nombre: string; equipoId: number | null; vlans: Vlan[]; interfaces: number };

export function Vlans() {
  const { usuario } = useSesion();
  const gestor = puede(usuario?.rol, "gestionar_equipos");
  const dominios = useDatos<Dominio[]>("/vlans/dominios");
  const [elegido, setElegido] = useState<number | null>(null);
  const [nuevoDominio, setNuevoDominio] = useState(false);
  const actual = elegido ?? dominios.datos?.[0]?.id ?? null;

  return (
    <>
      <Encabezado
        titulo="VLANs"
        subtitulo="Documentación por dominio de capa 2: un número no se repite dentro del mismo dominio. Para traerlas de un equipo: Equipos › el equipo › Documentar."
        acciones={gestor && <button className="boton" onClick={() => setNuevoDominio(true)}>Nuevo dominio</button>}
      />
      <MensajeError mensaje={dominios.error} />
      {dominios.cargando && !dominios.datos ? (
        <Cargando />
      ) : !dominios.datos?.length ? (
        <Tarjeta>
          <Vacio titulo="Sin dominios de capa 2">
            Un dominio es un conjunto de equipos unidos por troncales, donde cada VLAN tiene que ser única (por ejemplo «Anillo central»).
          </Vacio>
        </Tarjeta>
      ) : (
        <>
          {dominios.datos.length > 1 && (
            <div className="dominios" role="tablist" aria-label="Dominio de capa 2">
              {dominios.datos.map((d) => (
                <button key={d.id} role="tab" aria-selected={d.id === actual} className={d.id === actual ? "activo" : ""} onClick={() => setElegido(d.id)}>
                  {d.nombre}
                </button>
              ))}
            </div>
          )}
          {actual !== null && <VlansDelDominio key={actual} dominioId={actual} gestor={gestor} />}
        </>
      )}
      {nuevoDominio && (
        <NuevoDominio
          onCerrar={() => setNuevoDominio(false)}
          onListo={(d) => { setNuevoDominio(false); setElegido(d.id); dominios.recargar(); }}
        />
      )}
    </>
  );
}

function NuevoDominio(props: { onCerrar: () => void; onListo: (d: Dominio) => void }) {
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  return (
    <Modal titulo="Nuevo dominio de capa 2" onCerrar={props.onCerrar}>
      <Formulario
        textoBoton="Crear"
        onCancelar={props.onCerrar}
        onEnviar={async () => props.onListo(await api<Dominio>("/vlans/dominios", { metodo: "POST", cuerpo: { nombre, descripcion } }))}
      >
        <Campo etiqueta="Nombre"><input value={nombre} onChange={(e) => setNombre(e.target.value)} required placeholder="Anillo central" /></Campo>
        <Campo etiqueta="Descripción"><input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} /></Campo>
      </Formulario>
    </Modal>
  );
}

function VlansDelDominio({ dominioId, gestor }: { dominioId: number; gestor: boolean }) {
  const { datos, recargar } = useDatos<Vlan[]>(`/vlans/dominios/${dominioId}/vlans`);
  const { datos: equipos } = useDatos<Equipo[]>("/equipos");
  const [agregandoA, setAgregandoA] = useState<Vlan | null>(null);
  const [editando, setEditando] = useState<Vlan | "nueva" | null>(null);
  const [busqueda, setBusqueda] = useState("");

  const t = busqueda.trim().toLowerCase();
  const visibles = (datos ?? []).filter(
    (v) =>
      !t ||
      String(v.numero) === t ||
      v.nombre.toLowerCase().includes(t) ||
      v.descripcion.toLowerCase().includes(t) ||
      v.equipos.some((e) => e.equipo.toLowerCase().includes(t) || e.interfaz.toLowerCase().includes(t)),
  );
  // A la izquierda: todas, cada equipo con sus VLANs, y las que no están en ningún equipo.
  const grupos = useMemo(() => {
    const porEquipo = new Map<number, GrupoVlan>();
    const sin: Vlan[] = [];
    for (const v of visibles) {
      if (!v.equipos.length) sin.push(v);
      for (const e of v.equipos) {
        const g = porEquipo.get(e.equipo_id) ?? { clave: `e${e.equipo_id}`, nombre: e.equipo, equipoId: e.equipo_id, vlans: [], interfaces: 0 };
        if (!g.vlans.includes(v)) g.vlans.push(v);
        if (e.interfaz) g.interfaces++;
        porEquipo.set(e.equipo_id, g);
      }
    }
    const equipos = [...porEquipo.values()].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
    const lista: GrupoVlan[] = [{ clave: "todas", nombre: "Todas", equipoId: null, vlans: visibles, interfaces: 0 }, ...equipos];
    if (sin.length) lista.push({ clave: "sin", nombre: "Sin equipo", equipoId: null, vlans: sin, interfaces: 0 });
    return lista;
  }, [visibles]);
  const [grupo, setGrupo] = useState("todas");
  const grupoActual = grupos.find((g) => g.clave === grupo) ?? grupos[0]!;
  const reservadas = (datos ?? []).filter((v) => v.reservada).length;
  const conEquipo = new Set((datos ?? []).flatMap((v) => v.equipos.map((e) => e.equipo_id))).size;

  return (
    <div className="crece pila" style={{ gap: 14 }}>
      <div className="entre" style={{ gap: 12, flexWrap: "wrap" }}>
        <div className="cifras-ipam">
          <div><strong>{datos?.length ?? 0}</strong><span>VLANs</span></div>
          <div className="libre"><strong>{(datos?.length ?? 0) - reservadas}</strong><span>en uso</span></div>
          <div className="uso"><strong>{reservadas}</strong><span>reservadas</span></div>
          <div><strong>{conEquipo}</strong><span>equipos</span></div>
        </div>
        {gestor && <button className="boton primario" onClick={() => setEditando("nueva")}>Agregar VLAN</button>}
      </div>
      <div className="buscador">
        <Icono nombre="buscar" className="tenue" />
        <input placeholder="Buscar por número, nombre, uso, equipo o interfaz…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} aria-label="Buscar VLAN" />
        {busqueda && <button className="boton-texto" onClick={() => setBusqueda("")} aria-label="Limpiar">×</button>}
      </div>
      {!datos?.length ? (
        <Tarjeta><Vacio titulo="Sin VLANs en este dominio">Agrégalas a mano o tráelas de un equipo: Equipos › el equipo › Documentar.</Vacio></Tarjeta>
      ) : !visibles.length ? (
        <Tarjeta><Vacio titulo="Nada coincide" /></Tarjeta>
      ) : (
        <div className="maestro-detalle">
          <aside className="grupos" aria-label="Equipos">
            {grupos.map((g, i) => (
              <button key={g.clave} className={g.clave === grupoActual.clave ? "grupo activo" : "grupo"} style={{ animationDelay: `${Math.min(i, 12) * 30}ms` }} onClick={() => setGrupo(g.clave)}>
                <span className="grupo-fila">
                  <span className={`grupo-icono ${g.clave === "todas" ? "sitio" : g.clave === "sin" ? "ninguno" : ""}`} aria-hidden="true"><Icono nombre={g.clave === "todas" ? "lista" : g.clave === "sin" ? "pregunta" : "equipo"} /></span>
                  <strong>{g.nombre}</strong>
                  <span className="grupo-porcentaje">{g.vlans.length}</span>
                </span>
                <span className="grupo-detalle">
                  {g.clave === "todas" ? `${g.vlans.length} VLANs del dominio` : g.clave === "sin" ? "Documentadas sin equipo" : `${g.vlans.length} VLANs · ${g.interfaces} interfaces`}
                </span>
              </button>
            ))}
          </aside>
          <section className="detalle-grupo" key={grupoActual.clave}>
            <div className="detalle-grupo-cabeza">
              <div>
                <span className="tenue" style={{ fontSize: 12 }}>{grupoActual.clave === "todas" ? "Dominio" : grupoActual.clave === "sin" ? "Sin equipo" : "Equipo"}</span>
                <h2>{grupoActual.nombre}</h2>
              </div>
              <div className="cifras-ipam">
                <div><strong>{grupoActual.vlans.length}</strong><span>VLANs</span></div>
                <div className="libre"><strong>{grupoActual.vlans.filter((v) => !v.reservada).length}</strong><span>en uso</span></div>
                <div className="uso"><strong>{grupoActual.vlans.filter((v) => v.reservada).length}</strong><span>reservadas</span></div>
              </div>
            </div>
            {grupoActual.equipoId === null ? (
            <div className="tabla-caja">
              <table className="tabla-vlans">
                <thead><tr><th>VLAN</th><th>Nombre y uso</th><th>Dónde está</th><th>Estado</th>{gestor && <th />}</tr></thead>
                <tbody>
                  {grupoActual.vlans.map((v, i) => (
                    <tr key={v.id} className="fila-entra" style={{ animationDelay: `${Math.min(i, 12) * 25}ms` }}>
                      <td><span className={v.reservada ? "vlan-id reservada" : "vlan-id"}>{v.numero}</span></td>
                      <td>
                        <div style={{ fontWeight: 600 }}>{v.nombre}</div>
                        {v.descripcion && <div className="red-descripcion">{v.descripcion}</div>}
                      </td>
                      <td>
                        <div className="chips-equipos">
                          {v.equipos.map((e) => (
                            <span key={`${e.equipo_id}-${e.interfaz}`} className="chip-equipo">
                              <Link to={`/equipos/${e.equipo_id}`}>{e.equipo}</Link>
                              {e.interfaz && <span className="tenue">{e.interfaz}</span>}
                              {e.nombre_en_equipo && e.nombre_en_equipo !== v.nombre && <span className="pill medio" title="En el equipo tiene otro nombre">{e.nombre_en_equipo}</span>}
                              {gestor && (
                                <button
                                  className="quitar"
                                  title={`Quitar de ${e.equipo}`}
                                  aria-label={`Quitar de ${e.equipo}`}
                                  onClick={async () => {
                                    await api(`/vlans/${v.id}/equipos/${e.equipo_id}?interfaz=${encodeURIComponent(e.interfaz)}`, { metodo: "DELETE" });
                                    recargar();
                                  }}
                                >×</button>
                              )}
                            </span>
                          ))}
                          {gestor ? (
                            <button className="chip-agregar" onClick={() => setAgregandoA(v)}>+ Equipo</button>
                          ) : (
                            !v.equipos.length && <span className="tenue">—</span>
                          )}
                        </div>
                      </td>
                      <td>{v.reservada ? <span className="pill info">Reservada</span> : <span className="pill ok">En uso</span>}</td>
                      {gestor && (
                        <td className="acciones-fila">
                          <button className="boton-icono" title="Editar" aria-label={`Editar VLAN ${v.numero}`} onClick={() => setEditando(v)}><Icono nombre="editar" /></button>
                          <button className="boton-icono peligro" title="Eliminar" aria-label={`Eliminar VLAN ${v.numero}`} onClick={async () => {
                            if (window.confirm(`¿Eliminar la VLAN ${v.numero} (${v.nombre}) de la documentación? No se toca nada en los equipos.`)) {
                              await api(`/vlans/${v.id}`, { metodo: "DELETE" });
                              recargar();
                            }
                          }}><Icono nombre="papelera" /></button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            ) : (
              <div className="lista-redes">
                {grupoActual.vlans.map((v, i) => {
                  const aca = v.equipos.filter((e) => e.equipo_id === grupoActual.equipoId);
                  return (
                    <div key={v.id} className="fila-red fila-entra" style={{ animationDelay: `${Math.min(i, 15) * 20}ms` }}>
                      <div className="fila-red-principal">
                        <span className={v.reservada ? "vlan-id reservada" : "vlan-id"}>{v.numero}</span>
                        <span className="fila-red-texto">
                          <strong>{v.nombre}</strong>
                          {v.descripcion && <span className="tenue"> · {v.descripcion}</span>}
                        </span>
                      </div>
                      <div className="fila-red-uso" style={{ textAlign: "left" }}>
                        <span>{aca.map((e) => e.interfaz).filter(Boolean).join(", ") || <span className="tenue">sin interfaz</span>}</span>
                        {aca.some((e) => e.nombre_en_equipo && e.nombre_en_equipo !== v.nombre) && (
                          <span className="tenue">En el equipo: {aca.map((e) => e.nombre_en_equipo).filter(Boolean).join(", ")}</span>
                        )}
                      </div>
                      {gestor && (
                        <span className="acciones-fila">
                          <button className="boton-icono" title="Editar" aria-label={`Editar VLAN ${v.numero}`} onClick={() => setEditando(v)}><Icono nombre="editar" /></button>
                          <button className="boton-icono peligro" title={`Quitar de ${grupoActual.nombre}`} aria-label={`Quitar VLAN ${v.numero} de ${grupoActual.nombre}`} onClick={async () => {
                            for (const e of aca) await api(`/vlans/${v.id}/equipos/${e.equipo_id}?interfaz=${encodeURIComponent(e.interfaz)}`, { metodo: "DELETE" });
                            recargar();
                          }}>×</button>
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}
      {agregandoA && (
        <AgregarEquipo vlan={agregandoA} equipos={equipos ?? []} onCerrar={() => setAgregandoA(null)} onListo={() => { setAgregandoA(null); recargar(); }} />
      )}
      {editando && (
        <EditarVlan
          dominioId={dominioId}
          vlan={editando === "nueva" ? undefined : editando}
          equipos={equipos ?? []}
          onCerrar={() => setEditando(null)}
          onListo={() => { setEditando(null); recargar(); }}
        />
      )}
    </div>
  );
}

function EditarVlan(props: { dominioId: number; vlan?: Vlan; equipos: Equipo[]; onCerrar: () => void; onListo: () => void }) {
  const v = props.vlan;
  const [numero, setNumero] = useState("");
  const [nombre, setNombre] = useState(v?.nombre ?? "");
  const [descripcion, setDescripcion] = useState(v?.descripcion ?? "");
  const [reservada, setReservada] = useState(v?.reservada ?? false);
  const [equipo, setEquipo] = useState("");
  const [interfaz, setInterfaz] = useState("");
  return (
    <Modal titulo={v ? `Editar VLAN ${v.numero}` : "Agregar VLAN"} onCerrar={props.onCerrar}>
      <Formulario
        textoBoton={v ? "Guardar" : numero ? "Agregar" : "Agregar con el siguiente número libre"}
        onCancelar={props.onCerrar}
        onEnviar={async () => {
          if (v) {
            await api(`/vlans/${v.id}`, { metodo: "PATCH", cuerpo: { nombre, descripcion, reservada } });
          } else {
            await api(`/vlans/dominios/${props.dominioId}/vlans`, {
              metodo: "POST",
              cuerpo: {
                numero: numero ? Number(numero) : null,
                desde: 100,
                nombre,
                descripcion,
                reservada,
                equipos: equipo ? [{ equipo_id: Number(equipo), interfaz }] : [],
              },
            });
          }
          props.onListo();
        }}
      >
        <div className="formulario">
          {!v && (
            <Campo etiqueta="Número" ayuda="Vacío = el siguiente libre desde 100">
              <input type="number" min={1} max={4094} value={numero} onChange={(e) => setNumero(e.target.value)} />
            </Campo>
          )}
          <Campo etiqueta="Nombre"><input value={nombre} onChange={(e) => setNombre(e.target.value)} required placeholder="GESTION" /></Campo>
          <Campo etiqueta="Uso"><input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} placeholder="Gestión de equipos" /></Campo>
          {!v && (
            <>
              <Campo etiqueta="Equipo" ayuda="Opcional: dónde está configurada">
                <select value={equipo} onChange={(e) => setEquipo(e.target.value)}>
                  <option value="">Ninguno por ahora</option>
                  {props.equipos.map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
                </select>
              </Campo>
              {equipo && (
                <Campo etiqueta="Interfaz" ayuda="Opcional">
                  <input value={interfaz} onChange={(e) => setInterfaz(e.target.value)} placeholder="sfp-sfpplus1, bridge1…" />
                </Campo>
              )}
            </>
          )}
          <label className="casilla ancho"><input type="checkbox" checked={reservada} onChange={(e) => setReservada(e.target.checked)} /> Reservada (todavía sin uso)</label>
        </div>
      </Formulario>
    </Modal>
  );
}

function AgregarEquipo(props: { vlan: Vlan; equipos: Equipo[]; onCerrar: () => void; onListo: () => void }) {
  const [equipo, setEquipo] = useState(String(props.equipos[0]?.id ?? ""));
  const [interfaz, setInterfaz] = useState("");
  return (
    <Modal titulo={`VLAN ${props.vlan.numero} · ${props.vlan.nombre}`} onCerrar={props.onCerrar}>
      <Formulario
        textoBoton="Agregar"
        onCancelar={props.onCerrar}
        onEnviar={async () => {
          await api(`/vlans/${props.vlan.id}/equipos`, { metodo: "POST", cuerpo: { equipo_id: Number(equipo), interfaz } });
          props.onListo();
        }}
      >
        <Campo etiqueta="Equipo">
          <select value={equipo} onChange={(e) => setEquipo(e.target.value)} required>
            {props.equipos.map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Interfaz" ayuda="Opcional: en qué puerto o bridge está">
          <input value={interfaz} onChange={(e) => setInterfaz(e.target.value)} placeholder="sfp-sfpplus1, bridge1…" />
        </Campo>
      </Formulario>
    </Modal>
  );
}
