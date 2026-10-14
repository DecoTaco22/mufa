// Informes en PDF (mufa Pro): el resumen del mes, la descarga y el envío mensual.
import { useState } from "react";
import { api, textoDeError } from "../api";
import { Campo, Cargando, ElegirArchivo, Encabezado, Formulario, Tarjeta } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Canal } from "../tipos";
import { fecha, puede, useDatos } from "../util";

interface FilaEquipo {
  equipo_id: number;
  equipo: string;
  sitio: string;
  disponibilidad: number | null;
  anterior: number | null;
  caidas: number;
  minutos_caido: number;
}

interface Resumen {
  mes: string;
  disponibilidad: number | null;
  disponibilidad_anterior: number | null;
  caidas: number;
  minutos_caido: number;
  puntaje: number | null;
  equipos: FilaEquipo[];
  lista_caidas: { equipo: string; inicio: string; fin: string | null; minutos: number }[];
  interfaces: { equipo: string; interfaz: string; velocidad_mbps: number; pico_pct: number; prom_pct: number; dias_saturada: number }[];
}

interface AjustesInforme {
  empresa: string;
  destinatarios: string[];
  canal_id: number | null;
  enviar_mensual: boolean;
  equipos: number[];
  tiene_logo: boolean;
}

const MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(" ");

function claveMes(fecha: Date): string {
  return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, "0")}`;
}

function ultimosMeses(cantidad: number): { valor: string; texto: string }[] {
  const hoy = new Date();
  return Array.from({ length: cantidad }, (_, i) => {
    const f = new Date(hoy.getFullYear(), hoy.getMonth() - i, 1);
    return { valor: claveMes(f), texto: `${MESES[f.getMonth()]} ${f.getFullYear()}${i === 0 ? " (en curso)" : ""}` };
  });
}

function porcentaje(v: number | null, decimales = 2): string {
  return v === null ? "—" : `${(v * 100).toLocaleString("es", { minimumFractionDigits: decimales, maximumFractionDigits: decimales })} %`;
}

function claseDisponibilidad(v: number | null): string {
  if (v === null) return "gris";
  return v >= 0.999 ? "ok" : v >= 0.99 ? "medio" : "critico";
}

function duracion(minutos: number): string {
  if (minutos < 60) return `${minutos} min`;
  const h = Math.floor(minutos / 60);
  if (h < 24) return `${h} h ${String(minutos % 60).padStart(2, "0")} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}

export function Informes() {
  const { usuario } = useSesion();
  const meses = ultimosMeses(13);
  // Por defecto, el mes pasado: el que ya está completo.
  const [mes, setMes] = useState(meses[1]?.valor ?? meses[0]!.valor);
  const { datos, cargando, error } = useDatos<Resumen>(`/pro/informes/resumen?mes=${mes}`);
  const configura = puede(usuario?.rol, "configurar_alertas");

  return (
    <>
      <Encabezado
        titulo="Informes"
        subtitulo="El mes de tu red en un PDF con tu logo: disponibilidad, caídas, saturación y seguridad."
        acciones={
          <div className="fila" style={{ gap: 8 }}>
            <select value={mes} onChange={(e) => setMes(e.target.value)} aria-label="Mes del informe">
              {meses.map((m) => <option key={m.valor} value={m.valor}>{m.texto}</option>)}
            </select>
            <a className="boton primario" href={`/api/v1/pro/informes/pdf?mes=${mes}`} download={`informe-${mes}.pdf`}>
              Descargar PDF
            </a>
          </div>
        }
      />
      {error && <div className="aviso error">{error}</div>}
      {cargando && !datos ? <Cargando /> : datos && <Vista resumen={datos} />}
      {configura && <Configuracion mes={mes} />}
    </>
  );
}

function Vista({ resumen }: { resumen: Resumen }) {
  const diferencia =
    resumen.disponibilidad !== null && resumen.disponibilidad_anterior !== null
      ? (resumen.disponibilidad - resumen.disponibilidad_anterior) * 100
      : null;
  return (
    <div className="pila" style={{ gap: 14, marginBottom: 14 }}>
      <div className="capacidad-resumen">
        <div className={`tarjeta capacidad-cifra ${claseDisponibilidad(resumen.disponibilidad)}`}>
          <span className="tenue">Disponibilidad</span>
          <strong>{porcentaje(resumen.disponibilidad)}</strong>
          {diferencia !== null && (
            <span className="tenue" style={{ fontSize: 12 }}>
              {diferencia >= 0 ? "+" : ""}{diferencia.toLocaleString("es", { maximumFractionDigits: 2 })} vs. mes anterior
            </span>
          )}
        </div>
        <div className="tarjeta capacidad-cifra"><span className="tenue">Caídas</span><strong>{resumen.caidas}</strong></div>
        <div className="tarjeta capacidad-cifra"><span className="tenue">Tiempo caído</span><strong>{duracion(resumen.minutos_caido)}</strong></div>
        <div className="tarjeta capacidad-cifra">
          <span className="tenue">Seguridad</span>
          <strong>{resumen.puntaje === null ? "—" : `${Math.round(resumen.puntaje)}/100`}</strong>
        </div>
      </div>

      <Tarjeta titulo="Disponibilidad por equipo" sinRelleno>
        <div className="tabla-caja">
          <table>
            <thead>
              <tr><th>Equipo</th><th>Sitio</th><th>Disponible</th><th>Mes anterior</th><th>Caídas</th><th>Tiempo caído</th></tr>
            </thead>
            <tbody>
              {resumen.equipos.map((e) => (
                <tr key={e.equipo_id}>
                  <td style={{ fontWeight: 500 }}>{e.equipo}</td>
                  <td className="tenue">{e.sitio || "—"}</td>
                  <td><span className={`pill ${claseDisponibilidad(e.disponibilidad)}`}>{porcentaje(e.disponibilidad)}</span></td>
                  <td className="tenue">{porcentaje(e.anterior)}</td>
                  <td>{e.caidas}</td>
                  <td className="tenue">{e.caidas ? duracion(e.minutos_caido) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Tarjeta>

      {resumen.lista_caidas.length > 0 && (
        <Tarjeta titulo="Caídas del mes" sinRelleno>
          <div className="tabla-caja">
            <table>
              <thead><tr><th>Equipo</th><th>Desde</th><th>Hasta</th><th>Duración</th></tr></thead>
              <tbody>
                {resumen.lista_caidas.map((c) => (
                  <tr key={`${c.equipo}-${c.inicio}`}>
                    <td style={{ fontWeight: 500 }}>{c.equipo}</td>
                    <td>{fecha(c.inicio)}</td>
                    <td>{c.fin ? fecha(c.fin) : <span className="pill critico">Sigue caído</span>}</td>
                    <td>{duracion(c.minutos)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Tarjeta>
      )}

      {resumen.interfaces.length > 0 && (
        <Tarjeta titulo="Interfaces más cargadas" sinRelleno>
          <div className="tabla-caja">
            <table>
              <thead><tr><th>Equipo · interfaz</th><th>Velocidad</th><th>Pico (p95)</th><th>Promedio</th><th>Días sobre 80 %</th></tr></thead>
              <tbody>
                {resumen.interfaces.map((i) => (
                  <tr key={`${i.equipo}-${i.interfaz}`}>
                    <td style={{ fontWeight: 500 }}>{i.equipo}<div className="tenue mono" style={{ fontWeight: 400 }}>{i.interfaz}</div></td>
                    <td>{i.velocidad_mbps} Mbps</td>
                    <td className={i.pico_pct >= 80 ? "texto-alerta" : ""}>{Math.round(i.pico_pct)} %</td>
                    <td className="tenue">{Math.round(i.prom_pct)} %</td>
                    <td>{i.dias_saturada}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Tarjeta>
      )}
    </div>
  );
}

function Configuracion({ mes }: { mes: string }) {
  const { datos, recargar } = useDatos<AjustesInforme>("/pro/informes/ajustes");
  const { datos: canales } = useDatos<Canal[]>("/alertas/canales");
  if (!datos) return null;
  return <FormularioAjustes key={JSON.stringify(datos)} inicial={datos} canales={canales ?? []} mes={mes} onGuardado={recargar} />;
}

function FormularioAjustes(props: { inicial: AjustesInforme; canales: Canal[]; mes: string; onGuardado: () => void }) {
  const [empresa, setEmpresa] = useState(props.inicial.empresa);
  const [destinatarios, setDestinatarios] = useState(props.inicial.destinatarios.join(", "));
  const [canal, setCanal] = useState(props.inicial.canal_id ? String(props.inicial.canal_id) : "");
  const [mensual, setMensual] = useState(props.inicial.enviar_mensual);
  const [logo, setLogo] = useState<File | null>(null);
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null);
  const [version, setVersion] = useState(0);
  const correos = props.canales.filter((c) => c.tipo === "correo");

  async function subirLogo(archivo: File | null) {
    setLogo(archivo);
    if (!archivo) return;
    const formulario = new FormData();
    formulario.append("archivo", archivo);
    try {
      await api("/pro/informes/logo", { metodo: "PUT", formulario });
      setMensaje({ ok: true, texto: "Logo guardado." });
      setVersion((v) => v + 1);
      props.onGuardado();
    } catch (e) {
      setMensaje({ ok: false, texto: textoDeError(e) });
    }
  }

  return (
    <div className="fila" style={{ alignItems: "flex-start" }}>
      <div className="crece">
        <Tarjeta titulo="Tu marca en el informe">
          <Formulario
            textoBoton="Guardar"
            onEnviar={async () => {
              await api("/pro/informes/ajustes", {
                metodo: "PUT",
                cuerpo: {
                  empresa,
                  destinatarios: destinatarios.split(/[\s,;]+/).filter(Boolean),
                  canal_id: canal ? Number(canal) : null,
                  enviar_mensual: mensual,
                  equipos: props.inicial.equipos,
                },
              });
              setMensaje({ ok: true, texto: "Guardado." });
              props.onGuardado();
            }}
          >
            <Campo etiqueta="Nombre de tu empresa" ayuda="Va en la portada y en el pie de cada página.">
              <input value={empresa} maxLength={120} onChange={(e) => setEmpresa(e.target.value)} placeholder="Telecom Ejemplo" />
            </Campo>
            <Campo etiqueta="Mandarlo cada mes a" ayuda="Correos separados por comas. El día 1 reciben el informe del mes anterior.">
              <input value={destinatarios} onChange={(e) => setDestinatarios(e.target.value)} placeholder="gerencia@tuisp.com, cliente@empresa.com" />
            </Campo>
            <Campo
              etiqueta="Servidor de correo"
              ayuda={correos.length ? "Se usa el servidor SMTP de este canal de alertas." : "Primero agrega un canal de correo en Alertas."}
            >
              <select value={canal} onChange={(e) => setCanal(e.target.value)}>
                <option value="">Elegir…</option>
                {correos.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
              </select>
            </Campo>
            <label className="casilla ancho"><input type="checkbox" checked={mensual} onChange={(e) => setMensual(e.target.checked)} /> Mandarlo automáticamente el día 1 de cada mes</label>
          </Formulario>
          {mensaje && <div className={`aviso ${mensaje.ok ? "ok" : "error"}`} style={{ marginTop: 12 }}>{mensaje.texto}</div>}
        </Tarjeta>
      </div>
      <div className="crece">
        <Tarjeta titulo="Logo">
          {props.inicial.tiene_logo && (
            <div className="logo-informe">
              <img src={`/api/v1/pro/informes/logo?v=${version}`} alt="Logo del informe" />
            </div>
          )}
          <ElegirArchivo aceptar="image/png,image/jpeg" archivo={logo} onElegir={(a) => void subirLogo(a)} ayuda="PNG o JPG, hasta 1 MB. Mejor con fondo blanco o transparente." />
          {props.inicial.tiene_logo && (
            <button
              className="boton chico"
              style={{ marginTop: 10 }}
              onClick={async () => {
                await api("/pro/informes/logo", { metodo: "DELETE" });
                setLogo(null);
                props.onGuardado();
              }}
            >
              Quitar logo
            </button>
          )}
        </Tarjeta>
        <Tarjeta titulo="Probar el envío">
          <p className="tenue" style={{ marginTop: 0 }}>Manda ahora el informe del mes elegido a los destinatarios guardados.</p>
          <Formulario
            textoBoton="Mandar ahora"
            onEnviar={async () => {
              const r = await api<{ enviado_a: string }>(`/pro/informes/enviar?mes=${props.mes}`, { metodo: "POST" });
              setMensaje({ ok: true, texto: `Enviado a ${r.enviado_a}.` });
            }}
          >
            <span />
          </Formulario>
        </Tarjeta>
      </div>
    </div>
  );
}
