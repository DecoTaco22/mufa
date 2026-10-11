import { useState } from "react";
import { api, textoDeError } from "../api";
import { Campo, Cargando, Encabezado, Formulario, MensajeError, Modal, Segmentado, Tarjeta, Vacio } from "../componentes/ui";
import type { Canal } from "../tipos";
import { useDatos } from "../util";

const TIPOS = { telegram: "Telegram", correo: "Correo", webhook: "Webhook" } as const;

export function Alertas() {
  const { datos, error, cargando, recargar } = useDatos<Canal[]>("/alertas/canales");
  const { datos: tipos } = useDatos<Record<string, string>>("/alertas/tipos");
  const [editando, setEditando] = useState<Canal | "nuevo" | null>(null);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);

  async function probar(canal: Canal) {
    setAviso(null);
    try {
      await api(`/alertas/canales/${canal.id}/probar`, { metodo: "POST" });
      setAviso({ tipo: "ok", texto: `Aviso de prueba enviado por ${canal.nombre}.` });
    } catch (e) {
      setAviso({ tipo: "error", texto: textoDeError(e) });
    }
  }

  return (
    <>
      <Encabezado
        titulo="Alertas"
        subtitulo="A dónde avisar cuando un equipo se cae, cambia su configuración o aparece un hallazgo crítico"
        acciones={<button className="boton primario" onClick={() => setEditando("nuevo")}>Nuevo canal</button>}
      />
      <MensajeError mensaje={error} />
      {aviso && <div className={`aviso ${aviso.tipo}`}>{aviso.texto}</div>}
      <Tarjeta sinRelleno>
        {cargando && !datos ? (
          <Cargando />
        ) : !datos?.length ? (
          <Vacio titulo="Sin canales de alerta">Agrega un chat de Telegram, un correo o un webhook.</Vacio>
        ) : (
          <div className="tabla-caja">
            <table>
              <thead><tr><th>Canal</th><th>Tipo</th><th>Destino</th><th>Avisa de</th><th /></tr></thead>
              <tbody>
                {datos.map((c) => (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 500 }}>
                      {c.nombre} {!c.activo && <span className="pill gris">Pausado</span>}
                    </td>
                    <td>{TIPOS[c.tipo]}</td>
                    <td className="mono" style={{ maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis" }}>{c.destino}</td>
                    <td className="tenue">{c.eventos.map((e) => tipos?.[e] ?? e).join(", ")}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button className="boton chico" onClick={() => void probar(c)}>Probar</button>{" "}
                      <button className="boton chico" onClick={() => setEditando(c)}>Editar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
      {editando && tipos && (
        <FormularioCanal
          canal={editando === "nuevo" ? undefined : editando}
          tipos={tipos}
          onCerrar={() => setEditando(null)}
          onListo={() => { setEditando(null); recargar(); }}
        />
      )}
    </>
  );
}

function FormularioCanal(props: { canal?: Canal; tipos: Record<string, string>; onCerrar: () => void; onListo: () => void }) {
  const c = props.canal;
  const [tipo, setTipo] = useState<Canal["tipo"]>(c?.tipo ?? "telegram");
  const [nombre, setNombre] = useState(c?.nombre ?? "");
  const [destino, setDestino] = useState(c?.destino ?? "");
  const [secreto, setSecreto] = useState("");
  const [servidor, setServidor] = useState(c?.correo?.servidor ?? "");
  const [puerto, setPuerto] = useState(String(c?.correo?.puerto ?? 587));
  const [usuario, setUsuario] = useState(c?.correo?.usuario ?? "");
  const [remitente, setRemitente] = useState(c?.correo?.remitente ?? "");
  const [eventos, setEventos] = useState<string[]>(c?.eventos ?? ["equipo.caido", "auditoria.critico"]);
  const [activo, setActivo] = useState(c?.activo ?? true);

  const [etiquetaDestino, ayudaDestino] = {
    telegram: ["ID del chat", "Por ejemplo -1001234567890 (agrega el bot al grupo)"],
    correo: ["Enviar a", "noc@tuempresa.com"],
    webhook: ["URL", "https://… (recibe un POST con JSON firmado)"],
  }[tipo] as [string, string];
  const secretos = {
    telegram: "Token del bot",
    correo: "Contraseña SMTP",
    webhook: "Clave para firmar (opcional)",
  }[tipo];

  return (
    <Modal titulo={c ? `Editar ${c.nombre}` : "Nuevo canal de alerta"} onCerrar={props.onCerrar}>
      <Formulario
        textoBoton="Guardar"
        onCancelar={props.onCerrar}
        onEnviar={async () => {
          const cuerpo = {
            nombre,
            tipo,
            destino,
            // Vacío: en edición se conserva el secreto guardado.
            secreto: secreto || null,
            correo: tipo === "correo" ? { servidor, puerto: Number(puerto), usuario, remitente } : null,
            eventos,
            activo,
          };
          if (c) await api(`/alertas/canales/${c.id}`, { metodo: "PUT", cuerpo });
          else await api("/alertas/canales", { metodo: "POST", cuerpo });
          props.onListo();
        }}
      >
        {!c && (
          <Segmentado etiqueta="Tipo de canal" valor={tipo} onCambio={setTipo} opciones={Object.entries(TIPOS).map(([valor, texto]) => ({ valor: valor as Canal["tipo"], texto }))} />
        )}
        <div className="formulario">
          <Campo etiqueta="Nombre"><input value={nombre} onChange={(e) => setNombre(e.target.value)} required placeholder="NOC" /></Campo>
          <Campo etiqueta={etiquetaDestino} ayuda={ayudaDestino}><input value={destino} onChange={(e) => setDestino(e.target.value)} required /></Campo>
          <Campo etiqueta={secretos} ayuda={c?.tiene_secreto ? "Vacío = no cambiar" : "Se guarda cifrado y no se vuelve a mostrar"}>
            <input type="password" value={secreto} onChange={(e) => setSecreto(e.target.value)} autoComplete="new-password" required={tipo === "telegram" && !c?.tiene_secreto} />
          </Campo>
          {tipo === "correo" && (
            <>
              <Campo etiqueta="Servidor SMTP"><input value={servidor} onChange={(e) => setServidor(e.target.value)} required placeholder="smtp.tuempresa.com" /></Campo>
              <Campo etiqueta="Puerto" ayuda="587 (STARTTLS) o 465 (SSL)"><input type="number" value={puerto} onChange={(e) => setPuerto(e.target.value)} /></Campo>
              <Campo etiqueta="Usuario SMTP"><input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="off" /></Campo>
              <Campo etiqueta="Remitente"><input value={remitente} onChange={(e) => setRemitente(e.target.value)} placeholder="mufa@tuempresa.com" /></Campo>
            </>
          )}
        </div>
        <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
          <legend className="tenue" style={{ fontSize: 12, marginBottom: 6 }}>Avisar cuando</legend>
          <div className="pila" style={{ gap: 6 }}>
            {Object.entries(props.tipos).map(([clave, texto]) => (
              <label key={clave} className="casilla">
                <input
                  type="checkbox"
                  checked={eventos.includes(clave)}
                  onChange={(e) => setEventos(e.target.checked ? [...eventos, clave] : eventos.filter((x) => x !== clave))}
                />
                {texto}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="casilla"><input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo</label>
        {c && (
          <button type="button" className="boton peligro" style={{ alignSelf: "flex-start" }} onClick={async () => {
            if (window.confirm(`¿Borrar el canal ${c.nombre}?`)) { await api(`/alertas/canales/${c.id}`, { metodo: "DELETE" }); props.onListo(); }
          }}>Borrar canal</button>
        )}
      </Formulario>
    </Modal>
  );
}
