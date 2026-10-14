// OLT GPON (mufa Pro): las ONU de cada OLT, su señal y los cortes por puerto.
import { useState } from "react";
import { api } from "../api";
import { Campo, Cargando, Encabezado, Formulario, Modal, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Equipo } from "../tipos";
import { hace, puede, useDatos } from "../util";

type EstadoOnu = "en_linea" | "sin_senal" | "sin_energia" | "desconectada" | "otro";

interface Conteo {
  total: number;
  en_linea: number;
  sin_senal: number;
  sin_energia: number;
  desconectada: number;
  otro: number;
  senal_baja: number;
}

interface OltInfo {
  equipo_id: number;
  equipo: string;
  ip: string;
  perfil: string;
  perfil_titulo: string;
  umbral_rx_dbm: number;
  ultimo_sondeo: string | null;
  error: string;
  onus: Conteo;
}

interface Puerto {
  pon_if_index: number;
  puerto: string;
  onus: Conteo;
  rx_promedio: number | null;
  rx_peor: number | null;
}

interface Onu {
  id: number;
  pon_if_index: number;
  puerto: string;
  onu_id: number;
  nombre: string;
  serie: string;
  estado: EstadoOnu;
  causa: string;
  rx_dbm: number | null;
  tx_dbm: number | null;
  distancia_m: number | null;
  cambio: string;
  senal_baja: boolean;
}

const ESTADOS: Record<EstadoOnu, { texto: string; clase: string }> = {
  en_linea: { texto: "En línea", clase: "ok" },
  sin_senal: { texto: "Sin señal", clase: "critico" },
  sin_energia: { texto: "Sin energía", clase: "alto" },
  desconectada: { texto: "Desconectada", clase: "medio" },
  otro: { texto: "Otro", clase: "gris" },
};

function dbm(v: number | null): string {
  return v === null ? "—" : `${v.toLocaleString("es", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} dBm`;
}

function caidas(c: Conteo): number {
  return c.total - c.en_linea;
}

export function OltGpon() {
  const { usuario } = useSesion();
  const { datos, cargando, recargar } = useDatos<OltInfo[]>("/pro/olt");
  const [elegida, setElegida] = useState<number | null>(null);
  const [agregando, setAgregando] = useState(false);
  const gestiona = puede(usuario?.rol, "gestionar_equipos");
  const actual = datos?.find((o) => o.equipo_id === elegida) ?? datos?.[0] ?? null;

  return (
    <>
      <Encabezado
        titulo="OLT GPON"
        subtitulo="Cada ONU, su señal y sus caídas, leídas por SNMP en solo lectura cada 15 minutos."
        acciones={gestiona && <button className="boton primario" onClick={() => setAgregando(true)}>Agregar OLT</button>}
      />
      {agregando && <AgregarOlt onCerrar={() => setAgregando(false)} onListo={(id) => { setAgregando(false); setElegida(id); recargar(); }} />}
      {cargando && !datos ? (
        <Cargando />
      ) : !datos?.length ? (
        <Tarjeta>
          <Vacio titulo="Todavía no hay OLT">
            <p className="tenue" style={{ maxWidth: 520, margin: "0 auto" }}>
              Agrega tu OLT Huawei (MA5600T, MA5800) o ZTE (C300, C320) como equipo con SNMP y después márcala aquí como
              OLT: mufa descubre los puertos PON y sus ONU.
            </p>
          </Vacio>
        </Tarjeta>
      ) : (
        <div className="pila" style={{ gap: 14 }}>
          {datos.length > 1 && (
            <div className="fila" style={{ gap: 8, flexWrap: "wrap" }}>
              {datos.map((o) => (
                <button key={o.equipo_id} className={`boton chico${actual?.equipo_id === o.equipo_id ? " primario" : ""}`} onClick={() => setElegida(o.equipo_id)}>
                  {o.equipo}
                  {caidas(o.onus) > 0 && <span className="pill critico" style={{ marginLeft: 6 }}>{caidas(o.onus)}</span>}
                </button>
              ))}
            </div>
          )}
          {actual && <DetalleOlt key={actual.equipo_id} olt={actual} gestiona={gestiona} onCambio={recargar} />}
        </div>
      )}
    </>
  );
}

function DetalleOlt({ olt, gestiona, onCambio }: { olt: OltInfo; gestiona: boolean; onCambio: () => void }) {
  const { datos: puertos, recargar: recargarPuertos } = useDatos<Puerto[]>(`/pro/olt/${olt.equipo_id}/puertos`);
  const [puerto, setPuerto] = useState<number | null>(null);
  const [filtro, setFiltro] = useState("");
  const [buscar, setBuscar] = useState("");
  const [leyendo, setLeyendo] = useState(false);
  const parametros = new URLSearchParams();
  if (puerto !== null) parametros.set("puerto", String(puerto));
  if (filtro === "senal_baja") parametros.set("senal_baja", "true");
  else if (filtro) parametros.set("estado", filtro);
  if (buscar) parametros.set("q", buscar);
  const { datos: onus } = useDatos<Onu[]>(`/pro/olt/${olt.equipo_id}/onus?${parametros}`);
  const c = olt.onus;

  return (
    <>
      <div className="capacidad-resumen">
        <div className="tarjeta capacidad-cifra ok"><span className="tenue">En línea</span><strong>{c.en_linea}</strong><span className="tenue" style={{ fontSize: 12 }}>de {c.total} ONU</span></div>
        <div className={`tarjeta capacidad-cifra ${c.sin_senal ? "critico" : ""}`}><span className="tenue">Sin señal (LOS)</span><strong>{c.sin_senal}</strong></div>
        <div className={`tarjeta capacidad-cifra ${c.sin_energia ? "alto" : ""}`}><span className="tenue">Sin energía</span><strong>{c.sin_energia}</strong></div>
        <div className={`tarjeta capacidad-cifra ${c.senal_baja ? "medio" : ""}`}><span className="tenue">Señal baja</span><strong>{c.senal_baja}</strong><span className="tenue" style={{ fontSize: 12 }}>bajo {olt.umbral_rx_dbm} dBm</span></div>
      </div>

      <Tarjeta
        titulo={<>{olt.equipo} <span className="tenue" style={{ fontWeight: 400 }}>· {olt.perfil_titulo} · {olt.ip}</span></>}
        acciones={
          gestiona && (
            <div className="fila" style={{ gap: 8 }}>
              <button
                className="boton chico"
                disabled={leyendo}
                onClick={async () => {
                  setLeyendo(true);
                  try {
                    await api(`/pro/olt/${olt.equipo_id}/sondear`, { metodo: "POST" });
                    onCambio();
                    recargarPuertos();
                  } finally {
                    setLeyendo(false);
                  }
                }}
              >
                {leyendo ? "Leyendo…" : "Leer ahora"}
              </button>
              <button
                className="boton chico peligro"
                onClick={async () => {
                  if (!window.confirm(`¿Dejar de leer ${olt.equipo} como OLT? El equipo sigue en mufa.`)) return;
                  await api(`/pro/olt/${olt.equipo_id}`, { metodo: "DELETE" });
                  onCambio();
                }}
              >
                Quitar
              </button>
            </div>
          )
        }
      >
        <div className="tenue" style={{ fontSize: 13 }}>
          {olt.ultimo_sondeo ? `Leída ${hace(olt.ultimo_sondeo)}.` : "Todavía no se leyó."}
        </div>
        {olt.error && <div className="aviso atencion" style={{ marginTop: 10 }}>{olt.error}</div>}
      </Tarjeta>

      {puertos && puertos.length > 0 && (
        <Tarjeta titulo="Puertos PON" sinRelleno>
          <div className="tabla-caja">
            <table>
              <thead><tr><th>Puerto</th><th>ONU</th><th>Caídas</th><th>Señal promedio</th><th>Peor señal</th></tr></thead>
              <tbody>
                {puertos.map((p) => {
                  const activo = puerto === p.pon_if_index;
                  return (
                    <tr key={p.pon_if_index} className={activo ? "clic activa" : "clic"} onClick={() => setPuerto(activo ? null : p.pon_if_index)}>
                      <td className="mono" style={{ fontWeight: 500 }}>{p.puerto}</td>
                      <td>{p.onus.en_linea} / {p.onus.total}</td>
                      <td>
                        {caidas(p.onus) === 0 ? <span className="tenue">—</span> : (
                          <span className={`pill ${caidas(p.onus) * 2 >= p.onus.total ? "critico" : "medio"}`}>{caidas(p.onus)}</span>
                        )}
                      </td>
                      <td>{dbm(p.rx_promedio)}</td>
                      <td className={p.rx_peor !== null && p.rx_peor < olt.umbral_rx_dbm ? "texto-alerta" : ""}>{dbm(p.rx_peor)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Tarjeta>
      )}

      <Tarjeta
        titulo={puerto !== null ? `ONU de ${puertos?.find((p) => p.pon_if_index === puerto)?.puerto ?? "el puerto"}` : "ONU"}
        acciones={
          <div className="fila" style={{ gap: 8, flexWrap: "nowrap" }}>
            <input placeholder="Nombre o serie" value={buscar} onChange={(e) => setBuscar(e.target.value)} style={{ width: 170 }} />
            <select value={filtro} onChange={(e) => setFiltro(e.target.value)} aria-label="Filtrar ONU" style={{ width: "auto" }}>
              <option value="">Todas</option>
              <option value="caidas">Caídas</option>
              <option value="sin_senal">Sin señal</option>
              <option value="sin_energia">Sin energía</option>
              <option value="senal_baja">Señal baja</option>
            </select>
          </div>
        }
        sinRelleno
      >
        <div className="tabla-caja">
          <table>
            <thead><tr><th>ONU</th><th>Puerto</th><th>Estado</th><th>Recibe</th><th>Distancia</th><th>Desde</th></tr></thead>
            <tbody>
              {onus?.map((o) => (
                <tr key={o.id}>
                  <td style={{ fontWeight: 500 }}>
                    {o.nombre || `ONU ${o.onu_id}`}
                    <div className="tenue mono" style={{ fontWeight: 400 }}>{o.serie || "—"} · {o.onu_id}</div>
                  </td>
                  <td className="mono">{o.puerto}</td>
                  <td>
                    <span className={`pill ${ESTADOS[o.estado].clase}`}>{ESTADOS[o.estado].texto}</span>
                    {o.causa && <div className="tenue" style={{ fontSize: 12, marginTop: 4 }}>{o.causa}</div>}
                  </td>
                  <td className={o.senal_baja ? "texto-alerta" : ""}>{dbm(o.rx_dbm)}</td>
                  <td className="tenue">{o.distancia_m === null ? "—" : `${(o.distancia_m / 1000).toLocaleString("es", { maximumFractionDigits: 2 })} km`}</td>
                  <td className="tenue">{hace(o.cambio)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {onus && onus.length === 0 && <p className="tenue" style={{ padding: 16, margin: 0 }}>Ninguna ONU con ese filtro.</p>}
        </div>
      </Tarjeta>
    </>
  );
}

function AgregarOlt({ onCerrar, onListo }: { onCerrar: () => void; onListo: (id: number) => void }) {
  const { datos: equipos } = useDatos<Equipo[]>("/equipos");
  const [equipo, setEquipo] = useState("");
  const [perfil, setPerfil] = useState("");
  const [umbral, setUmbral] = useState("-27");
  const conSnmp = equipos?.filter((e) => e.snmp) ?? [];
  return (
    <Modal titulo="Agregar OLT" onCerrar={onCerrar}>
      <Formulario
        textoBoton="Agregar y leer"
        onEnviar={async () => {
          const r = await api<OltInfo>("/pro/olt", {
            metodo: "POST",
            cuerpo: { equipo_id: Number(equipo), perfil: perfil || null, umbral_rx_dbm: Number(umbral) },
          });
          onListo(r.equipo_id);
        }}
      >
        <Campo etiqueta="Equipo" ayuda={conSnmp.length ? "La OLT tiene que estar agregada como equipo, con SNMP." : "Primero agrega la OLT en Equipos, con SNMP."}>
          <select value={equipo} onChange={(e) => setEquipo(e.target.value)} required>
            <option value="">Elegir…</option>
            {conSnmp.map((e) => <option key={e.id} value={e.id}>{e.nombre} · {e.ip_gestion}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Marca" ayuda="Sin elegir, mufa usa la marca del equipo.">
          <select value={perfil} onChange={(e) => setPerfil(e.target.value)}>
            <option value="">Según el equipo</option>
            <option value="huawei">Huawei MA5600T / MA5800</option>
            <option value="zte">ZTE C300 / C320</option>
          </select>
        </Campo>
        <Campo etiqueta="Avisar si una ONU recibe menos de (dBm)" ayuda="Para GPON clase B+, -27 dBm deja margen antes del límite de -28.">
          <input type="number" step="0.5" min={-40} max={-10} value={umbral} onChange={(e) => setUmbral(e.target.value)} required />
        </Campo>
      </Formulario>
    </Modal>
  );
}
