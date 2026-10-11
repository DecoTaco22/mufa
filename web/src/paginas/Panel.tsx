import { Link } from "react-router";
import { Cargando, Encabezado, MensajeError, Severidad, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Panel as DatosPanel } from "../tipos";
import { hace, puede, useDatos } from "../util";

export function Panel() {
  const { usuario } = useSesion();
  const { datos, error, cargando } = useDatos<DatosPanel>("/panel");

  if (cargando && !datos) return <Cargando />;
  if (!datos) return <MensajeError mensaje={error} />;

  const sev = datos.hallazgos_por_severidad;
  const criticos = sev["crítico"] ?? 0;
  const altos = sev["alto"] ?? 0;

  return (
    <>
      <Encabezado
        titulo="Panel"
        subtitulo={`Plan ${datos.plan} · ${datos.max_equipos === null ? `${datos.equipos} equipos` : `${datos.equipos} de ${datos.max_equipos} equipos`}`}
        acciones={
          puede(usuario?.rol, "gestionar_equipos") && (
            <Link className="boton primario" to="/equipos?nuevo=1">Agregar equipo</Link>
          )
        }
      />

      {datos.equipos === 0 ? (
        <Tarjeta>
          <Vacio titulo="Todavía no hay equipos">
            <p>Agrega tu primer router, switch u OLT para empezar a monitorearlo y auditarlo.</p>
            <p>
              ¿Solo quieres probar? <Link to="/hallazgos">Sube un export de configuración</Link> y mira qué encuentra mufa.
            </p>
          </Vacio>
        </Tarjeta>
      ) : (
        <div className="grilla">
          <Tarjeta>
            <div className="kpi">
              <div className="etiqueta">Equipos en línea</div>
              <div className="valor">
                {datos.en_linea}
                <small> / {datos.monitoreados}</small>
              </div>
              <div className={datos.caidos.length ? "nota texto-rojo" : "nota"}>
                {datos.caidos.length ? `${datos.caidos.length} caído(s)` : `${datos.monitoreados} con SNMP`}
              </div>
            </div>
          </Tarjeta>
          <Tarjeta>
            <div className="kpi">
              <div className="etiqueta">Seguridad de la red</div>
              <div className={datos.puntaje_red !== null && datos.puntaje_red < 60 ? "valor texto-rojo" : "valor"}>
                {datos.puntaje_red ?? "—"}
                {datos.puntaje_red !== null && <small> / 100</small>}
              </div>
              <div className={criticos ? "nota texto-rojo" : "nota"}>
                {datos.puntaje_red === null ? "Audita un equipo para calcularla" : `${criticos} críticos · ${altos} altos · ${sev["medio"] ?? 0} medios`}
              </div>
            </div>
          </Tarjeta>
          <Tarjeta>
            <div className="kpi">
              <div className="etiqueta">Respaldos al día</div>
              <div className="valor">
                {datos.respaldos_al_dia}
                <small> / {datos.respaldables}</small>
              </div>
              <div className="nota"><Link to="/respaldos">Todos los días, a la hora que elijas</Link></div>
            </div>
          </Tarjeta>
          <Tarjeta>
            <div className="kpi">
              <div className="etiqueta">Canales de alerta</div>
              <div className="valor">{datos.canales_de_alerta}</div>
              <div className="nota">
                {datos.canales_de_alerta ? "Telegram, correo o webhook" : <Link to="/alertas">Configurar alertas</Link>}
              </div>
            </div>
          </Tarjeta>
        </div>
      )}

      {datos.equipos > 0 && (
        <div className="fila">
          <div className="crece" style={{ flexGrow: 2 }}>
            <Tarjeta titulo="Hallazgos que requieren atención" acciones={<Link to="/hallazgos">Ver todos</Link>} sinRelleno>
              {datos.hallazgos_principales.length === 0 ? (
                <Vacio titulo="Sin hallazgos abiertos">Los equipos se auditan solos una vez al día.</Vacio>
              ) : (
                <div className="tabla-caja">
                  <table>
                    <thead>
                      <tr><th>Severidad</th><th>Hallazgo</th><th>Equipo</th></tr>
                    </thead>
                    <tbody>
                      {datos.hallazgos_principales.map((h) => (
                        <tr key={h.hallazgo.id}>
                          <td><Severidad valor={h.hallazgo.severidad} /></td>
                          <td>
                            <Link to={`/hallazgos?id=${h.hallazgo.id}`}>{h.hallazgo.titulo}</Link>
                            <div className="tenue mono">{h.hallazgo.check_id}</div>
                          </td>
                          <td><Link to={`/equipos/${h.equipo_id}`}>{h.equipo}</Link></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Tarjeta>
          </div>
          <div className="crece">
            <Tarjeta titulo="Equipos que no responden">
              {datos.caidos.length === 0 ? (
                <p className="tenue" style={{ margin: 0 }}>Todos los equipos monitoreados responden.</p>
              ) : (
                <div className="pila">
                  {datos.caidos.map((c) => (
                    <div key={c.equipo_id}>
                      <Link to={`/equipos/${c.equipo_id}`} style={{ fontWeight: 600 }}>{c.nombre}</Link>
                      <div className="tenue" style={{ fontSize: 12 }}>
                        {c.alcanzable ? "Encendido (responde a ping), pero sin SNMP" : `En línea por última vez ${hace(c.ultimo_en_linea)}`}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Tarjeta>
          </div>
        </div>
      )}
    </>
  );
}
