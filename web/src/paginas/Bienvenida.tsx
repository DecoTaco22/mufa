import { type FormEvent, type ReactNode, useState } from "react";
import { api, textoDeError } from "../api";
import { Campo, Cargando, MensajeError, Segmentado } from "../componentes/ui";
import { useDatos } from "../util";
import { Ingreso } from "./Ingreso";

type Inicial = { necesita_admin: boolean; puede_importar: boolean };
type Modo = "nueva" | "traer";

/** Sin usuarios todavía: crea el administrador o trae los datos de otra computadora. Si no, el ingreso. */
export function EntradaOBienvenida() {
  const { datos, cargando } = useDatos<Inicial>("/sistema/inicial");
  const [listo, setListo] = useState<string | null>(null);
  if (cargando && !datos) return <Cargando />;
  if (datos?.necesita_admin && !listo) return <Bienvenida puedeImportar={datos.puede_importar} onListo={setListo} />;
  return <Ingreso aviso={listo ?? undefined} />;
}

function Bienvenida({ puedeImportar, onListo }: { puedeImportar: boolean; onListo: (aviso: string) => void }) {
  // El lanzador de escritorio abre la ventana con el token en la URL.
  const [token, setToken] = useState(() => new URLSearchParams(location.search).get("token") ?? "");
  // Con el token en la URL (app de escritorio) no hace falta mostrar el campo.
  const [tokenAutomatico] = useState(() => new URLSearchParams(location.search).has("token"));
  const [modo, setModo] = useState<Modo>("nueva");

  const campoToken = !tokenAutomatico && (
    <Campo etiqueta="Token de instalación" ayuda="Lo muestra el servidor al arrancar (con Docker: docker compose logs mufa).">
      <input className="mono" value={token} onChange={(e) => setToken(e.target.value)} required autoComplete="off" />
    </Campo>
  );

  return (
    <div className="centrado">
      <div className="tarjeta acceso pila" style={{ gap: 14, maxWidth: 440 }}>
        <div className="marca">
          <img src="/favicon.svg" alt="" />
          mufa
        </div>
        <div style={{ textAlign: "center" }}>
          <h2 style={{ margin: "0 0 4px" }}>Bienvenido</h2>
          <p className="tenue" style={{ margin: 0 }}>
            {modo === "nueva"
              ? "Crea la cuenta de administrador. Después vas a activar la verificación en dos pasos."
              : "Usa la cuenta que ya tienes: trae tus datos desde la otra computadora."}
          </p>
        </div>
        {puedeImportar && (
          <Segmentado
            etiqueta="Cómo empezar"
            valor={modo}
            onCambio={setModo}
            opciones={[
              { valor: "nueva", texto: "Soy nuevo en mufa" },
              { valor: "traer", texto: "Ya tengo cuenta" },
            ]}
          />
        )}
        {modo === "nueva" ? (
          <CrearAdmin token={token} campoToken={campoToken} onListo={() => onListo("Listo. Entra con tu usuario y contraseña nuevos.")} />
        ) : (
          <TraerDatos token={token} campoToken={campoToken} onListo={onListo} />
        )}
      </div>
    </div>
  );
}

function TraerDatos({ token, campoToken, onListo }: { token: string; campoToken: ReactNode; onListo: (aviso: string) => void }) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [frase, setFrase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function traer(e: FormEvent) {
    e.preventDefault();
    if (!archivo) return;
    setEnviando(true);
    setError(null);
    try {
      const formulario = new FormData();
      formulario.append("archivo", archivo);
      formulario.append("frase", frase);
      formulario.append("token", token.trim());
      await api("/sistema/importar", { metodo: "POST", formulario });
      history.replaceState(null, "", "/");
      onListo("Tus datos ya están en esta computadora. Entra con tu usuario y contraseña de siempre.");
    } catch (err) {
      setError(textoDeError(err));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className="pila" onSubmit={traer} style={{ gap: 14 }}>
      <ol className="pasos-traslado">
        <li>En la computadora donde ya usas mufa, abre <strong>Ajustes › Llevar a otra computadora</strong> y descarga el archivo.</li>
        <li>Pásalo a esta computadora (USB, correo o la nube) y elígelo aquí.</li>
      </ol>
      {campoToken}
      <label className="elegir-archivo">
        <input type="file" accept=".mufa" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} required />
        <span className="boton">Elegir archivo</span>
        <span className={archivo ? "mono" : "tenue"}>{archivo ? archivo.name : "Ningún archivo .mufa elegido"}</span>
      </label>
      <Campo etiqueta="Frase del archivo" ayuda="La que elegiste al descargarlo.">
        <input type="password" value={frase} onChange={(e) => setFrase(e.target.value)} required autoComplete="off" />
      </Campo>
      <MensajeError mensaje={error} />
      <button className="boton primario" type="submit" disabled={enviando || !archivo} style={{ justifyContent: "center" }}>
        {enviando ? "Trayendo tus datos…" : "Traer mis datos"}
      </button>
      <p className="tenue" style={{ margin: 0, fontSize: 12, textAlign: "center" }}>
        Para que tu equipo use la misma mufa desde varias computadoras, instálala en un servidor.
      </p>
    </form>
  );
}

function CrearAdmin({ token, campoToken, onListo }: { token: string; campoToken: ReactNode; onListo: () => void }) {
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
    <form className="pila" onSubmit={crear} style={{ gap: 14 }}>
        {campoToken}
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
  );
}
