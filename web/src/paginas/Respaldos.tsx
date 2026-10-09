import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, textoDeError } from "../api";
import { Icono, type NombreIcono } from "../componentes/Icono";
import { Campo, Cargando, Encabezado, MensajeError, Segmentado, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Marca } from "../tipos";
import { fecha, hace, puede, useDatos } from "../util";

type Protocolo = "sftp" | "ftps" | "ftp";
type Organizar = "por_equipo" | "por_dia";

interface Destino {
  activo: boolean;
  protocolo: Protocolo;
  host: string;
  puerto: number;
  usuario: string;
  tiene_password: boolean;
  carpeta: string;
  organizar: Organizar;
  verificar_certificado: boolean;
}

interface EquipoRespaldo {
  id: number;
  nombre: string;
  marca: string;
  estado: "ok" | "error" | "sin_acceso" | "sin_soporte" | "pendiente";
  ultimo: string | null;
  versiones: number;
  error: string;
}

interface Resumen {
  programa: { activo: boolean; hora: string };
  proximo: string | null;
  hora_servidor: string;
  zona: string;
  respaldando: boolean;
  destino: Destino;
  ultimo_envio: { cuando: string; ok: boolean; archivos: number; mensaje: string } | null;
  equipos: EquipoRespaldo[];
}

const ESTADOS: Record<EquipoRespaldo["estado"], [string, string, NombreIcono]> = {
  ok: ["Al día", "ok", "escudo"],
  error: ["Falló", "critico", "alerta"],
  pendiente: ["Pendiente", "gris", "reloj"],
  sin_acceso: ["Falta usuario SSH", "medio", "llave"],
  sin_soporte: ["Solo SNMP", "gris", "grafica"],
};

const PUERTOS: Record<Protocolo, number> = { sftp: 22, ftps: 21, ftp: 21 };

export function Respaldos() {
  const { usuario } = useSesion();
  const [version, setVersion] = useState(0);
  const { datos, error, cargando } = useDatos<Resumen>(`/respaldos?v=${version}`);
  const { datos: marcas } = useDatos<Marca[]>("/marcas");
  const ingeniero = puede(usuario?.rol, "gestionar_equipos");
  const senior = puede(usuario?.rol, "configurar_alertas");
  const [aviso, setAviso] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const recargar = () => setVersion((v) => v + 1);

  // Mientras hay un respaldo general en curso, la tabla se actualiza sola.
  useEffect(() => {
    if (!datos?.respaldando) return;
    const t = setTimeout(recargar, 3000);
    return () => clearTimeout(t);
  }, [datos]);

  async function respaldarTodo() {
    setAviso(null);
    try {
      const r = await api<{ iniciado: boolean }>("/respaldos/ejecutar", { metodo: "POST" });
      setAviso(r.iniciado ? { tipo: "ok", texto: "Respaldando todos los equipos. La tabla se actualiza sola." } : { tipo: "ok", texto: "Ya hay un respaldo en curso." });
      recargar();
    } catch (e) {
      setAviso({ tipo: "error", texto: textoDeError(e) });
    }
  }

  const nombreMarca = (m: string) => marcas?.find((x) => x.marca === m)?.nombre ?? m;
  const respaldables = datos?.equipos.filter((e) => e.estado !== "sin_soporte") ?? [];
  const alDia = respaldables.filter((e) => e.estado === "ok").length;

  return (
    <>
      <Encabezado
        titulo="Respaldos"
        subtitulo="La configuración de cada equipo, todos los días, con sus versiones y una copia en tu propio servidor."
        acciones={
          ingeniero && (
            <button className="boton primario" disabled={datos?.respaldando} onClick={() => void respaldarTodo()}>
              <Icono nombre="descarga" /> {datos?.respaldando ? "Respaldando…" : "Respaldar todo ahora"}
            </button>
          )
        }
      />
      <MensajeError mensaje={error} />
      {aviso && <div className={`aviso ${aviso.tipo}`} role="status">{aviso.texto}</div>}
      {cargando && !datos ? (
        <Cargando />
      ) : datos ? (
        <>
          <div className="respaldos-cabecera">
            <Horario resumen={datos} editable={ingeniero} onGuardado={recargar} />
            <div className="tarjeta kpi respaldos-cifra">
              <div className="etiqueta">Al día</div>
              <div className="valor">{alDia}<small> / {respaldables.length}</small></div>
              <div className="nota">
                {datos.ultimo_envio
                  ? datos.ultimo_envio.ok
                    ? `Última copia al servidor ${hace(datos.ultimo_envio.cuando)} (${datos.ultimo_envio.archivos} archivos)`
                    : `La última copia falló: ${datos.ultimo_envio.mensaje}`
                  : datos.destino.activo ? "Todavía no se copió al servidor" : "Sin copia a un servidor"}
              </div>
            </div>
          </div>

          <ServidorDeCopia destino={datos.destino} editable={senior} onGuardado={recargar} />

          <Tarjeta titulo="Equipos" sinRelleno>
            {!datos.equipos.length ? (
              <Vacio titulo="Todavía no hay equipos">Agrega equipos con su usuario SSH para respaldarlos.</Vacio>
            ) : (
              <div className="tabla-caja">
                <table>
                  <thead><tr><th>Equipo</th><th>Marca</th><th>Estado</th><th>Último respaldo</th><th>Versiones</th></tr></thead>
                  <tbody>
                    {datos.equipos.map((e) => {
                      const [texto, tono, icono] = ESTADOS[e.estado];
                      return (
                        <tr key={e.id}>
                          <td style={{ fontWeight: 500 }}><Link to={`/equipos/${e.id}`}>{e.nombre}</Link></td>
                          <td className="tenue">{nombreMarca(e.marca)}</td>
                          <td>
                            <span className={`pill ${tono}`} title={e.error || undefined}><Icono nombre={icono} tamano={12} /> {texto}</span>
                            {e.error && <div className="tenue respaldos-error">{e.error}</div>}
                          </td>
                          <td className="tenue" title={e.ultimo ? fecha(e.ultimo) : undefined}>{e.ultimo ? hace(e.ultimo) : "—"}</td>
                          <td className="tenue">{e.versiones || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Tarjeta>
          <p className="tenue" style={{ fontSize: 13 }}>
            Se respaldan MikroTik, Cisco, Huawei, Juniper, HPE / Aruba, Ubiquiti, Nokia y ZTE, siempre en solo lectura. Solo se guarda una versión nueva cuando la configuración cambió.
          </p>
        </>
      ) : null}
    </>
  );
}

function Horario({ resumen, editable, onGuardado }: { resumen: Resumen; editable: boolean; onGuardado: () => void }) {
  const [activo, setActivo] = useState(resumen.programa.activo);
  const [hora, setHora] = useState(resumen.programa.hora);
  const [error, setError] = useState<string | null>(null);
  const cambiado = activo !== resumen.programa.activo || hora !== resumen.programa.hora;

  async function guardar() {
    setError(null);
    try {
      await api("/respaldos/programa", { metodo: "PUT", cuerpo: { activo, hora } });
      onGuardado();
    } catch (e) {
      setError(textoDeError(e));
    }
  }

  const servidor = new Date(resumen.hora_servidor).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
  return (
    <div className="tarjeta respaldos-horario">
      <div className="respaldos-horario-fila">
        <span className="respaldos-icono"><Icono nombre="calendario" tamano={22} /></span>
        <div className="crece">
          <div className="etiqueta">Respaldo automático</div>
          <div className="respaldos-hora">
            {activo ? "Todos los días a las" : "Apagado"}
            {activo && (
              <input type="time" value={hora} disabled={!editable} onChange={(e) => setHora(e.target.value)} aria-label="Hora del respaldo" />
            )}
          </div>
        </div>
        {editable && (
          <label className="interruptor" title={activo ? "Apagar" : "Encender"}>
            <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} aria-label="Respaldo automático" />
            <span />
          </label>
        )}
      </div>
      <div className="nota">
        {resumen.proximo ? `Próximo: ${fecha(resumen.proximo)}. ` : ""}
        Hora del servidor: {servidor}{resumen.zona ? ` (${resumen.zona})` : ""}. Si estaba apagado a esa hora, respalda apenas arranca.
      </div>
      {error && <div className="aviso error">{error}</div>}
      {editable && cambiado && (
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button className="boton chico" onClick={() => { setActivo(resumen.programa.activo); setHora(resumen.programa.hora); }}>Deshacer</button>
          <button className="boton chico primario" onClick={() => void guardar()}>Guardar horario</button>
        </div>
      )}
    </div>
  );
}

function ServidorDeCopia({ destino, editable, onGuardado }: { destino: Destino; editable: boolean; onGuardado: () => void }) {
  const [d, setD] = useState(destino);
  const [password, setPassword] = useState("");
  const [abierto, setAbierto] = useState(!destino.host);
  const [ocupado, setOcupado] = useState<"" | "probar" | "guardar" | "enviar">("");
  const [aviso, setAviso] = useState<{ tipo: "ok" | "error" | "atencion"; texto: string; detalle?: string } | null>(null);
  const cambiar = <K extends keyof Destino>(clave: K, valor: Destino[K]) => setD((x) => ({ ...x, [clave]: valor }));
  const cuerpo = () => ({ ...d, password: password || null });

  async function hacer(cual: "probar" | "guardar" | "enviar") {
    setOcupado(cual);
    setAviso(null);
    try {
      if (cual === "probar") {
        const r = await api<{ ok: boolean; mensaje: string; huella: string }>("/respaldos/destino/probar", { metodo: "POST", cuerpo: cuerpo() });
        setAviso({ tipo: r.ok ? "ok" : "error", texto: r.mensaje, detalle: r.huella ? `Huella del servidor: ${r.huella}. Compárala con la de tu servidor la primera vez.` : undefined });
      } else if (cual === "guardar") {
        await api("/respaldos/destino", { metodo: "PUT", cuerpo: cuerpo() });
        setPassword("");
        setAviso({ tipo: "ok", texto: d.activo ? "Guardado. Después de cada respaldo diario se copia al servidor." : "Guardado (la copia automática está apagada)." });
        onGuardado();
      } else {
        const r = await api<{ archivos: number; rutas: string[] }>("/respaldos/enviar", { metodo: "POST" });
        setAviso({ tipo: "ok", texto: `Se copiaron ${r.archivos} archivos.`, detalle: r.rutas.slice(0, 3).join("\n") + (r.rutas.length > 3 ? "\n…" : "") });
        onGuardado();
      }
    } catch (e) {
      setAviso({ tipo: "error", texto: textoDeError(e) });
    } finally {
      setOcupado("");
    }
  }

  const ejemplo = d.organizar === "por_dia"
    ? `${d.carpeta.replace(/\/$/, "")}/2026-10-08/RT-CORE.rsc`
    : `${d.carpeta.replace(/\/$/, "")}/RT-CORE/RT-CORE_2026-10-08_1200.rsc`;

  return (
    <Tarjeta
      titulo={<span className="respaldos-titulo"><Icono nombre="intercambio" /> Copia a tu servidor</span>}
      acciones={
        destino.host && (
          <button className="boton chico" onClick={() => setAbierto((a) => !a)}>{abierto ? "Cerrar" : editable ? "Configurar" : "Ver"}</button>
        )
      }
    >
      {destino.host && (
        <div className="respaldos-destino-resumen">
          <span className={`pill ${destino.activo ? "ok" : "gris"}`}>{destino.activo ? "Activa" : "Apagada"}</span>
          <span className="mono">{destino.protocolo}://{destino.usuario ? `${destino.usuario}@` : ""}{destino.host}:{destino.puerto}{destino.carpeta}</span>
        </div>
      )}
      {!destino.host && !editable && <p className="tenue">Todavía no hay un servidor configurado. Lo configura un usuario Senior o Admin.</p>}
      {abierto && (editable || destino.host) && (
        <fieldset disabled={!editable} className="respaldos-formulario">
          <Campo etiqueta="Protocolo" ancho>
            <Segmentado
              etiqueta="Protocolo"
              valor={d.protocolo}
              onCambio={(p) => setD((x) => ({ ...x, protocolo: p, puerto: x.puerto === PUERTOS[x.protocolo] ? PUERTOS[p] : x.puerto }))}
              opciones={[{ valor: "sftp", texto: "SFTP" }, { valor: "ftps", texto: "FTPS" }, { valor: "ftp", texto: "FTP" }]}
            />
          </Campo>
          {d.protocolo === "ftp" && (
            <div className="aviso atencion campo ancho">
              Con FTP simple la contraseña y las configuraciones viajan sin cifrar, y las configuraciones tienen secretos (comunidades SNMP, claves de VPN). Úsalo solo dentro de una red de confianza; mejor SFTP.
            </div>
          )}
          <div className="respaldos-fila">
            <Campo etiqueta="IP o nombre del servidor">
              <input value={d.host} onChange={(e) => cambiar("host", e.target.value)} placeholder="192.168.10.20" autoComplete="off" spellCheck={false} />
            </Campo>
            <Campo etiqueta="Puerto">
              <input type="number" min={1} max={65535} value={d.puerto} onChange={(e) => cambiar("puerto", Number(e.target.value))} style={{ maxWidth: 110 }} />
            </Campo>
          </div>
          <div className="respaldos-fila">
            <Campo etiqueta="Usuario">
              <input value={d.usuario} onChange={(e) => cambiar("usuario", e.target.value)} autoComplete="off" spellCheck={false} />
            </Campo>
            <Campo etiqueta="Contraseña" ayuda={destino.tiene_password ? "Déjala vacía para mantener la guardada." : undefined}>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={destino.tiene_password ? "••••••••" : ""} autoComplete="new-password" />
            </Campo>
          </div>
          <div className="respaldos-fila">
            <Campo etiqueta="Carpeta" ayuda={<>Ejemplo: <span className="mono">{ejemplo}</span></>}>
              <input value={d.carpeta} onChange={(e) => cambiar("carpeta", e.target.value)} placeholder="/mufa" spellCheck={false} />
            </Campo>
            <Campo etiqueta="Organizar">
              <Segmentado
                etiqueta="Organizar"
                valor={d.organizar}
                onCambio={(o) => cambiar("organizar", o)}
                opciones={[{ valor: "por_equipo", texto: "Carpeta por equipo" }, { valor: "por_dia", texto: "Carpeta por día" }]}
              />
            </Campo>
          </div>
          {d.protocolo === "ftps" && (
            <label className="casilla">
              <input type="checkbox" checked={d.verificar_certificado} onChange={(e) => cambiar("verificar_certificado", e.target.checked)} />
              Verificar el certificado (desmárcalo solo si tu servidor usa uno propio, como un NAS)
            </label>
          )}
          <label className="casilla">
            <input type="checkbox" checked={d.activo} onChange={(e) => cambiar("activo", e.target.checked)} />
            Copiar al servidor después de cada respaldo diario
          </label>
          {aviso && (
            <div className={`aviso ${aviso.tipo}`} role="status">
              {aviso.texto}
              {aviso.detalle && <pre className="respaldos-detalle">{aviso.detalle}</pre>}
            </div>
          )}
          {editable && (
            <div className="respaldos-acciones">
              <button type="button" className="boton" disabled={!!ocupado || !d.host} onClick={() => void hacer("probar")}>
                {ocupado === "probar" ? "Probando…" : "Probar conexión"}
              </button>
              <button type="button" className="boton" disabled={!!ocupado || !destino.host} onClick={() => void hacer("enviar")} title={!destino.host ? "Guarda el servidor primero" : undefined}>
                {ocupado === "enviar" ? "Enviando…" : "Enviar ahora"}
              </button>
              <button type="button" className="boton primario" disabled={!!ocupado} onClick={() => void hacer("guardar")}>
                {ocupado === "guardar" ? "Guardando…" : "Guardar"}
              </button>
            </div>
          )}
        </fieldset>
      )}
    </Tarjeta>
  );
}
