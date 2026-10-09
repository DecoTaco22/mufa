import { useEffect, useState } from "react";
import { api, textoDeError } from "../api";
import { Campo, Encabezado, MensajeError, Tarjeta } from "../componentes/ui";

type Valores = Record<string, string>;
type Resultado = Record<string, number | boolean>;

/** Llama a la API cada vez que cambian los valores (con una pequeña espera). */
function useCalculo(ruta: string, cuerpo: Record<string, unknown>) {
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const clave = JSON.stringify(cuerpo);
  useEffect(() => {
    const espera = setTimeout(() => {
      api<Resultado>(ruta, { metodo: "POST", cuerpo: JSON.parse(clave) })
        .then((r) => { setResultado(r); setError(null); })
        .catch((e: unknown) => setError(textoDeError(e)));
    }, 250);
    return () => clearTimeout(espera);
  }, [ruta, clave]);
  return { resultado, error };
}

const n = (v: string | undefined) => (v === undefined || v === "" ? 0 : Number(v));
const f = (v: number | boolean | undefined, decimales = 1) =>
  typeof v === "number" ? v.toLocaleString("es", { maximumFractionDigits: decimales, minimumFractionDigits: decimales }) : "—";

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div style={{ background: "var(--sutil)", borderRadius: 12, padding: "12px 14px" }}>
      <div className="tenue" style={{ fontSize: 12 }}>{etiqueta}</div>
      <div style={{ fontSize: 21, fontWeight: 600, marginTop: 2 }}>{valor}</div>
    </div>
  );
}

export function Fibra() {
  return (
    <>
      <Encabezado titulo="Fibra óptica" subtitulo="Calculadoras de diseño de enlaces" />
      <Presupuesto />
      <div className="fila">
        <div className="crece" style={{ flexGrow: 2 }}><DispersionCromatica /></div>
        <div className="crece"><Apertura /></div>
      </div>
    </>
  );
}

function Presupuesto() {
  const [v, setV] = useState<Valores>({
    potencia_tx_dbm: "0", sensibilidad_rx_dbm: "-24", distancia_km: "40", longitud_onda_nm: "1550",
    conectores: "4", tipo_conectores: "mismo", empalmes: "12", perdida_empalme_db: "0.1",
    relacion_extincion_db: "10", receptor: "pin", margen_seguridad_db: "3",
  });
  const cambiar = (clave: string) => (e: { target: { value: string } }) => setV({ ...v, [clave]: e.target.value });
  const { resultado: r, error } = useCalculo("/fibra/presupuesto", {
    ...Object.fromEntries(["potencia_tx_dbm", "sensibilidad_rx_dbm", "distancia_km", "perdida_empalme_db", "margen_seguridad_db"].map((k) => [k, n(v[k])])),
    conectores: n(v.conectores), empalmes: n(v.empalmes), longitud_onda_nm: n(v.longitud_onda_nm),
    relacion_extincion_db: n(v.relacion_extincion_db), tipo_conectores: v.tipo_conectores, receptor: v.receptor,
  });

  const veredicto = !r ? null : r.con_margen_suficiente ? ["ok", "El enlace cierra con margen"] : r.cierra ? ["alto", "Cierra, pero con menos margen del recomendado"] : ["critico", "El enlace no cierra"];

  return (
    <Tarjeta titulo="Presupuesto óptico">
      <div className="formulario">
        <Campo etiqueta="Potencia Tx (dBm)"><input type="number" step="0.5" value={v.potencia_tx_dbm} onChange={cambiar("potencia_tx_dbm")} /></Campo>
        <Campo etiqueta="Sensibilidad Rx (dBm)"><input type="number" step="0.5" value={v.sensibilidad_rx_dbm} onChange={cambiar("sensibilidad_rx_dbm")} /></Campo>
        <Campo etiqueta="Distancia (km)"><input type="number" step="1" value={v.distancia_km} onChange={cambiar("distancia_km")} /></Campo>
        <Campo etiqueta="Longitud de onda">
          <select value={v.longitud_onda_nm} onChange={cambiar("longitud_onda_nm")}>
            <option value="1310">1310 nm · 0,35 dB/km</option>
            <option value="1550">1550 nm · 0,22 dB/km</option>
          </select>
        </Campo>
        <Campo etiqueta="Conectores"><input type="number" min={0} value={v.conectores} onChange={cambiar("conectores")} /></Campo>
        <Campo etiqueta="Fabricante de conectores">
          <select value={v.tipo_conectores} onChange={cambiar("tipo_conectores")}>
            <option value="mismo">Mismo (0,20 ± 0,15 dB)</option>
            <option value="mixto">Distintos (0,35 ± 0,25 dB)</option>
          </select>
        </Campo>
        <Campo etiqueta="Empalmes"><input type="number" min={0} value={v.empalmes} onChange={cambiar("empalmes")} /></Campo>
        <Campo etiqueta="Pérdida por empalme (dB)"><input type="number" step="0.01" value={v.perdida_empalme_db} onChange={cambiar("perdida_empalme_db")} /></Campo>
        <Campo etiqueta="Relación de extinción">
          <select value={v.relacion_extincion_db} onChange={cambiar("relacion_extincion_db")}>
            <option value="10">10 dB</option><option value="3">3 dB</option>
          </select>
        </Campo>
        <Campo etiqueta="Receptor">
          <select value={v.receptor} onChange={cambiar("receptor")}><option value="pin">PIN</option><option value="apd">APD</option></select>
        </Campo>
        <Campo etiqueta="Margen de seguridad (dB)"><input type="number" step="0.5" value={v.margen_seguridad_db} onChange={cambiar("margen_seguridad_db")} /></Campo>
      </div>
      <MensajeError mensaje={error} />
      {r && (
        <div className="pila" style={{ marginTop: 16 }}>
          <div className="grilla" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
            <Dato etiqueta="Fibra" valor={`${f(r.perdida_fibra, 2)} dB`} />
            <Dato etiqueta="Conectores" valor={`${f(r.perdida_conectores, 2)} dB`} />
            <Dato etiqueta="Empalmes" valor={`${f(r.perdida_empalmes, 2)} dB`} />
            <Dato etiqueta="Penalidad por ER" valor={`${f(r.penalidad)} dB`} />
            <Dato etiqueta="Potencia esperada en Rx" valor={`${f(r.potencia_esperada_rx)} dBm`} />
            <Dato etiqueta="Margen" valor={`${f(r.margen)} dB`} />
          </div>
          {veredicto && (
            <div className="fila" style={{ alignItems: "center" }}>
              <span className={`pill ${veredicto[0]}`} style={{ fontSize: 13, padding: "4px 12px" }}>{veredicto[1]}</span>
              <span>Distancia máxima: <strong>{f(r.distancia_maxima_km, 0)} km</strong></span>
            </div>
          )}
          <div className="tenue" style={{ fontSize: 12 }}>
            Conectores: media + σ√n. Atenuación típica de fibra monomodo estándar: usa la del fabricante si la tienes.
          </div>
        </div>
      )}
    </Tarjeta>
  );
}

function DispersionCromatica() {
  const [v, setV] = useState<Valores>({ coeficiente_ps_nm_km: "17", ancho_espectral_nm: "6", distancia_km: "10", tasa_gbps: "1" });
  const cambiar = (clave: string) => (e: { target: { value: string } }) => setV({ ...v, [clave]: e.target.value });
  const { resultado: r, error } = useCalculo("/fibra/dispersion", Object.fromEntries(Object.entries(v).map(([k, x]) => [k, n(x)])));
  return (
    <Tarjeta titulo="Dispersión cromática">
      <div className="formulario">
        <Campo etiqueta="Tipo de fibra">
          <select value={v.coeficiente_ps_nm_km} onChange={cambiar("coeficiente_ps_nm_km")}>
            <option value="17">SMF estándar · 17 ps/nm/km</option>
            <option value="4">NZDSF · 4 ps/nm/km</option>
          </select>
        </Campo>
        <Campo etiqueta="Ancho espectral (nm)"><input type="number" step="0.1" value={v.ancho_espectral_nm} onChange={cambiar("ancho_espectral_nm")} /></Campo>
        <Campo etiqueta="Distancia (km)"><input type="number" value={v.distancia_km} onChange={cambiar("distancia_km")} /></Campo>
        <Campo etiqueta="Tasa (Gbps)"><input type="number" step="0.5" value={v.tasa_gbps} onChange={cambiar("tasa_gbps")} /></Campo>
      </div>
      <MensajeError mensaje={error} />
      {r && (
        <div className="pila" style={{ marginTop: 14 }}>
          <div>Dispersión total <strong>{f(r.total_ps, 0)} ps</strong> · periodo de bit <strong>{f(r.periodo_bit_ps, 0)} ps</strong></div>
          <div>
            Ocupa el <strong>{f(r.porcentaje_del_periodo, 0)} %</strong> del periodo (máximo 20 %){" "}
            <span className={`pill ${r.dentro_del_limite ? "ok" : "critico"}`}>{r.dentro_del_limite ? "Dentro del límite" : "Excede el límite"}</span>
          </div>
          <div>Para compensarla: <strong>{f(r.dcf_para_compensar_km)} km de DCF</strong> (−100 ps/nm/km)</div>
          <div className="tenue" style={{ fontSize: 12 }}>Cada vez que doblas la velocidad, el efecto de la dispersión se cuadruplica.</div>
        </div>
      )}
    </Tarjeta>
  );
}

function Apertura() {
  const [v, setV] = useState<Valores>({ n_nucleo: "1.4682", n_revestimiento: "1.4629" });
  const cambiar = (clave: string) => (e: { target: { value: string } }) => setV({ ...v, [clave]: e.target.value });
  const { resultado: r, error } = useCalculo("/fibra/apertura-numerica", { n_nucleo: n(v.n_nucleo), n_revestimiento: n(v.n_revestimiento) });
  return (
    <Tarjeta titulo="Apertura numérica">
      <div className="formulario">
        <Campo etiqueta="n1 (núcleo)"><input type="number" step="0.0001" value={v.n_nucleo} onChange={cambiar("n_nucleo")} /></Campo>
        <Campo etiqueta="n2 (revestimiento)"><input type="number" step="0.0001" value={v.n_revestimiento} onChange={cambiar("n_revestimiento")} /></Campo>
      </div>
      <MensajeError mensaje={error} />
      {r && !error && (
        <div className="pila" style={{ marginTop: 14 }}>
          <div>NA = √(n1² − n2²) = <strong>{f(r.apertura, 4)}</strong></div>
          <div>Ángulo de aceptación <strong>{f(r.angulo_aceptacion_grados)}°</strong></div>
        </div>
      )}
    </Tarjeta>
  );
}
