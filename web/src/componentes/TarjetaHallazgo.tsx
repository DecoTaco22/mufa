import type { Hallazgo } from "../tipos";
import { BotonCopiar, Severidad } from "./ui";

/** Un hallazgo en capas: resumen para todos, evidencia y solución, y el porqué para quien aprende. */
export function TarjetaHallazgo({ hallazgo, equipo }: { hallazgo: Hallazgo; equipo?: string }) {
  const solucion = hallazgo.remediacion.join("\n");
  return (
    <article className="tarjeta pila" id={`hallazgo-${hallazgo.id}`}>
      <div className="fila" style={{ alignItems: "center", gap: 10 }}>
        <Severidad valor={hallazgo.severidad} />
        <span className="mono tenue">{hallazgo.check_id}</span>
        {equipo && <span className="tenue">· {equipo}</span>}
      </div>
      <h3 style={{ fontSize: 17 }}>{hallazgo.titulo}</h3>
      <div>
        <div className="tenue" style={{ fontSize: 12, marginBottom: 4 }}>Evidencia</div>
        <div>{hallazgo.evidencia}</div>
      </div>
      <div>
        <div className="entre" style={{ marginBottom: 6 }}>
          <span className="tenue" style={{ fontSize: 12 }}>Solución</span>
          <BotonCopiar texto={solucion} />
        </div>
        <pre>{solucion}</pre>
      </div>
      <details>
        <summary>¿Por qué importa?</summary>
        <p style={{ marginBottom: 0 }}>{hallazgo.impacto}</p>
        {hallazgo.referencia && (
          <p className="tenue" style={{ marginBottom: 0, fontSize: 12 }}>Referencia: {hallazgo.referencia}</p>
        )}
      </details>
    </article>
  );
}
