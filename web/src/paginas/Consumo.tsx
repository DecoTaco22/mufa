// Consumo por cliente (mufa Pro): cuánto baja y sube cada IP de cliente, desde NetFlow / IPFIX.
import { LOCALE } from "../i18n";
import { useState } from "react";
import { api } from "../api";
import { Campo, Cargando, Encabezado, Formulario, Segmentado, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import { fecha, hace, puede, useDatos } from "../util";

interface EstadoColector {
  escuchando: boolean;
  puerto: number;
  error: string;
  paquetes: number;
  flujos: number;
  rechazados: number;
  ultimo: string | null;
  exportadores: string[];
}

interface Ajustes {
  activo: boolean;
  puerto: number;
  redes: string[];
  estado: EstadoColector | null;
}

interface Cliente {
  ip: string;
  cliente: string;
  bajada: number;
  subida: number;
}

interface Detalle {
  ip: string;
  cliente: string;
  horas: { hora: string; bajada: number; subida: number }[];
}

function bytes(n: number): string {
  const unidades = ["B", "KB", "MB", "GB", "TB", "PB"];
  let v = n;
  let i = 0;
  while (v >= 1000 && i < unidades.length - 1) {
    v /= 1000;
    i++;
  }
  return `${v.toLocaleString(LOCALE, { maximumFractionDigits: v < 10 ? 1 : 0 })} ${unidades[i]}`;
}

export function Consumo() {
  const { usuario } = useSesion();
  const gestiona = puede(usuario?.rol, "gestionar_equipos");
  const ajustes = useDatos<Ajustes>("/pro/consumo/ajustes");
  const [dias, setDias] = useState("1");
  const ranking = useDatos<Cliente[]>(`/pro/consumo?dias=${dias}`);
  const [elegida, setElegida] = useState<string | null>(null);
  const maximo = Math.max(1, ...(ranking.datos ?? []).map((c) => c.bajada + c.subida));

  return (
    <>
      <Encabezado
        titulo="Consumo por cliente"
        subtitulo="Cuánto baja y sube cada cliente, desde los flujos (NetFlow / IPFIX) que manda tu router. Sin guardar a qué sitios entra nadie."
      />
      <div className="fila" style={{ alignItems: "flex-start" }}>
        <div className="crece pila" style={{ gap: 14, minWidth: 0 }}>
          <Tarjeta
            titulo="Los que más consumen"
            acciones={
              <Segmentado
                etiqueta="Período"
                valor={dias}
                onCambio={setDias}
                opciones={[
                  { valor: "1", texto: "24 h" },
                  { valor: "7", texto: "7 días" },
                  { valor: "30", texto: "30 días" },
                ]}
              />
            }
            sinRelleno
          >
            {!ranking.datos && <Cargando />}
            {ranking.datos && ranking.datos.length === 0 && (
              <Vacio titulo="Todavía no hay datos">
                Activa la recepción de flujos y configura tu router para que los mande a mufa (a la derecha).
              </Vacio>
            )}
            {ranking.datos && ranking.datos.length > 0 && (
              <div className="tabla-caja">
                <table>
                  <thead><tr><th>Cliente</th><th>Baja</th><th>Sube</th><th style={{ width: "30%" }} /></tr></thead>
                  <tbody>
                    {ranking.datos.map((c) => (
                      <tr key={c.ip} className="clic" onClick={() => setElegida(c.ip)} style={{ cursor: "pointer" }}>
                        <td>
                          <span translate="no" style={{ fontWeight: 500 }}>{c.cliente || "—"}</span>
                          <div className="tenue mono" style={{ fontSize: 12 }}>{c.ip}</div>
                        </td>
                        <td className="mono">{bytes(c.bajada)}</td>
                        <td className="mono">{bytes(c.subida)}</td>
                        <td>
                          <div className="barra-uso"><div style={{ width: `${(100 * (c.bajada + c.subida)) / maximo}%` }} /></div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Tarjeta>
          {elegida && <DetalleCliente ip={elegida} />}
        </div>
        <div className="crece" style={{ maxWidth: 420 }}>
          {ajustes.datos ? (
            <Configurar key={JSON.stringify(ajustes.datos)} inicial={ajustes.datos} gestiona={gestiona} onGuardado={ajustes.recargar} />
          ) : (
            <Cargando />
          )}
        </div>
      </div>
    </>
  );
}

function DetalleCliente({ ip }: { ip: string }) {
  const { datos } = useDatos<Detalle>(`/pro/consumo/${ip}?dias=7`);
  if (!datos) return <Cargando />;
  const maximo = Math.max(1, ...datos.horas.map((h) => h.bajada + h.subida));
  return (
    <Tarjeta titulo={<span translate="no">{datos.cliente || datos.ip}</span>}>
      <div className="tenue" style={{ fontSize: 12, marginBottom: 8 }}>Últimos 7 días, hora por hora</div>
      <svg viewBox={`0 0 ${Math.max(datos.horas.length, 1) * 4} 100`} preserveAspectRatio="none" style={{ width: "100%", height: 120 }} role="img" aria-label="Consumo por hora">
        {datos.horas.map((h, i) => {
          const alto = (100 * h.bajada) / maximo;
          const altoSubida = (100 * h.subida) / maximo;
          return (
            <g key={h.hora}>
              <rect x={i * 4} y={100 - alto - altoSubida} width={3} height={alto} fill="var(--azul, #0a84ff)"><title>{`${fecha(h.hora)} · ↓ ${bytes(h.bajada)} · ↑ ${bytes(h.subida)}`}</title></rect>
              <rect x={i * 4} y={100 - altoSubida} width={3} height={altoSubida} fill="var(--ok)" />
            </g>
          );
        })}
      </svg>
      <div className="tenue" style={{ fontSize: 12 }}>
        <span style={{ color: "var(--azul, #0a84ff)" }}>■</span> Baja · <span style={{ color: "var(--ok)" }}>■</span> Sube
      </div>
    </Tarjeta>
  );
}

function Configurar({ inicial, gestiona, onGuardado }: { inicial: Ajustes; gestiona: boolean; onGuardado: () => void }) {
  const { datos: prefijos } = useDatos<{ prefijo: string; descripcion: string }[]>("/prefijos");
  const [activo, setActivo] = useState(inicial.activo);
  const [puerto, setPuerto] = useState(String(inicial.puerto));
  const [redes, setRedes] = useState(inicial.redes.join("\n"));
  const e = inicial.estado;
  const ip = window.location.hostname;

  return (
    <Tarjeta titulo="Recepción de flujos">
      {e?.error && <div className="aviso error" style={{ marginBottom: 12 }}>{e.error}</div>}
      {e?.escuchando && (
        <div className="aviso ok" style={{ marginBottom: 12 }}>
          Escuchando en UDP {e.puerto}. {e.ultimo ? `Último flujo ${hace(e.ultimo)} de ${e.exportadores.join(", ")}.` : "Todavía no llegó ningún flujo."}
          {e.rechazados > 0 && ` Se ignoraron ${e.rechazados} paquetes de IPs que no son equipos de mufa.`}
        </div>
      )}
      <Formulario
        textoBoton="Guardar"
        onEnviar={async () => {
          if (!gestiona) throw new Error("Tu rol no puede cambiar esto.");
          const lista = redes.split(/[\s,]+/).map((r) => r.trim()).filter(Boolean);
          await api("/pro/consumo/ajustes", { metodo: "PUT", cuerpo: { activo, puerto: Number(puerto), redes: lista } });
          onGuardado();
        }}
      >
        <Campo etiqueta="Redes de los clientes" ancho ayuda="Una por línea. Solo se cuenta el tráfico de estas redes.">
          <textarea value={redes} onChange={(ev) => setRedes(ev.target.value)} rows={4} placeholder="100.64.0.0/16" className="mono" />
        </Campo>
        {prefijos && prefijos.length > 0 && (
          <div className="fila" style={{ gap: 6, flexWrap: "wrap" }}>
            {prefijos.slice(0, 12).map((p) => (
              <button
                key={p.prefijo}
                type="button"
                className="boton chico"
                title={p.descripcion}
                onClick={() => !redes.split(/\s+/).includes(p.prefijo) && setRedes(`${redes.trim()}\n${p.prefijo}`.trim())}
              >
                <span translate="no">+ {p.prefijo}</span>
              </button>
            ))}
          </div>
        )}
        <Campo etiqueta="Puerto UDP">
          <input type="number" min={1024} max={65535} value={puerto} onChange={(ev) => setPuerto(ev.target.value)} />
        </Campo>
        <label className="casilla ancho"><input type="checkbox" checked={activo} onChange={(ev) => setActivo(ev.target.checked)} /> Recibir flujos</label>
      </Formulario>
      <h3 style={{ fontSize: 14, marginBottom: 4 }}>En el router (lo haces tú; mufa no toca el equipo)</h3>
      <p className="tenue" style={{ fontSize: 12, marginTop: 0 }}>MikroTik RouterOS:</p>
      <pre className="mono" style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>
        {`/ip traffic-flow set enabled=yes interfaces=all\n/ip traffic-flow target add dst-address=${ip} port=${inicial.puerto} version=9`}
      </pre>
      <p className="tenue" style={{ fontSize: 12 }}>Cisco IOS:</p>
      <pre className="mono" style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>
        {`flow exporter MUFA\n destination ${ip}\n transport udp ${inicial.puerto}`}
      </pre>
      <p className="tenue" style={{ fontSize: 12, marginBottom: 0 }}>
        mufa acepta flujos solo de las IPs de gestión de tus equipos. Los clientes se nombran con la descripción de su IP en el IPAM.
        {e?.ultimo && ` Actualizado ${fecha(e.ultimo)}.`}
      </p>
    </Tarjeta>
  );
}
