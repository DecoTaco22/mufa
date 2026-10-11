import { type FormEvent, useState } from "react";
import { api, ErrorApi, textoDeError } from "../api";
import { Campo, MensajeError } from "../componentes/ui";
import { useSesion } from "../sesion";

export function Ingreso({ aviso }: { aviso?: string } = {}) {
  const { recargar } = useSesion();
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [codigo, setCodigo] = useState("");
  const [pideCodigo, setPideCodigo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function entrar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await api("/auth/login", {
        metodo: "POST",
        cuerpo: { usuario, password, codigo: pideCodigo ? codigo.trim() : null },
      });
      await recargar();
    } catch (err) {
      if (err instanceof ErrorApi && err.cabeceras.get("X-Mufa-Dos-Pasos") === "requerido" && !pideCodigo) {
        setPideCodigo(true);
      } else {
        setError(textoDeError(err));
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="centrado">
      <form className="tarjeta acceso pila" onSubmit={entrar} style={{ gap: 14 }}>
        <div className="marca">
          <img src="/favicon.svg" alt="" />
          mufa
        </div>
        <p className="tenue" style={{ textAlign: "center", margin: 0 }}>
          Monitoreo y auditoría de redes
        </p>
        {aviso && <div className="aviso ok">{aviso}</div>}
        {!pideCodigo ? (
          <>
            <Campo etiqueta="Usuario o email">
              <input autoFocus autoComplete="username" value={usuario} onChange={(e) => setUsuario(e.target.value)} required />
            </Campo>
            <Campo etiqueta="Contraseña">
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </Campo>
          </>
        ) : (
          <Campo etiqueta="Código de verificación" ayuda="Los 6 dígitos de tu app de autenticación, o un código de recuperación (xxxxx-xxxxx).">
            <input autoFocus inputMode="text" autoComplete="one-time-code" value={codigo} onChange={(e) => setCodigo(e.target.value)} required />
          </Campo>
        )}
        <MensajeError mensaje={error} />
        <button className="boton primario" type="submit" disabled={enviando} style={{ justifyContent: "center" }}>
          {enviando ? "Entrando…" : pideCodigo ? "Verificar" : "Entrar"}
        </button>
        {pideCodigo && (
          <button type="button" className="boton-texto" onClick={() => { setPideCodigo(false); setCodigo(""); }}>
            Volver
          </button>
        )}
      </form>
    </div>
  );
}
