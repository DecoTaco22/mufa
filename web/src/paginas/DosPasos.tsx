import { AppsDosPasos } from "../componentes/AppsDosPasos";
import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { api, textoDeError } from "../api";
import { Campo, MensajeError, Formulario } from "../componentes/ui";
import { useSesion } from "../sesion";
import { descargar } from "../util";

/** Configurar la verificación en dos pasos. Obligatoria para N3, Senior y Admin. */
export function DosPasos({ obligatorio = false }: { obligatorio?: boolean }) {
  const { usuario, recargar, salir } = useSesion();
  const [secreto, setSecreto] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [codigo, setCodigo] = useState("");
  const [codigos, setCodigos] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const iniciado = useRef(false);

  useEffect(() => {
    // Una sola vez: cada llamada genera un secreto nuevo y anula el anterior.
    if (iniciado.current) return;
    iniciado.current = true;
    api<{ secreto: string; uri: string }>("/auth/2fa/iniciar", { metodo: "POST" })
      .then(async (r) => {
        setSecreto(r.secreto);
        setQr(await QRCode.toDataURL(r.uri, { margin: 1, width: 220 }));
      })
      .catch((e: unknown) => setError(textoDeError(e)));
  }, []);

  if (codigos) {
    return (
      <div className="centrado">
        <div className="tarjeta acceso pila" style={{ width: "min(460px, 100%)" }}>
          <h2>Guarda tus códigos de recuperación</h2>
          <p className="tenue" style={{ margin: 0 }}>
            Si pierdes el teléfono, cada uno de estos códigos te deja entrar una vez. Es la única vez que se muestran.
          </p>
          <pre className="codigos">{codigos.map((c) => <span key={c}>{c}</span>)}</pre>
          <div className="fila">
            <button className="boton" onClick={() => descargar("mufa-codigos-de-recuperacion.txt", codigos.join("\n") + "\n")}>
              Descargar .txt
            </button>
            <button className="boton primario" onClick={() => void recargar()}>Ya los guardé</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="centrado">
      <div className="tarjeta acceso pila" style={{ width: "min(460px, 100%)" }}>
        <h2>Verificación en dos pasos</h2>
        {obligatorio && (
          <div className="aviso info">
            Tu rol puede cambiar la red, así que necesitas un segundo paso además de la contraseña.
          </div>
        )}
        <ol className="tenue" style={{ margin: 0, paddingLeft: 18 }}>
          <li>Abre una app de autenticación en tu teléfono (abajo, las compatibles).</li>
          <li>Escanea este código (o escribe la clave a mano).</li>
          <li>Escribe los 6 dígitos que muestra la app.</li>
        </ol>
        <AppsDosPasos compacto />
        <MensajeError mensaje={error} />
        {qr && <img src={qr} alt="Código QR para la app de autenticación" style={{ width: 220, height: 220, alignSelf: "center", borderRadius: 10, background: "#fff" }} />}
        {secreto && <code style={{ textAlign: "center", wordBreak: "break-all" }}>{secreto}</code>}
        <Formulario
          textoBoton="Activar"
          onEnviar={async () => {
            const r = await api<{ codigos_recuperacion: string[] }>("/auth/2fa/confirmar", {
              metodo: "POST",
              cuerpo: { codigo: codigo.trim() },
            });
            setCodigos(r.codigos_recuperacion);
          }}
        >
          <Campo etiqueta="Código de 6 dígitos">
            <input inputMode="numeric" pattern="\d{6}" maxLength={6} autoComplete="one-time-code" value={codigo} onChange={(e) => setCodigo(e.target.value)} required />
          </Campo>
        </Formulario>
        {obligatorio && (
          <button className="boton-texto" onClick={() => void salir()}>
            Salir ({usuario?.usuario})
          </button>
        )}
      </div>
    </div>
  );
}
