import { useEffect, useState } from "react";
import { api } from "../api";
import { TarjetaActualizacion } from "../componentes/Actualizacion";
import { Campo, Encabezado, Formulario, Tarjeta } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Licencia, Sitio } from "../tipos";
import { SITIO } from "./Pro";
import { descargar, fecha, NOMBRES_DE_ROL, puede, useDatos } from "../util";

export function Ajustes() {
  const { usuario } = useSesion();
  return (
    <>
      <Encabezado titulo="Ajustes" />
      <div className="fila">
        <div className="crece pila" style={{ gap: 14 }}>
          <MiCuenta />
          {usuario?.totp_activo && <CodigosRecuperacion />}
          {puede(usuario?.rol, "administrar_usuarios") && <LlevarAOtraComputadora />}
        </div>
        <div className="crece pila" style={{ gap: 14 }}>
          <LicenciaYPlan />
          <TarjetaActualizacion />
          {puede(usuario?.rol, "gestionar_equipos") && <Sitios />}
          <AcercaDe />
        </div>
      </div>
    </>
  );
}

function MiCuenta() {
  const { usuario, recargar } = useSesion();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetida, setRepetida] = useState("");
  if (!usuario) return null;
  return (
    <Tarjeta titulo="Mi cuenta">
      <div className="pila" style={{ marginBottom: 16 }}>
        <div><span className="tenue">Usuario </span><span className="mono">{usuario.usuario}</span></div>
        <div><span className="tenue">Rol </span>{NOMBRES_DE_ROL[usuario.rol]}</div>
        <div><span className="tenue">Verificación en dos pasos </span>{usuario.totp_activo ? "activa" : "no activa"}</div>
      </div>
      <h3 style={{ marginBottom: 10 }}>Cambiar contraseña</h3>
      <Formulario
        textoBoton="Cambiar contraseña"
        onEnviar={async () => {
          if (nueva !== repetida) throw new Error("Las contraseñas nuevas no coinciden.");
          await api("/auth/password", { metodo: "POST", cuerpo: { actual, nueva } });
          // Cambiar la contraseña cierra todas las sesiones: hay que volver a entrar.
          await recargar();
        }}
      >
        <Campo etiqueta="Contraseña actual"><input type="password" value={actual} onChange={(e) => setActual(e.target.value)} required autoComplete="current-password" /></Campo>
        <Campo etiqueta="Nueva contraseña" ayuda="Mínimo 12 caracteres. Vas a tener que volver a entrar.">
          <input type="password" minLength={12} value={nueva} onChange={(e) => setNueva(e.target.value)} required autoComplete="new-password" />
        </Campo>
        <Campo etiqueta="Repetir la nueva"><input type="password" value={repetida} onChange={(e) => setRepetida(e.target.value)} required autoComplete="new-password" /></Campo>
      </Formulario>
    </Tarjeta>
  );
}

function CodigosRecuperacion() {
  const [password, setPassword] = useState("");
  const [codigo, setCodigo] = useState("");
  const [codigos, setCodigos] = useState<string[] | null>(null);
  return (
    <Tarjeta titulo="Códigos de recuperación">
      {codigos ? (
        <div className="pila">
          <div className="aviso atencion">Los anteriores ya no sirven. Guarda estos: es la única vez que se muestran.</div>
          <pre className="codigos">{codigos.map((c) => <span key={c}>{c}</span>)}</pre>
          <button className="boton" style={{ alignSelf: "flex-start" }} onClick={() => descargar("mufa-codigos-de-recuperacion.txt", codigos.join("\n") + "\n")}>
            Descargar .txt
          </button>
        </div>
      ) : (
        <>
          <p className="tenue" style={{ marginTop: 0 }}>Genera diez códigos nuevos e invalida los anteriores.</p>
          <Formulario
            textoBoton="Generar códigos nuevos"
            onEnviar={async () => {
              const r = await api<{ codigos_recuperacion: string[] }>("/auth/2fa/codigos-recuperacion", { metodo: "POST", cuerpo: { password, codigo } });
              setCodigos(r.codigos_recuperacion);
            }}
          >
            <div className="formulario">
              <Campo etiqueta="Contraseña"><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" /></Campo>
              <Campo etiqueta="Código de la app"><input inputMode="numeric" maxLength={6} value={codigo} onChange={(e) => setCodigo(e.target.value)} required autoComplete="one-time-code" /></Campo>
            </div>
          </Formulario>
        </>
      )}
    </Tarjeta>
  );
}

function LlevarAOtraComputadora() {
  const { datos } = useDatos<{ puede_importar: boolean }>("/sistema/inicial");
  const [password, setPassword] = useState("");
  const [frase, setFrase] = useState("");
  const [repetida, setRepetida] = useState("");
  const [listo, setListo] = useState<string | null>(null);
  // Con PostgreSQL (servidor) se respalda la base del servidor: esto es para la app de escritorio.
  if (!datos?.puede_importar) return null;
  return (
    <Tarjeta titulo="Llevar a otra computadora">
      <p className="tenue" style={{ marginTop: 0 }}>
        Descarga todos tus datos (cuentas, equipos, respaldos e IPAM) en un archivo cifrado. En la otra computadora, instala
        mufa, elige <strong>Ya tengo cuenta</strong> y abre el archivo: entras con tu mismo usuario y contraseña.
      </p>
      {listo && <div className="aviso ok" style={{ marginBottom: 12 }}>Descargado: {listo}. Guarda la frase: sin ella el archivo no se puede abrir.</div>}
      <Formulario
        textoBoton="Descargar mis datos"
        onEnviar={async () => {
          if (frase !== repetida) throw new Error("Las frases no coinciden.");
          const r = await api<{ nombre: string; contenido: string }>("/sistema/exportar", { metodo: "POST", cuerpo: { password, frase } });
          descargar(r.nombre, r.contenido);
          setListo(r.nombre);
          setPassword("");
          setFrase("");
          setRepetida("");
        }}
      >
        <Campo etiqueta="Tu contraseña"><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" /></Campo>
        <Campo etiqueta="Frase para el archivo" ayuda="Mínimo 12 caracteres. El archivo lleva las claves de tus equipos: sin esta frase nadie puede abrirlo.">
          <input type="password" minLength={12} value={frase} onChange={(e) => setFrase(e.target.value)} required autoComplete="new-password" />
        </Campo>
        <Campo etiqueta="Repite la frase"><input type="password" minLength={12} value={repetida} onChange={(e) => setRepetida(e.target.value)} required autoComplete="new-password" /></Campo>
      </Formulario>
    </Tarjeta>
  );
}

function AcercaDe() {
  return (
    <Tarjeta titulo="Acerca de mufa">
      <p className="tenue" style={{ marginTop: 0 }}>
        mufa es gratis y de código abierto. Lo hace una sola persona en Guatemala: si te sirve, puedes invitarle un café o
        ser fundador de Pro.
      </p>
      <div className="fila" style={{ gap: 8, flexWrap: "wrap" }}>
        <a className="boton primario" href={`${SITIO}/apoyar`} target="_blank" rel="noreferrer">Apoyar mufa</a>
        <a className="boton" href={`${SITIO}/#ideas`} target="_blank" rel="noreferrer">Sugerir una idea</a>
        <a className="boton" href="https://github.com/DecoTaco22/mufa" target="_blank" rel="noreferrer">Código en GitHub</a>
      </div>
    </Tarjeta>
  );
}

function LicenciaYPlan() {
  const { usuario } = useSesion();
  const { datos, recargar } = useDatos<Licencia>("/licencia");
  const [texto, setTexto] = useState("");
  const [correo, setCorreo] = useState(usuario?.email ?? "");
  useEffect(() => {
    if (datos && window.location.hash === "#plan") {
      document.getElementById("plan")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [datos]);
  if (!datos) return null;
  const admin = puede(usuario?.rol, "administrar_usuarios");
  return (
    <div id="plan">
    <Tarjeta titulo="Plan">
      <div className="pila">
        <div style={{ fontSize: 22, fontWeight: 600, textTransform: "capitalize" }}>
          {datos.plan}
          {datos.prueba && <span className="pill medio" style={{ marginLeft: 8, verticalAlign: "middle" }}>Prueba gratis</span>}
        </div>
        <div>{datos.max_equipos === null ? `${datos.equipos_registrados} equipos (ilimitados)` : `${datos.equipos_registrados} de ${datos.max_equipos} equipos`}</div>
        {datos.cliente && <div><span className="tenue">A nombre de </span>{datos.cliente}</div>}
        {datos.vence && <div><span className="tenue">Vence </span>{fecha(datos.vence)}</div>}
        {datos.aviso && <div className="aviso atencion">{datos.aviso}</div>}
        {datos.prueba && (
          <div className="aviso info">
            Estás probando Pro. Al vencer vuelve al plan gratis sin perder nada.{" "}
            <a href={`${SITIO}/pro`} target="_blank" rel="noreferrer">Obtener Pro</a> (se paga en Ko-fi, con PayPal o tarjeta).
          </div>
        )}
      </div>
      {admin && datos.plan === "gratis" && (
        <div className="prueba-pro">
          <h3 style={{ margin: "0 0 4px" }}>Prueba Pro gratis 14 días</h3>
          <p className="tenue" style={{ margin: "0 0 12px" }}>
            Equipos ilimitados, informes en PDF, OLT GPON, avisos al equipo y predicción de capacidad, con tu red. Sin tarjeta;
            al terminar vuelve al plan gratis sin perder datos.
          </p>
          <Formulario
            textoBoton="Empezar la prueba"
            onEnviar={async () => {
              await api("/licencia/prueba", { metodo: "POST", cuerpo: { email: correo.trim() } });
              recargar();
            }}
          >
            <Campo etiqueta="Tu correo" ayuda="Para avisarte antes de que termine. Una prueba por instalación.">
              <input type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} required autoComplete="email" />
            </Campo>
          </Formulario>
        </div>
      )}
      {admin && (
        <div style={{ marginTop: 16 }}>
          <Formulario
            textoBoton="Instalar licencia"
            onEnviar={async () => {
              await api("/licencia", { metodo: "PUT", cuerpo: { licencia: texto.trim() } });
              setTexto("");
              recargar();
            }}
          >
            <Campo etiqueta="Licencia" ayuda="Pega el texto de la licencia que recibiste al contratar un plan.">
              <textarea value={texto} onChange={(e) => setTexto(e.target.value)} required className="mono" />
            </Campo>
          </Formulario>
        </div>
      )}
    </Tarjeta>
    </div>
  );
}

function Sitios() {
  const { datos, recargar } = useDatos<Sitio[]>("/sitios");
  const [nombre, setNombre] = useState("");
  return (
    <Tarjeta titulo="Sitios">
      <p className="tenue" style={{ marginTop: 0 }}>Nodos, torres o data centers donde están los equipos.</p>
      {datos && datos.length > 0 && (
        <ul style={{ margin: "0 0 12px", paddingLeft: 18 }}>
          {datos.map((s) => <li key={s.id}>{s.nombre}</li>)}
        </ul>
      )}
      <Formulario
        textoBoton="Agregar sitio"
        onEnviar={async () => {
          await api("/sitios", { metodo: "POST", cuerpo: { nombre } });
          setNombre("");
          recargar();
        }}
      >
        <Campo etiqueta="Nombre"><input value={nombre} onChange={(e) => setNombre(e.target.value)} required placeholder="Nodo Norte" /></Campo>
      </Formulario>
    </Tarjeta>
  );
}
