import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";
import { esLimiteDelPlan, textoDeError } from "../api";
import { claseSeveridad } from "../util";

export function Encabezado(props: { titulo: string; subtitulo?: ReactNode; acciones?: ReactNode }) {
  return (
    <div className="encabezado">
      <div>
        <h1>{props.titulo}</h1>
        {props.subtitulo && <div className="subtitulo">{props.subtitulo}</div>}
      </div>
      {props.acciones && <div className="fila">{props.acciones}</div>}
    </div>
  );
}

export function Tarjeta(props: { titulo?: ReactNode; acciones?: ReactNode; children: ReactNode; sinRelleno?: boolean }) {
  return (
    <section className={props.sinRelleno ? "tarjeta sin-relleno" : "tarjeta"}>
      {(props.titulo || props.acciones) && (
        <div className="entre" style={props.sinRelleno ? { padding: "12px 14px 4px" } : { marginBottom: 12 }}>
          {props.titulo && <h2>{props.titulo}</h2>}
          {props.acciones}
        </div>
      )}
      {props.children}
    </section>
  );
}

export function Severidad({ valor }: { valor: string }) {
  const texto = valor.charAt(0).toUpperCase() + valor.slice(1);
  return <span className={`pill ${claseSeveridad(valor)}`}>{texto}</span>;
}

export function EstadoEnLinea({ valor, alcanzable }: { valor: boolean | null; alcanzable?: boolean | null }) {
  if (valor === null) return <span className="tenue"><span className="punto sin-dato" />Sin datos</span>;
  if (valor) return <span><span className="punto ok" />En línea</span>;
  if (alcanzable)
    return (
      <span className="texto-naranja" title="Responde a ping, pero no a SNMP: revisa la configuración SNMP">
        <span className="punto atencion" />Sin SNMP
      </span>
    );
  return <span className="texto-rojo"><span className="punto caido" />Caído</span>;
}

export function Cargando() {
  return <div className="tenue" style={{ padding: 16 }}>Cargando…</div>;
}

export function MensajeError({ mensaje }: { mensaje: string | null }) {
  return mensaje ? <div className="aviso error" role="alert">{mensaje}</div> : null;
}

/** Lo que el plan gratis no incluye. Informa y muestra el camino, sin interrumpir. */
export function AvisoPro({ mensaje }: { mensaje: ReactNode }) {
  return (
    <div className="aviso pro" role="status">
      <span className="insignia-pro">Pro</span>
      <span className="crece">{mensaje}</span>
      <Link to="/planes" className="boton chico">Ver planes</Link>
    </div>
  );
}

/** Error de la API, o la invitación a Pro si es un límite del plan. */
export function ErrorOPro({ error }: { error: unknown }) {
  if (!error) return null;
  if (esLimiteDelPlan(error)) return <AvisoPro mensaje={textoDeError(error)} />;
  return <MensajeError mensaje={textoDeError(error)} />;
}

export function Vacio(props: { titulo: string; children?: ReactNode }) {
  return (
    <div className="vacio">
      <h3>{props.titulo}</h3>
      {props.children}
    </div>
  );
}

export function Modal(props: { titulo: string; onCerrar: () => void; children: ReactNode }) {
  const { onCerrar } = props;
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && onCerrar();
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [onCerrar]);
  // Fuera del árbol de la página: el vidrio (backdrop-filter) de una tarjeta
  // no puede encerrar a una ventana que se abre desde adentro.
  return createPortal(
    <div className="fondo-modal" onMouseDown={(e) => e.target === e.currentTarget && props.onCerrar()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={props.titulo}>
        <div className="entre">
          <h2>{props.titulo}</h2>
          <button className="boton-texto" onClick={props.onCerrar} aria-label="Cerrar">Cerrar</button>
        </div>
        {props.children}
      </div>
    </div>,
    document.body,
  );
}

/** Formulario que maneja el estado de envío y muestra el error de la API. */
export function Formulario(props: {
  onEnviar: () => Promise<void>;
  children: ReactNode;
  textoBoton: string;
  onCancelar?: () => void;
  peligro?: boolean;
}) {
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await props.onEnviar();
    } catch (err) {
      setError(err);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={enviar} className="pila">
      {props.children}
      <ErrorOPro error={error} />
      <div className="acciones" style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
        {props.onCancelar && (
          <button type="button" className="boton" onClick={props.onCancelar}>Cancelar</button>
        )}
        <button type="submit" className={props.peligro ? "boton peligro" : "boton primario"} disabled={enviando}>
          {enviando ? "Un momento…" : props.textoBoton}
        </button>
      </div>
    </form>
  );
}

export function Campo(props: { etiqueta: string; ayuda?: ReactNode; ancho?: boolean; children: ReactNode }) {
  return (
    <label className={props.ancho ? "campo ancho" : "campo"}>
      {props.etiqueta}
      {props.children}
      {props.ayuda && <span className="ayuda">{props.ayuda}</span>}
    </label>
  );
}

export function Segmentado<T extends string>(props: {
  opciones: { valor: T; texto: string }[];
  valor: T;
  onCambio: (valor: T) => void;
  etiqueta: string;
}) {
  return (
    <div className="segmentado" role="group" aria-label={props.etiqueta}>
      {props.opciones.map((o) => (
        <button
          key={o.valor}
          type="button"
          className={o.valor === props.valor ? "activo" : ""}
          aria-pressed={o.valor === props.valor}
          onClick={() => props.onCambio(o.valor)}
        >
          {o.texto}
        </button>
      ))}
    </div>
  );
}

export function BarraUso({ porcentaje }: { porcentaje: number | null }) {
  if (porcentaje === null) return <span className="tenue">—</span>;
  const clase = porcentaje >= 85 ? "lleno" : porcentaje >= 70 ? "alto" : "";
  return (
    <div className="fila" style={{ alignItems: "center", gap: 8, flexWrap: "nowrap" }}>
      <div className="barra-uso" style={{ flex: 1 }}>
        <div className={clase} style={{ width: `${Math.min(100, porcentaje)}%` }} />
      </div>
      <span className="tenue" style={{ minWidth: 42, textAlign: "right" }}>{porcentaje}%</span>
    </div>
  );
}

/** Puntaje de seguridad de 0 a 100, con color según el riesgo. */
export function Puntaje({ valor, conTexto }: { valor: number | null | undefined; conTexto?: boolean }) {
  if (valor === null || valor === undefined) return <span className="tenue">—</span>;
  const clase = valor >= 85 ? "ok" : valor >= 60 ? "medio" : "critico";
  return (
    <span className={`pill ${clase}`} title="Puntaje de seguridad según los hallazgos abiertos (100 = ninguno)">
      {conTexto ? `Seguridad ${valor}/100` : valor}
    </span>
  );
}

export function BotonCopiar({ texto }: { texto: string }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <button
      type="button"
      className="boton chico"
      onClick={async () => {
        await navigator.clipboard.writeText(texto);
        setCopiado(true);
        setTimeout(() => setCopiado(false), 1500);
      }}
    >
      {copiado ? "Copiado" : "Copiar"}
    </button>
  );
}

/** Elegir un archivo: en español y con arrastrar y soltar (el control nativo sale en inglés). */
export function ElegirArchivo(props: { aceptar?: string; archivo: File | null; onElegir: (archivo: File | null) => void; ayuda?: string }) {
  const [encima, setEncima] = useState(false);
  return (
    <label
      className={`elegir-archivo ${encima ? "encima" : ""} ${props.archivo ? "elegido" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setEncima(true); }}
      onDragLeave={() => setEncima(false)}
      onDrop={(e) => {
        e.preventDefault();
        setEncima(false);
        props.onElegir(e.dataTransfer.files[0] ?? null);
      }}
    >
      <input type="file" accept={props.aceptar} onChange={(e) => props.onElegir(e.target.files?.[0] ?? null)} />
      <span className="elegir-archivo-icono" aria-hidden="true">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M12 15V4M7 9l5-5 5 5M5 20h14" /></svg>
      </span>
      {props.archivo ? (
        <span><strong>{props.archivo.name}</strong> <span className="tenue">· {(props.archivo.size / 1024).toFixed(1)} KB · toca para cambiarlo</span></span>
      ) : (
        <span><strong>Elegir archivo</strong> <span className="tenue">o suéltalo aquí{props.ayuda ? ` · ${props.ayuda}` : ""}</span></span>
      )}
    </label>
  );
}
