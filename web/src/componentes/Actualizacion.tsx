import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, textoDeError } from "../api";
import { useSesion } from "../sesion";
import type { Actualizacion } from "../tipos";
import { dia, hace, puede, useDatos } from "../util";
import { Tarjeta } from "./ui";

const RUTA = "/sistema/actualizacion";

/** Mientras se descarga o se instala, pregunta seguido cómo va. */
function useSeguimiento(datos: Actualizacion | null, recargar: () => void) {
  useEffect(() => {
    if (!datos?.estado) return;
    const reloj = window.setInterval(recargar, 1500);
    return () => window.clearInterval(reloj);
  }, [datos?.estado, recargar]);
}

/** Arriba de todas las páginas: aparece solo si hay una versión nueva. */
export function AvisoActualizacion() {
  const { datos, recargar } = useDatos<Actualizacion>(RUTA);
  const [cerrado, setCerrado] = useState(false);
  useSeguimiento(datos, recargar);
  if (!datos?.nueva || cerrado) return null;
  return (
    <div className="aviso info aviso-actualizacion">
      <span className="crece">
        {datos.estado === "descargando" && <>Descargando mufa {datos.nueva.version}…</>}
        {datos.estado === "instalando" && <>Instalando mufa {datos.nueva.version}: se va a cerrar y volver a abrir sola.</>}
        {!datos.estado && <>Hay una versión nueva: <strong>mufa {datos.nueva.version}</strong> (tienes la {datos.version_actual}).</>}
      </span>
      {!datos.estado && (
        <>
          <Link className="boton chico primario" to="/ajustes#actualizacion">
            {datos.puede_instalar ? "Ver y actualizar" : "Cómo actualizar"}
          </Link>
          <button className="boton chico" onClick={() => setCerrado(true)} aria-label="Ocultar el aviso">Más tarde</button>
        </>
      )}
    </div>
  );
}

/** En Ajustes: versión, novedades, actualizar con un clic y si busca o no. */
export function TarjetaActualizacion() {
  const { usuario } = useSesion();
  const { datos, recargar } = useDatos<Actualizacion>(RUTA);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useSeguimiento(datos, recargar);
  useEffect(() => {
    if (datos && window.location.hash === "#actualizacion") {
      document.getElementById("actualizacion")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [datos]);
  if (!datos) return null;
  const admin = puede(usuario?.rol, "administrar_usuarios");

  async function hacer(accion: () => Promise<unknown>) {
    setOcupado(true);
    setError(null);
    try {
      await accion();
      recargar();
    } catch (e) {
      setError(textoDeError(e));
    } finally {
      setOcupado(false);
    }
  }

  const nueva = datos.nueva;
  return (
    <div id="actualizacion">
      <Tarjeta titulo="Actualizaciones">
        <div className="pila">
          <div><span className="tenue">Tienes </span>mufa {datos.version_actual}</div>
          {!nueva && datos.revisada && <div className="aviso ok">Es la última versión (revisado {hace(datos.revisada)}).</div>}
          {nueva && (
            <div className="pila" style={{ gap: 8 }}>
              <div style={{ fontSize: 18, fontWeight: 600 }}>
                mufa {nueva.version} está disponible
                {nueva.publicada && <span className="tenue" style={{ fontSize: 13, fontWeight: 400 }}> · {dia(nueva.publicada)}</span>}
              </div>
              {nueva.notas && <pre className="notas-version">{nueva.notas}</pre>}
              {datos.estado === "descargando" && <div className="aviso info">Descargando y verificando la firma…</div>}
              {datos.estado === "instalando" && (
                <div className="aviso info">Instalando: mufa se va a cerrar y volver a abrir sola. Tus datos se conservan.</div>
              )}
              {datos.puede_instalar && !datos.estado && admin && (
                <div>
                  <button className="boton primario" disabled={ocupado} onClick={() => void hacer(() => api(`${RUTA}/instalar`, { metodo: "POST" }))}>
                    Actualizar ahora
                  </button>
                  <div className="tenue" style={{ fontSize: 12, marginTop: 6 }}>
                    {datos.modo === "instalador"
                      ? "Windows te va a pedir permiso de administrador, como cualquier instalador."
                      : "mufa se cierra, se reemplaza y se vuelve a abrir."}
                  </div>
                </div>
              )}
              {datos.puede_instalar && !admin && <div className="tenue">Un administrador de mufa puede instalarla desde aquí.</div>}
              {!datos.puede_instalar && datos.pasos && (
                <>
                  <div className="tenue">Para actualizar:</div>
                  <pre className="notas-version mono">{datos.pasos}</pre>
                </>
              )}
              <a href={datos.url_versiones} target="_blank" rel="noreferrer">Ver la versión en GitHub</a>
            </div>
          )}
          {datos.error && <div className="aviso atencion">{datos.error}</div>}
          {error && <div className="aviso error">{error}</div>}
          {admin && datos.modo !== "tienda" && (
            <div className="fila" style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <label className="casilla">
                <input
                  type="checkbox"
                  checked={datos.buscar}
                  disabled={ocupado}
                  onChange={(e) => void hacer(() => api(RUTA, { metodo: "PUT", cuerpo: { buscar: e.target.checked } }))}
                />{" "}
                Buscar versiones nuevas una vez al día
              </label>
              {datos.buscar && (
                <button className="boton chico" disabled={ocupado} onClick={() => void hacer(() => api(`${RUTA}/buscar`, { metodo: "POST" }))}>
                  Buscar ahora
                </button>
              )}
            </div>
          )}
          {datos.modo === "tienda" && <div className="tenue">La Microsoft Store mantiene mufa al día.</div>}
          <div className="tenue" style={{ fontSize: 12 }}>
            Para buscar, mufa solo descarga de GitHub la lista firmada de la última versión. No manda datos tuyos.
          </div>
        </div>
      </Tarjeta>
    </div>
  );
}
