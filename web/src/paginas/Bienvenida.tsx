import { type FormEvent, useState } from "react";
import { api, textoDeError } from "../api";
import { Campo, Cargando, MensajeError } from "../componentes/ui";
import { useDatos } from "../util";
import { Ingreso } from "./Ingreso";

/** Sin usuarios todavía: crea el administrador. Si no, es la pantalla de ingreso. */
export function EntradaOBienvenida() {
  const { datos, cargando } = useDatos<{ necesita_admin: boolean }>("/sistema/inicial");
  const [creado, setCreado] = useState(false);
  if (cargando && !datos) return <Cargando />;
  if (datos?.necesita_admin && !creado) return <Bienvenida onListo={() => setCreado(true)} />;
  return <Ingreso aviso={creado ? "Listo. Entra con tu usuario y contraseña nuevos." : undefined} />;
}

function Bienvenida({ onListo }: { onListo: () => void }) {
  // El lanzador de escritorio abre el navegador con el token en la URL.
  const [token, setToken] = useState(() => new URLSearchParams(location.search).get("token") ?? "");
  // Con el token en la URL (app de escritorio) no hace falta mostrar el campo.
  const [tokenAutomatico] = useState(() => new URLSearchParams(location.search).has("token"));
  const [usuario, setUsuario] = useState("");
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [repetida, setRepetida] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function crear(e: FormEvent) {
    e.preventDefault();
    if (password !== repetida) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      await api("/sistema/inicial", {
        metodo: "POST",
        cuerpo: { token: token.trim(), usuario: usuario.trim().toLowerCase(), nombre, email: email || null, password },
      });
      history.replaceState(null, "", "/");
      onListo();
    } catch (err) {
      setError(textoDeError(err));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="centrado">
      <form className="tarjeta acceso pila" onSubmit={crear} style={{ gap: 14, maxWidth: 420 }}>
        <div className="marca">
          <img src="/favicon.svg" alt="" />
          mufa
        </div>
        <div style={{ textAlign: "center" }}>
          <h2 style={{ margin: "0 0 4px" }}>Bienvenido</h2>
          <p className="tenue" style={{ margin: 0 }}>Crea la cuenta de administrador. Después vas a activar la verificación en dos pasos.</p>
        </div>
        {!tokenAutomatico && (
          <Campo etiqueta="Token de instalación" ayuda="Lo muestra el servidor al arrancar (con Docker: docker compose logs mufa).">
            <input className="mono" value={token} onChange={(e) => setToken(e.target.value)} required autoComplete="off" />
          </Campo>
        )}
        <Campo etiqueta="Usuario" ayuda="Minúsculas, números, punto, guion o guion bajo.">
          <input autoFocus value={usuario} onChange={(e) => setUsuario(e.target.value)} required autoComplete="username" pattern="[a-zA-Z][a-zA-Z0-9._\-]{2,31}" />
        </Campo>
        <Campo etiqueta="Nombre">
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} required autoComplete="name" />
        </Campo>
        <Campo etiqueta="Email (opcional)">
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </Campo>
        <Campo etiqueta="Contraseña" ayuda="Mínimo 12 caracteres. Una frase larga es más segura y más fácil de recordar.">
          <input type="password" minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" />
        </Campo>
        <Campo etiqueta="Repite la contraseña">
          <input type="password" minLength={12} value={repetida} onChange={(e) => setRepetida(e.target.value)} required autoComplete="new-password" />
        </Campo>
        <MensajeError mensaje={error} />
        <button className="boton primario" type="submit" disabled={enviando} style={{ justifyContent: "center" }}>
          {enviando ? "Creando…" : "Crear administrador"}
        </button>
      </form>
    </div>
  );
}
