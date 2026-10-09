import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { FormularioEquipo } from "../componentes/FormularioEquipo";
import { Cargando, Encabezado, MensajeError, EstadoEnLinea, Puntaje, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Equipo, Marca } from "../tipos";
import { hace, puede, useDatos } from "../util";

export function Equipos() {
  const { usuario } = useSesion();
  const navegar = useNavigate();
  const [parametros, setParametros] = useSearchParams();
  const { datos, error, cargando } = useDatos<Equipo[]>("/equipos");
  const { datos: marcas } = useDatos<Marca[]>("/marcas");
  const [buscar, setBuscar] = useState("");
  const nuevo = parametros.get("nuevo") === "1";

  const nombreMarca = (m: string) => marcas?.find((x) => x.marca === m)?.nombre ?? m;
  const filtro = buscar.trim().toLowerCase();
  const visibles = (datos ?? []).filter(
    (e) => !filtro || e.nombre.toLowerCase().includes(filtro) || e.ip_gestion.includes(filtro) || e.marca.includes(filtro),
  );

  return (
    <>
      <Encabezado
        titulo="Equipos"
        subtitulo={datos ? `${datos.length} equipos` : undefined}
        acciones={
          puede(usuario?.rol, "gestionar_equipos") && (
            <button className="boton primario" onClick={() => setParametros({ nuevo: "1" })}>Agregar equipo</button>
          )
        }
      />
      <MensajeError mensaje={error} />
      <input
        type="search"
        placeholder="Buscar por nombre, IP o marca"
        value={buscar}
        onChange={(e) => setBuscar(e.target.value)}
        style={{ maxWidth: 360 }}
        aria-label="Buscar equipos"
      />
      <Tarjeta sinRelleno>
        {cargando && !datos ? (
          <Cargando />
        ) : visibles.length === 0 ? (
          <Vacio titulo={datos?.length ? "Ningún equipo coincide" : "Todavía no hay equipos"} />
        ) : (
          <div className="tabla-caja">
            <table>
              <thead>
                <tr>
                  <th>Estado</th><th>Nombre</th><th>Marca</th><th>IP de gestión</th><th>Seguridad</th><th>Hallazgos</th><th>Último respaldo</th>
                </tr>
              </thead>
              <tbody>
                {visibles.map((e) => (
                  <tr key={e.id} className="clic" onClick={() => navegar(`/equipos/${e.id}`)}>
                    <td><EstadoEnLinea valor={e.snmp ? e.en_linea : null} alcanzable={e.alcanzable} /></td>
                    <td style={{ fontWeight: 500 }}>
                      {e.nombre}
                      {e.modelo && <div className="tenue" style={{ fontWeight: 400 }}>{e.modelo}</div>}
                    </td>
                    <td>{nombreMarca(e.marca)}</td>
                    <td className="mono">{e.ip_gestion}</td>
                    <td><Puntaje valor={e.puntaje} /></td>
                    <td>{e.hallazgos ? <span className="pill alto">{e.hallazgos}</span> : <span className="tenue">0</span>}</td>
                    <td className="tenue">{e.con_respaldo ? hace(e.ultimo_respaldo) : "Solo SNMP"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
      {nuevo && (
        <FormularioEquipo
          onCerrar={() => setParametros({})}
          onListo={(equipo) => navegar(`/equipos/${equipo.id}`)}
        />
      )}
    </>
  );
}
