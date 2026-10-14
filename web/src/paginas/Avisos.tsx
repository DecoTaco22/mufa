// Avisos al equipo (mufa Pro): contactos del NOC, guardias, escalamiento y «Lo tomo yo».
import { useState } from "react";
import { api, textoDeError } from "../api";
import { BotonCopiar, Campo, Encabezado, Formulario, Tarjeta, Vacio } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Canal } from "../tipos";
import { hace, puede, useDatos } from "../util";

interface AjustesAvisos {
  activo: boolean;
  canal_id: number | null;
  minutos_escalar: number;
  eventos: string[];
  bot: string;
  error: string;
  eventos_posibles: { tipo: string; titulo: string }[];
}

interface Contacto {
  id: number;
  nombre: string;
  supervisor: boolean;
  activo: boolean;
  vinculado: boolean;
  enlace: string;
  codigo: string;
  de_turno: boolean;
}

interface Turno {
  id: number;
  contacto_id: number;
  contacto: string;
  dias: string;
  desde: string;
  hasta: string;
  ahora: boolean;
}

interface Incidente {
  id: number;
  tipo: string;
  titulo: string;
  objeto: string;
  detalle: Record<string, string>;
  estado: "abierto" | "tomado" | "resuelto";
  nivel: number;
  tomado_por: string | null;
  tomado: string | null;
  creado: string;
  resuelto: string | null;
  avisados: number;
}

const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

function textoDias(dias: string): string {
  if (dias === "0123456") return "Todos los días";
  if (dias === "01234") return "Lunes a viernes";
  if (dias === "56") return "Fin de semana";
  return dias.split("").map((d) => DIAS[Number(d)]).join(", ");
}

export function Avisos() {
  const { usuario } = useSesion();
  const configura = puede(usuario?.rol, "configurar_alertas");
  const ajustes = useDatos<AjustesAvisos>("/pro/avisos/ajustes");
  const contactos = useDatos<Contacto[]>("/pro/avisos/contactos");
  const turnos = useDatos<Turno[]>("/pro/avisos/guardias");
  const recargarEquipo = () => {
    contactos.recargar();
    turnos.recargar();
  };

  return (
    <>
      <Encabezado
        titulo="Avisos al equipo"
        subtitulo="Que cada alerta le llegue a quien está de turno, con «Lo tomo yo» y escalamiento si nadie la atiende."
      />
      <div className="pila" style={{ gap: 14 }}>
        <Incidentes />
        <div className="fila" style={{ alignItems: "flex-start" }}>
          <div className="crece pila" style={{ gap: 14 }}>
            <Contactos datos={contactos.datos} bot={ajustes.datos?.bot ?? ""} configura={configura} onCambio={recargarEquipo} />
            <Guardias turnos={turnos.datos} contactos={contactos.datos ?? []} configura={configura} onCambio={recargarEquipo} />
          </div>
          <div className="crece">
            {ajustes.datos && <AjustesBot key={JSON.stringify(ajustes.datos)} inicial={ajustes.datos} configura={configura} onGuardado={ajustes.recargar} />}
          </div>
        </div>
      </div>
    </>
  );
}

function AjustesBot({ inicial, configura, onGuardado }: { inicial: AjustesAvisos; configura: boolean; onGuardado: () => void }) {
  const { datos: canales } = useDatos<Canal[]>("/alertas/canales");
  const [activo, setActivo] = useState(inicial.activo);
  const [canal, setCanal] = useState(inicial.canal_id ? String(inicial.canal_id) : "");
  const [minutos, setMinutos] = useState(String(inicial.minutos_escalar));
  const [eventos, setEventos] = useState(inicial.eventos);
  const [prueba, setPrueba] = useState<string | null>(null);
  const telegram = canales?.filter((c) => c.tipo === "telegram") ?? [];

  return (
    <Tarjeta titulo="Bot y escalamiento">
      {inicial.error && <div className="aviso atencion" style={{ marginBottom: 12 }}>{inicial.error}</div>}
      {inicial.activo && inicial.bot && !inicial.error && (
        <div className="aviso ok" style={{ marginBottom: 12 }}>Avisando con @{inicial.bot}.</div>
      )}
      <Formulario
        textoBoton="Guardar"
        onEnviar={async () => {
          if (!configura) throw new Error("Tu rol no puede cambiar los avisos.");
          await api("/pro/avisos/ajustes", {
            metodo: "PUT",
            cuerpo: { activo, canal_id: canal ? Number(canal) : null, minutos_escalar: Number(minutos), eventos },
          });
          onGuardado();
        }}
      >
        <Campo
          etiqueta="Bot de Telegram"
          ayuda={telegram.length ? "El bot de un canal de alertas de Telegram. Cada persona se une a él con su enlace." : "Primero agrega un canal de Telegram en Alertas."}
        >
          <select value={canal} onChange={(e) => setCanal(e.target.value)}>
            <option value="">Elegir…</option>
            {telegram.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Escalar a los supervisores si nadie lo toma en (minutos)">
          <input type="number" min={1} max={240} value={minutos} onChange={(e) => setMinutos(e.target.value)} required />
        </Campo>
        <fieldset className="ancho">
          <legend>Qué se avisa al equipo</legend>
          {inicial.eventos_posibles.map((t) => (
            <label key={t.tipo} className="casilla">
              <input
                type="checkbox"
                checked={eventos.includes(t.tipo)}
                onChange={(e) => setEventos(e.target.checked ? [...eventos, t.tipo] : eventos.filter((x) => x !== t.tipo))}
              />{" "}
              {t.titulo}
            </label>
          ))}
        </fieldset>
        <label className="casilla ancho"><input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Avisos al equipo encendidos</label>
      </Formulario>
      {configura && inicial.bot && (
        <div className="fila" style={{ gap: 8, marginTop: 12, alignItems: "center" }}>
          <button
            className="boton chico"
            onClick={async () => {
              try {
                const r = await api<{ enviados: number }>("/pro/avisos/probar", { metodo: "POST" });
                setPrueba(`Mensaje de prueba enviado a ${r.enviados} ${r.enviados === 1 ? "contacto" : "contactos"}.`);
              } catch (e) {
                setPrueba(textoDeError(e));
              }
            }}
          >
            Mandar una prueba
          </button>
          {prueba && <span className="tenue" style={{ fontSize: 13 }}>{prueba}</span>}
        </div>
      )}
      <p className="tenue" style={{ fontSize: 12, marginBottom: 0 }}>
        Las alertas de siempre siguen llegando a sus canales. Esto suma los avisos a personas, con guardias y «Lo tomo yo».
        mufa lee los botones con el mismo bot: no hace falta abrir puertos.
      </p>
    </Tarjeta>
  );
}

function Contactos({ datos, bot, configura, onCambio }: { datos: Contacto[] | null; bot: string; configura: boolean; onCambio: () => void }) {
  const [nombre, setNombre] = useState("");
  const [supervisor, setSupervisor] = useState(false);
  return (
    <Tarjeta titulo="Equipo">
      {datos && datos.length === 0 && <p className="tenue" style={{ marginTop: 0 }}>Agrega a cada técnico, supervisor o grupo del NOC.</p>}
      {datos && datos.length > 0 && (
        <div className="tabla-caja" style={{ marginBottom: 14 }}>
          <table>
            <thead><tr><th>Nombre</th><th>Telegram</th><th /></tr></thead>
            <tbody>
              {datos.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 500 }}>
                    {c.nombre}
                    <div className="fila" style={{ gap: 6, marginTop: 4 }}>
                      {c.supervisor && <span className="pill gris">Supervisor</span>}
                      {c.de_turno && <span className="pill ok">De turno</span>}
                    </div>
                  </td>
                  <td>
                    {c.vinculado ? (
                      <span className="pill ok">Conectado</span>
                    ) : c.enlace ? (
                      <div className="pila" style={{ gap: 4 }}>
                        <span className="tenue" style={{ fontSize: 12 }}>Que abra este enlace en su teléfono:</span>
                        <div className="fila" style={{ gap: 6, alignItems: "center" }}>
                          <a className="mono" href={c.enlace} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>{c.enlace.replace("https://", "")}</a>
                          <BotonCopiar texto={c.enlace} />
                        </div>
                        <span className="tenue" style={{ fontSize: 12 }}>Para un grupo: agrega el bot y escribe <span className="mono">/vincular {c.codigo}</span></span>
                      </div>
                    ) : (
                      <span className="tenue" style={{ fontSize: 12 }}>{bot ? "" : "Elige el bot para ver el enlace."}</span>
                    )}
                  </td>
                  <td>
                    {configura && (
                      <div className="fila" style={{ gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                        <button className="boton chico" onClick={async () => { await api(`/pro/avisos/contactos/${c.id}`, { metodo: "PATCH", cuerpo: { supervisor: !c.supervisor } }); onCambio(); }}>
                          {c.supervisor ? "Quitar supervisor" : "Supervisor"}
                        </button>
                        {c.vinculado && (
                          <button className="boton chico" title="Desconecta su Telegram y genera otro enlace" onClick={async () => { await api(`/pro/avisos/contactos/${c.id}/enlace-nuevo`, { metodo: "POST" }); onCambio(); }}>
                            Enlace nuevo
                          </button>
                        )}
                        <button className="boton chico peligro" onClick={async () => { if (window.confirm(`¿Quitar a ${c.nombre}?`)) { await api(`/pro/avisos/contactos/${c.id}`, { metodo: "DELETE" }); onCambio(); } }}>
                          Quitar
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {configura && (
        <Formulario
          textoBoton="Agregar"
          onEnviar={async () => {
            await api("/pro/avisos/contactos", { metodo: "POST", cuerpo: { nombre, supervisor } });
            setNombre("");
            setSupervisor(false);
            onCambio();
          }}
        >
          <Campo etiqueta="Nombre"><input value={nombre} onChange={(e) => setNombre(e.target.value)} required maxLength={120} placeholder="Ana (N2) o Grupo NOC" /></Campo>
          <label className="casilla"><input type="checkbox" checked={supervisor} onChange={(e) => setSupervisor(e.target.checked)} /> Supervisor: recibe lo que nadie tomó</label>
        </Formulario>
      )}
    </Tarjeta>
  );
}

function Guardias({ turnos, contactos, configura, onCambio }: { turnos: Turno[] | null; contactos: Contacto[]; configura: boolean; onCambio: () => void }) {
  const [contacto, setContacto] = useState("");
  const [dias, setDias] = useState("01234");
  const [desde, setDesde] = useState("08:00");
  const [hasta, setHasta] = useState("17:00");
  // De turno y con Telegram conectado: a quienes les llega de verdad.
  const reciben = contactos.filter((c) => c.de_turno).map((c) => c.nombre);
  const sinConectar = [...new Set(turnos?.filter((t) => t.ahora).map((t) => t.contacto) ?? [])].filter((n) => !reciben.includes(n));
  return (
    <Tarjeta titulo="Guardias">
      <p className="tenue" style={{ marginTop: 0 }}>
        {turnos && turnos.length === 0
          ? "Sin guardias, los avisos le llegan a todo el equipo (menos los supervisores)."
          : reciben.length
            ? `De turno ahora: ${reciben.join(", ")}.`
            : "Ahora no hay nadie de turno con Telegram conectado: los avisos van a los supervisores."}
        {sinConectar.length > 0 && ` ${sinConectar.join(", ")} está de turno pero no conectó su Telegram.`}
      </p>
      {turnos && turnos.length > 0 && (
        <div className="tabla-caja" style={{ marginBottom: 14 }}>
          <table>
            <thead><tr><th>Quién</th><th>Días</th><th>Horario</th><th /></tr></thead>
            <tbody>
              {turnos.map((t) => (
                <tr key={t.id}>
                  <td style={{ fontWeight: 500 }}>{t.contacto} {t.ahora && <span className="pill ok">Ahora</span>}</td>
                  <td>{textoDias(t.dias)}</td>
                  <td className="mono">{t.desde} – {t.hasta}{t.hasta <= t.desde && <span className="tenue"> (+1 día)</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    {configura && <button className="boton chico peligro" onClick={async () => { await api(`/pro/avisos/guardias/${t.id}`, { metodo: "DELETE" }); onCambio(); }}>Quitar</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {configura && contactos.length > 0 && (
        <Formulario
          textoBoton="Agregar turno"
          onEnviar={async () => {
            if (!dias) throw new Error("Elige al menos un día.");
            await api("/pro/avisos/guardias", { metodo: "POST", cuerpo: { contacto_id: Number(contacto), dias, desde, hasta } });
            onCambio();
          }}
        >
          <Campo etiqueta="Quién">
            <select value={contacto} onChange={(e) => setContacto(e.target.value)} required>
              <option value="">Elegir…</option>
              {contactos.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Desde"><input type="time" value={desde} onChange={(e) => setDesde(e.target.value)} required /></Campo>
          <Campo etiqueta="Hasta" ayuda="Si es antes de «desde», el turno termina al día siguiente."><input type="time" value={hasta} onChange={(e) => setHasta(e.target.value)} required /></Campo>
          <fieldset className="ancho">
            <legend>Días</legend>
            <div className="fila" style={{ gap: 10, flexWrap: "wrap" }}>
              {DIAS.map((d, i) => (
                <label key={d} className="casilla">
                  <input
                    type="checkbox"
                    checked={dias.includes(String(i))}
                    onChange={(e) => setDias(e.target.checked ? [...dias, String(i)].sort().join("") : dias.replace(String(i), ""))}
                  />{" "}
                  {d}
                </label>
              ))}
            </div>
          </fieldset>
        </Formulario>
      )}
    </Tarjeta>
  );
}

const ESTADOS: Record<Incidente["estado"], { texto: string; clase: string }> = {
  abierto: { texto: "Sin tomar", clase: "critico" },
  tomado: { texto: "Tomado", clase: "medio" },
  resuelto: { texto: "Resuelto", clase: "ok" },
};

function Incidentes() {
  const { usuario } = useSesion();
  const { datos, recargar } = useDatos<Incidente[]>("/pro/avisos/incidentes?limite=30");
  const [error, setError] = useState<string | null>(null);
  const diagnostica = puede(usuario?.rol, "diagnosticar");
  return (
    <Tarjeta titulo="Avisos recientes" sinRelleno acciones={<button className="boton chico" onClick={recargar}>Actualizar</button>}>
      {error && <div className="aviso error" style={{ margin: 12 }}>{error}</div>}
      {datos && datos.length === 0 ? (
        <Vacio titulo="Todavía no hubo avisos">
          <p className="tenue">Cuando se caiga un equipo o un puerto PON, aparece aquí con quién lo tomó y cuánto tardó en resolverse.</p>
        </Vacio>
      ) : (
        <div className="tabla-caja">
          <table>
            <thead><tr><th>Aviso</th><th>Estado</th><th>Quién</th><th>Cuándo</th><th /></tr></thead>
            <tbody>
              {datos?.map((i) => (
                <tr key={i.id}>
                  <td style={{ fontWeight: 500 }}>
                    {i.titulo}
                    <div className="tenue" style={{ fontWeight: 400 }}>{i.objeto}</div>
                  </td>
                  <td>
                    <span className={`pill ${ESTADOS[i.estado].clase}`}>{ESTADOS[i.estado].texto}</span>
                    {i.nivel > 0 && <div className="tenue" style={{ fontSize: 12, marginTop: 4 }}>Escalado</div>}
                  </td>
                  <td>{i.tomado_por ?? <span className="tenue">—</span>}</td>
                  <td className="tenue">
                    {hace(i.creado)}
                    {i.resuelto && <div style={{ fontSize: 12 }}>resuelto {hace(i.resuelto)}</div>}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {i.estado === "abierto" && diagnostica && (
                      <button
                        className="boton chico primario"
                        onClick={async () => {
                          try {
                            await api(`/pro/avisos/incidentes/${i.id}/tomar`, { metodo: "POST" });
                            recargar();
                          } catch (e) {
                            setError(textoDeError(e));
                          }
                        }}
                      >
                        Lo tomo yo
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Tarjeta>
  );
}
