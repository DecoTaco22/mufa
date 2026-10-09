import { AppsDosPasos, ROLES_CON_DOS_PASOS } from "../componentes/AppsDosPasos";
import { CuadroDeRoles, RESUMEN_DE_ROL } from "../componentes/CuadroDeRoles";
import { useState } from "react";
import { api, textoDeError } from "../api";
import { Campo, Cargando, Encabezado, Formulario, MensajeError, Modal, Tarjeta } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Rol, Usuario } from "../tipos";
import { NOMBRES_DE_ROL, useDatos } from "../util";

const ROLES = Object.keys(NOMBRES_DE_ROL) as Rol[];

export function Usuarios() {
  const { usuario: yo } = useSesion();
  const { datos, error, cargando, recargar } = useDatos<Usuario[]>("/usuarios");
  const [editando, setEditando] = useState<Usuario | "nuevo" | null>(null);

  return (
    <>
      <Encabezado
        titulo="Usuarios"
        subtitulo="Técnico N2, Ingeniero N3, Senior y Admin necesitan verificación en dos pasos: pueden usar las credenciales de los equipos"
        acciones={<button className="boton primario" onClick={() => setEditando("nuevo")}>Nuevo usuario</button>}
      />
      <MensajeError mensaje={error} />
      <Tarjeta sinRelleno>
        {cargando && !datos ? (
          <Cargando />
        ) : (
          <div className="tabla-caja">
            <table>
              <thead><tr><th>Usuario</th><th>Rol</th><th>Dos pasos</th><th>Estado</th></tr></thead>
              <tbody>
                {datos?.map((u) => (
                  <tr key={u.id} className="clic" onClick={() => setEditando(u)}>
                    <td>
                      <div style={{ fontWeight: 500 }}>{u.nombre} {u.id === yo?.id && <span className="tenue">(tú)</span>}</div>
                      <div className="tenue mono">{u.usuario}{u.email ? ` · ${u.email}` : ""}</div>
                    </td>
                    <td>{NOMBRES_DE_ROL[u.rol]}</td>
                    <td>{u.totp_activo ? <span className="pill ok">Activa</span> : <span className="pill gris">No</span>}</td>
                    <td>{u.activo ? "Activo" : <span className="tenue">Desactivado</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
      <Tarjeta titulo="Qué puede hacer cada rol" sinRelleno>
        <CuadroDeRoles />
      </Tarjeta>
      {editando === "nuevo" && <NuevoUsuario onCerrar={() => setEditando(null)} onListo={() => { setEditando(null); recargar(); }} />}
      {editando && editando !== "nuevo" && (
        <EditarUsuario usuario={editando} onCerrar={() => setEditando(null)} onListo={() => { setEditando(null); recargar(); }} />
      )}
    </>
  );
}

function NuevoUsuario(props: { onCerrar: () => void; onListo: () => void }) {
  const [usuario, setUsuario] = useState("");
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<Rol>("tecnico_n2");
  const [password, setPassword] = useState("");
  return (
    <Modal titulo="Nuevo usuario" onCerrar={props.onCerrar}>
      <Formulario
        textoBoton="Crear"
        onCancelar={props.onCerrar}
        onEnviar={async () => {
          await api("/usuarios", { metodo: "POST", cuerpo: { usuario: usuario.trim().toLowerCase(), nombre, email: email || null, rol, password } });
          props.onListo();
        }}
      >
        <div className="formulario">
          <Campo etiqueta="Usuario" ayuda="Minúsculas, 3 a 32 caracteres. Será también su usuario en los equipos (AAA).">
            <input value={usuario} onChange={(e) => setUsuario(e.target.value)} required pattern="[a-zA-Z][a-zA-Z0-9._\-]{2,31}" autoComplete="off" />
          </Campo>
          <Campo etiqueta="Nombre"><input value={nombre} onChange={(e) => setNombre(e.target.value)} required /></Campo>
          <Campo etiqueta="Email (opcional)"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Campo>
          <Campo etiqueta="Rol" ayuda={RESUMEN_DE_ROL[rol]}>
            <select value={rol} onChange={(e) => setRol(e.target.value as Rol)}>
              {ROLES.map((r) => <option key={r} value={r}>{NOMBRES_DE_ROL[r]}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Contraseña inicial" ayuda="Mínimo 12 caracteres" ancho>
            <input type="password" minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" />
          </Campo>
        </div>
        {ROLES_CON_DOS_PASOS.includes(rol) && (
          <div className="aviso info">
            <strong>{NOMBRES_DE_ROL[rol]} entra con verificación en dos pasos.</strong> La primera vez que inicie sesión,
            mufa le muestra un código QR para escanear con una de estas apps:
            <AppsDosPasos />
          </div>
        )}
      </Formulario>
    </Modal>
  );
}

function EditarUsuario(props: { usuario: Usuario; onCerrar: () => void; onListo: () => void }) {
  const u = props.usuario;
  const [nombre, setNombre] = useState(u.nombre);
  const [rol, setRol] = useState<Rol>(u.rol);
  const [activo, setActivo] = useState(u.activo);
  const [password, setPassword] = useState("");
  const [aviso, setAviso] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);

  async function accion(hacer: () => Promise<void>, texto: string) {
    try {
      await hacer();
      setAviso({ tipo: "ok", texto });
    } catch (e) {
      setAviso({ tipo: "error", texto: textoDeError(e) });
    }
  }

  return (
    <Modal titulo={u.nombre} onCerrar={props.onCerrar}>
      <Formulario
        textoBoton="Guardar"
        onCancelar={props.onCerrar}
        onEnviar={async () => {
          await api(`/usuarios/${u.id}`, { metodo: "PATCH", cuerpo: { nombre, rol, activo } });
          props.onListo();
        }}
      >
        <div className="formulario">
          <Campo etiqueta="Nombre"><input value={nombre} onChange={(e) => setNombre(e.target.value)} required /></Campo>
          <Campo etiqueta="Rol" ayuda={RESUMEN_DE_ROL[rol]}>
            <select value={rol} onChange={(e) => setRol(e.target.value as Rol)}>
              {ROLES.map((r) => <option key={r} value={r}>{NOMBRES_DE_ROL[r]}</option>)}
            </select>
          </Campo>
          <label className="casilla ancho"><input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo (desactivarlo cierra sus sesiones)</label>
        </div>
      </Formulario>
      <hr style={{ border: "none", borderTop: "1px solid var(--line)", width: "100%" }} />
      {aviso && <div className={`aviso ${aviso.tipo}`}>{aviso.texto}</div>}
      <div className="formulario">
        <Campo etiqueta="Nueva contraseña" ayuda="Cierra todas sus sesiones">
          <input type="password" minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </Campo>
      </div>
      <div className="fila">
        <button className="boton" disabled={password.length < 12} onClick={() => void accion(async () => {
          await api(`/usuarios/${u.id}/password`, { metodo: "POST", cuerpo: { password } });
          setPassword("");
        }, "Contraseña restablecida.")}>Restablecer contraseña</button>
        {u.totp_activo && (
          <button className="boton peligro" onClick={() => {
            if (window.confirm(`¿Restablecer la verificación en dos pasos de ${u.nombre}? Tendrá que configurarla de nuevo.`))
              void accion(() => api(`/usuarios/${u.id}/2fa/restablecer`, { metodo: "POST" }), "Verificación en dos pasos restablecida.");
          }}>Restablecer dos pasos</button>
        )}
      </div>
    </Modal>
  );
}
