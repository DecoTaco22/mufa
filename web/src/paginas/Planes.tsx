import { Encabezado, Tarjeta } from "../componentes/ui";
import type { Licencia } from "../tipos";
import { useDatos } from "../util";
import { ResumenPro, SITIO } from "./Pro";


// Lo mismo que docs/PLANES.md. Las funciones Pro se publican por etapas.
const FILAS: [string, string, string][] = [
  ["Equipos", "10", "Ilimitados"],
  ["Usuarios", "3", "Ilimitados"],
  ["Interfaces vigiladas (caída y saturación)", "5", "Ilimitadas"],
  ["Historial de tráfico", "7 días", "1 año"],
  ["Monitoreo, auditoría, respaldos, IPAM, VLANs, fibra, herramientas", "✓", "✓"],
  ["Alertas con tu propio bot y correo", "✓", "✓"],
  ["mufa Avisos: bot de Telegram y correo listos", "Solo para ti", "Todo tu equipo y grupos"],
  ["Escalamiento, guardias y «Lo tomo yo»", "", "✓"],
  ["Ventanas de mantenimiento", "", "✓"],
  ["Predicción de capacidad", "", "✓"],
  ["OLT GPON (Huawei, ZTE)", "", "✓"],
  ["Informes en PDF con tu logo", "", "✓"],
  ["Página de estado pública", "", "✓"],
  ["Respaldo externo cifrado", "", "✓"],
  ["Soporte", "Comunidad", "1 día hábil"],
];

export function Planes() {
  const { datos: licencia } = useDatos<Licencia>("/licencia");
  return (
    <>
      <Encabezado
        titulo="Planes"
        subtitulo={licencia ? `Tu plan: ${licencia.plan}` : undefined}
      />
      <ResumenPro />
      <div className="grilla" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        <Tarjeta titulo="Gratis">
          <div className="pila">
            <div style={{ fontSize: 30, fontWeight: 700 }}>$0</div>
            <p className="tenue" style={{ margin: 0 }}>Para ordenar y vigilar una red chica, sin tarjeta y sin vencimiento.</p>
          </div>
        </Tarjeta>
        <Tarjeta titulo={<>Pro <span className="insignia-pro">Recomendado</span></>}>
          <div className="pila">
            <div><span style={{ fontSize: 30, fontWeight: 700 }}>$29</span> <span className="tenue">al mes · $290 al año</span></div>
            <p className="tenue" style={{ margin: 0 }}>Equipos ilimitados y alertas que llegan a quien tiene que atenderlas, a cualquier hora.</p>
            <div>
              <a className="boton primario" href={`${SITIO}/fundador`} target="_blank" rel="noreferrer">Ser fundador</a>
            </div>
            <span className="tenue" style={{ fontSize: 12 }}>
              Pro está en camino. Los fundadores lo usan primero y a precio de fundador.
            </span>
          </div>
        </Tarjeta>
        <Tarjeta titulo={<>mufa Edge <span className="pill medio">En desarrollo</span></>}>
          <div className="pila">
            <div style={{ fontSize: 30, fontWeight: 700 }}>Por Gbps</div>
            <p className="tenue" style={{ margin: 0 }}>
              Control de tráfico por cliente en tu propio servidor: colas por plan para miles de clientes, DHCP y la calidad
              real de cada uno. Sin cajas cerradas ni precios de multinacional.
            </p>
            <div>
              <a className="boton" href={`${SITIO}/?tipo=edge#edge`} target="_blank" rel="noreferrer">Quiero el piloto</a>
            </div>
          </div>
        </Tarjeta>
        <Tarjeta titulo="Ingeniería">
          <div className="pila">
            <div style={{ fontSize: 30, fontWeight: 700 }}>A cotizar</div>
            <p className="tenue" style={{ margin: 0 }}>
              Un ingeniero en telecomunicaciones para tu red: puesta en marcha de mufa, diseño y auditoría (MikroTik, Cisco,
              Huawei), colas, BGP, FTTH y capacitación.
            </p>
            <div>
              <a className="boton" href={`${SITIO}/?tipo=servicio#servicios`} target="_blank" rel="noreferrer">Ver servicios</a>
            </div>
          </div>
        </Tarjeta>
      </div>
      <Tarjeta sinRelleno>
        <div className="tabla-caja">
          <table className="tabla-planes">
            <thead><tr><th /><th>Gratis</th><th>Pro</th></tr></thead>
            <tbody>
              {FILAS.map(([funcion, gratis, pro]) => (
                <tr key={funcion}><td>{funcion}</td><td>{gratis || <span className="tenue">—</span>}</td><td>{pro}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Tarjeta>
      <p className="tenue" style={{ fontSize: 12 }}>
        Para operadores con NOC propio (AAA con TACACS+ o RADIUS, SSO, soporte en 4 horas, varios clientes separados), escríbenos
        desde Ingeniería. Precios en dólares.
      </p>
      <p className="tenue" style={{ fontSize: 13 }}>
        ¿Qué le falta a mufa? <a href={`${SITIO}/#ideas`} target="_blank" rel="noreferrer">Cuéntanos tu idea</a>.
      </p>
    </>
  );
}
