import { useRef, useState } from "react";
import { api, textoDeError } from "../api";
import type { Acceso, Equipo, Marca, ResultadoPruebaSnmp, Sitio } from "../tipos";
import { useDatos } from "../util";
import { Campo, Formulario, Modal, Segmentado } from "./ui";

type VersionSnmp = "ninguno" | "3" | "2c";

export const NOMBRES_DE_ACCESO: Record<Acceso, string> = { ssh: "SSH", api: "API", "api-ssl": "API-SSL" };
const PUERTO_POR_ACCESO: Record<Acceso, number> = { ssh: 22, api: 8728, "api-ssl": 8729 };
// Puertos de MikroTik que no son SSH: un error común al cargar el equipo.
const PUERTOS_QUE_NO_SON_SSH: Record<number, string> = { 8728: "la API", 8729: "la API-SSL", 8291: "Winbox" };

/** Dónde está cada dato de SNMPv3 en el equipo, para no tener que adivinar. */
function GuiaSnmp({ marca }: { marca: string }) {
  if (marca === "mikrotik")
    return (
      <div className="aviso info" style={{ fontSize: 13 }}>
        <strong>En MikroTik</strong> (IP → SNMP → Communities, abre tu comunidad):
        <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
          <li><strong>Usuario</strong> = el <em>Name</em> de la comunidad.</li>
          <li><em>Security</em> tiene que ser <strong>private</strong>.</li>
          <li><em>Authentication Protocol</em> SHA1 → <strong>SHA-1</strong>; <em>Encryption Protocol</em> AES → <strong>AES-128</strong>.</li>
          <li>En <em>Addresses</em> tiene que estar la IP de mufa (te la dice <strong>Probar conexión</strong>).</li>
        </ul>
      </div>
    );
  if (marca === "cisco")
    return (
      <div className="aviso info" style={{ fontSize: 13 }}>
        <strong>En Cisco IOS</strong>, un usuario de solo lectura se ve así:
        <pre className="mono" style={{ margin: "6px 0 0", whiteSpace: "pre-wrap" }}>
          {"snmp-server group MUFA v3 priv\nsnmp-server user mufa MUFA v3 auth sha <clave> priv aes 128 <clave>"}
        </pre>
      </div>
    );
  return (
    <div className="aviso info" style={{ fontSize: 13 }}>
      Copia del equipo el usuario SNMPv3, sus dos claves y los protocolos. El equipo tiene que permitir consultas desde la IP de mufa.
    </div>
  );
}

/** Alta o edición de un equipo. Las contraseñas nunca vuelven del servidor: en edición, vacío = no cambiar. */
export function FormularioEquipo(props: { equipo?: Equipo; onListo: (equipo: Equipo) => void; onCerrar: () => void }) {
  const editando = props.equipo !== undefined;
  const e = props.equipo;
  const { datos: marcas } = useDatos<Marca[]>("/marcas");
  const { datos: sitios } = useDatos<Sitio[]>("/sitios");

  const [nombre, setNombre] = useState(e?.nombre ?? "");
  const [marca, setMarca] = useState(e?.marca ?? "mikrotik");
  const [modelo, setModelo] = useState(e?.modelo ?? "");
  const [ip, setIp] = useState(e?.ip_gestion ?? "");
  const [sitio, setSitio] = useState<string>(e?.sitio_id?.toString() ?? "");
  const [serie, setSerie] = useState(e?.numero_serie ?? "");
  const [acceso, setAcceso] = useState<Acceso>(e?.acceso ?? "ssh");
  const [usuarioSsh, setUsuarioSsh] = useState(e?.usuario_ssh ?? "");
  const [passwordSsh, setPasswordSsh] = useState("");
  const [puertoSsh, setPuertoSsh] = useState(String(e?.puerto_ssh ?? 22));

  const snmpGuardado = e?.snmp ?? null;
  const [version, setVersion] = useState<VersionSnmp>(
    e ? ((snmpGuardado?.version as VersionSnmp | undefined) ?? "ninguno") : "3",
  );
  const [snmpUsuario, setSnmpUsuario] = useState(snmpGuardado?.usuario ?? "");
  const [auth, setAuth] = useState(snmpGuardado?.protocolo_auth ?? (marca === "mikrotik" ? "sha" : "sha256"));
  const [claveAuth, setClaveAuth] = useState("");
  const [priv, setPriv] = useState(snmpGuardado?.protocolo_priv ?? "aes");
  const [clavePriv, setClavePriv] = useState("");
  const [mismaClave, setMismaClave] = useState(!editando);
  const [comunidad, setComunidad] = useState("");
  const [puertoSnmp, setPuertoSnmp] = useState(String(snmpGuardado?.puerto ?? 161));
  const [prueba, setPrueba] = useState<ResultadoPruebaSnmp | { ok: false; mensaje: string; ip_origen?: undefined } | null>(null);
  const [probando, setProbando] = useState(false);
  const [completados, setCompletados] = useState<string[]>([]);
  // Lo último que completó la prueba SNMP: eso se puede reemplazar, lo que escribió la persona no.
  const autollenado = useRef({ nombre: "", modelo: "", serie: "" });

  const marcaElegida = marcas?.find((m) => m.marca === marca);
  const esMikrotik = marca === "mikrotik";
  // En edición, las claves guardadas se conservan si los campos quedan vacíos.
  const hayClavesGuardadas = editando && snmpGuardado?.version === version;
  const puertoNoEsSsh = acceso === "ssh" ? PUERTOS_QUE_NO_SON_SSH[Number(puertoSsh)] : undefined;

  function cambiarMarca(nueva: string) {
    setMarca(nueva);
    if (nueva !== "mikrotik") setAcceso("ssh");
    if (!editando) setAuth(nueva === "mikrotik" ? "sha" : "sha256");
  }

  function cambiarAcceso(nuevo: Acceso) {
    // Si el puerto era el de fábrica del acceso anterior, pasa al del nuevo.
    if (Object.values(PUERTO_POR_ACCESO).includes(Number(puertoSsh))) setPuertoSsh(String(PUERTO_POR_ACCESO[nuevo]));
    setAcceso(nuevo);
  }

  function snmp() {
    if (version === "ninguno") return null;
    if (version === "2c") return { version, puerto: Number(puertoSnmp), comunidad: comunidad || null };
    return {
      version,
      puerto: Number(puertoSnmp),
      usuario: snmpUsuario.trim(),
      clave_auth: claveAuth || null,
      clave_priv: (mismaClave ? claveAuth : clavePriv) || null,
      protocolo_auth: auth,
      protocolo_priv: priv,
    };
  }

  /** Completa nombre, marca, modelo y serie con lo que el equipo dice de sí mismo. */
  function completarCon(resultado: ResultadoPruebaSnmp) {
    const campos: [keyof typeof autollenado.current, string, string, (valor: string) => void, string][] = [
      ["nombre", nombre, resultado.sys_nombre, setNombre, "nombre"],
      ["modelo", modelo, resultado.modelo, setModelo, "modelo"],
      ["serie", serie, resultado.serie, setSerie, "número de serie"],
    ];
    const hechos: string[] = [];
    for (const [clave, actual, nuevo, poner, texto] of campos) {
      const valor = nuevo.trim();
      if (!valor || valor === actual) continue;
      if (actual.trim() && actual !== autollenado.current[clave]) continue;
      poner(valor);
      autollenado.current[clave] = valor;
      hechos.push(texto);
    }
    const detectada = resultado.marca_detectada;
    if (!editando && detectada && detectada !== marca && marcas?.some((m) => m.marca === detectada)) {
      cambiarMarca(detectada);
      hechos.push("marca");
    }
    setCompletados(hechos);
  }

  async function probar() {
    setProbando(true);
    setPrueba(null);
    setCompletados([]);
    try {
      const resultado = await api<ResultadoPruebaSnmp>("/snmp/probar", {
        metodo: "POST",
        cuerpo: { ip_gestion: ip, snmp: snmp(), equipo_id: e?.id ?? null },
      });
      setPrueba(resultado);
      if (resultado.ok) completarCon(resultado);
    } catch (error) {
      setPrueba({ ok: false, mensaje: textoDeError(error) });
    } finally {
      setProbando(false);
    }
  }

  async function guardar() {
    const cuerpo: Record<string, unknown> = {
      nombre,
      modelo,
      ip_gestion: ip,
      numero_serie: serie,
      sitio_id: sitio ? Number(sitio) : null,
      acceso,
      usuario_ssh: usuarioSsh,
      puerto_ssh: Number(puertoSsh),
      snmp: snmp(),
    };
    if (passwordSsh) cuerpo.password_ssh = passwordSsh;
    const resultado = editando
      ? await api<Equipo>(`/equipos/${e!.id}`, { metodo: "PATCH", cuerpo })
      : await api<Equipo>("/equipos", { metodo: "POST", cuerpo: { ...cuerpo, marca } });
    props.onListo(resultado);
  }

  const ayudaClaveGuardada = hayClavesGuardadas ? "Guardada. Vacío = no cambiar" : "Mínimo 8 caracteres";

  return (
    <Modal titulo={editando ? `Editar ${e!.nombre}` : "Agregar equipo"} onCerrar={props.onCerrar}>
      <Formulario textoBoton={editando ? "Guardar" : "Agregar"} onEnviar={guardar} onCancelar={props.onCerrar}>
        <div className="formulario">
          <Campo etiqueta="Nombre">
            <input value={nombre} onChange={(x) => setNombre(x.target.value)} required placeholder={version === "ninguno" ? "CCR Nodo Norte" : "Se completa al probar SNMP"} />
          </Campo>
          <Campo etiqueta="Marca" ayuda={marcaElegida && !marcaElegida.con_respaldo ? "Solo monitoreo por SNMP (todavía sin auditoría ni respaldos)." : marcaElegida && !marcaElegida.con_adaptador ? "Monitoreo por SNMP y respaldos diarios (la auditoría de seguridad llega después)." : undefined}>
            <select value={marca} onChange={(x) => cambiarMarca(x.target.value)} disabled={editando}>
              {(marcas ?? [{ marca: "mikrotik", nombre: "MikroTik", con_adaptador: true }]).map((m) => (
                <option key={m.marca} value={m.marca}>{m.nombre}</option>
              ))}
            </select>
          </Campo>
          <Campo etiqueta="IP de gestión">
            <input value={ip} onChange={(x) => setIp(x.target.value)} required placeholder="10.20.4.1" />
          </Campo>
          <Campo etiqueta="Modelo">
            <input value={modelo} onChange={(x) => setModelo(x.target.value)} placeholder="CCR2004" />
          </Campo>
          <Campo etiqueta="Sitio">
            <select value={sitio} onChange={(x) => setSitio(x.target.value)}>
              <option value="">Sin sitio</option>
              {sitios?.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Número de serie">
            <input value={serie} onChange={(x) => setSerie(x.target.value)} />
          </Campo>
        </div>

        <h3>Acceso para auditoría y respaldos (solo lectura)</h3>
        {esMikrotik && (
          <Segmentado
            etiqueta="Cómo se conecta mufa"
            valor={acceso}
            onCambio={cambiarAcceso}
            opciones={[
              { valor: "ssh", texto: "SSH" },
              { valor: "api", texto: "API (8728)" },
              { valor: "api-ssl", texto: "API-SSL (8729)" },
            ]}
          />
        )}
        {acceso === "api" && (
          <div className="aviso atencion">
            La API sin TLS manda la contraseña sin cifrar. Úsala solo por una red de gestión o VPN; si puedes, mejor API-SSL.
          </div>
        )}
        <div className="formulario">
          <Campo etiqueta="Usuario" ayuda={acceso !== "ssh" ? "Grupo con permisos read y api" : undefined}>
            <input value={usuarioSsh} onChange={(x) => setUsuarioSsh(x.target.value)} autoComplete="off" placeholder="mufa" />
          </Campo>
          <Campo etiqueta="Contraseña" ayuda={editando && e?.tiene_credenciales ? "Guardada. Vacío = no cambiar" : undefined}>
            <input type="password" value={passwordSsh} onChange={(x) => setPasswordSsh(x.target.value)} autoComplete="new-password" />
          </Campo>
          <Campo etiqueta="Puerto">
            <input type="number" min={1} max={65535} value={puertoSsh} onChange={(x) => setPuertoSsh(x.target.value)} />
          </Campo>
        </div>
        {puertoNoEsSsh && (
          <div className="aviso atencion">
            El puerto {puertoSsh} es el de {puertoNoEsSsh}, no el de SSH.{" "}
            {esMikrotik && Number(puertoSsh) !== 8291 && (
              <button type="button" className="boton chico" onClick={() => setAcceso(Number(puertoSsh) === 8729 ? "api-ssl" : "api")}>
                Conectar por {Number(puertoSsh) === 8729 ? "API-SSL" : "API"}
              </button>
            )}
          </div>
        )}
        <p className="tenue" style={{ margin: 0, fontSize: 12 }}>
          Usa un usuario de solo lectura. mufa solo consulta; la contraseña se guarda cifrada y nunca se muestra.
        </p>

        <h3>Monitoreo SNMP</h3>
        <Segmentado
          etiqueta="Versión SNMP"
          valor={version}
          onCambio={(v) => {
            setVersion(v);
            setPrueba(null);
          }}
          opciones={[
            { valor: "3", texto: "SNMPv3 (recomendado)" },
            { valor: "2c", texto: "v2c" },
            { valor: "ninguno", texto: "Sin SNMP" },
          ]}
        />
        {version === "3" && (
          <>
            <GuiaSnmp marca={marca} />
            <div className="formulario">
              <Campo etiqueta="Usuario SNMPv3" ayuda={esMikrotik ? "El Name de la comunidad" : undefined}>
                <input value={snmpUsuario} onChange={(x) => setSnmpUsuario(x.target.value)} required autoComplete="off" placeholder={esMikrotik ? "Nombre de la comunidad" : ""} />
              </Campo>
              <Campo etiqueta="Puerto">
                <input type="number" value={puertoSnmp} onChange={(x) => setPuertoSnmp(x.target.value)} />
              </Campo>
              <Campo etiqueta="Autenticación" ayuda={esMikrotik ? "Authentication Protocol" : undefined}>
                <select value={auth} onChange={(x) => setAuth(x.target.value)}>
                  <option value="sha">SHA-1</option>
                  <option value="sha256">SHA-256</option>
                </select>
              </Campo>
              <Campo etiqueta="Clave de autenticación" ayuda={ayudaClaveGuardada}>
                <input type="password" minLength={8} value={claveAuth} onChange={(x) => setClaveAuth(x.target.value)} required={!hayClavesGuardadas} autoComplete="new-password" />
              </Campo>
              <Campo etiqueta="Cifrado" ayuda={esMikrotik ? "Encryption Protocol (AES = AES-128)" : undefined}>
                <select value={priv} onChange={(x) => setPriv(x.target.value)}>
                  <option value="aes">AES-128</option>
                  <option value="aes256">AES-256</option>
                </select>
              </Campo>
              {!mismaClave && (
                <Campo etiqueta="Clave de cifrado" ayuda={ayudaClaveGuardada}>
                  <input type="password" minLength={8} value={clavePriv} onChange={(x) => setClavePriv(x.target.value)} required={!hayClavesGuardadas} autoComplete="new-password" />
                </Campo>
              )}
            </div>
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
              <input type="checkbox" checked={mismaClave} onChange={(x) => setMismaClave(x.target.checked)} />
              La clave de cifrado es la misma que la de autenticación
            </label>
          </>
        )}
        {version === "2c" && (
          <>
            <div className="aviso atencion">
              v2c manda la comunidad sin cifrar por la red. Úsalo solo si el equipo no soporta SNMPv3.
            </div>
            <div className="formulario">
              <Campo etiqueta="Comunidad" ayuda={hayClavesGuardadas ? "Guardada. Vacío = no cambiar" : undefined}>
                <input type="password" value={comunidad} onChange={(x) => setComunidad(x.target.value)} required={!hayClavesGuardadas} autoComplete="off" />
              </Campo>
              <Campo etiqueta="Puerto">
                <input type="number" value={puertoSnmp} onChange={(x) => setPuertoSnmp(x.target.value)} />
              </Campo>
            </div>
          </>
        )}
        {version !== "ninguno" && (
          <div className="pila">
            <div>
              <button type="button" className="boton" onClick={probar} disabled={probando || !ip}>
                {probando ? "Probando…" : "Probar conexión SNMP"}
              </button>
            </div>
            {prueba && (
              <div className={prueba.ok ? "aviso ok" : "aviso error"}>
                {prueba.ok && "sys_nombre" in prueba ? (
                  <>
                    Responde: <strong>{prueba.sys_nombre || "sin nombre"}</strong>
                    {prueba.sys_descripcion && ` · ${prueba.sys_descripcion}`}
                    {prueba.version && ` · versión ${prueba.version}`}
                    {completados.length > 0 && (
                      <div style={{ marginTop: 6, fontSize: 12 }}>
                        Completé {unir(completados)} con lo que informa el equipo. {completados.length > 1 ? "Revísalos" : "Revísalo"} arriba; el sitio y el acceso los eliges tú.
                      </div>
                    )}
                  </>
                ) : (
                  prueba.mensaje
                )}
                {prueba.ip_origen && (
                  <div style={{ marginTop: 6, fontSize: 12 }}>
                    mufa consulta desde la IP <strong className="mono">{prueba.ip_origen}</strong>.
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Formulario>
    </Modal>
  );
}

function unir(partes: string[]): string {
  return partes.length < 2 ? partes.join("") : `${partes.slice(0, -1).join(", ")} y ${partes.at(-1)}`;
}
