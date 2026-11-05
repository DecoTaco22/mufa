// Modo demo (mufa.pages.dev/demo): la app real con datos de ejemplo, sin servidor.
// Las respuestas salen de datos-demo.json (scripts/datos_demo.py y capturar_demo.py).
// Nada se guarda: lo que cambiaría algo responde con una invitación a instalar mufa.

export const DEMO = import.meta.env.VITE_DEMO === "1";
export const DESCARGAR = "https://mufa.pages.dev/#descargar";

type Datos = Record<string, unknown> & { _capturado?: string };

let cargando: Promise<Datos> | null = null;

function datos(): Promise<Datos> {
  cargando ??= fetch(`${import.meta.env.BASE_URL}datos-demo.json`).then((r) => r.json() as Promise<Datos>);
  return cargando;
}

const FECHA_HORA = /^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?(Z|[+-]\d\d:\d\d)?$/;
const FECHA = /^\d{4}-\d\d-\d\d$/;

/** Corre todas las fechas como si los datos se hubieran tomado recién. */
function correr(valor: unknown, ms: number): unknown {
  if (typeof valor === "string") {
    if (FECHA_HORA.test(valor)) {
      const conZona = /[zZ]|[+-]\d\d:\d\d$/.test(valor) ? valor : `${valor}Z`;
      return new Date(new Date(conZona).getTime() + ms).toISOString();
    }
    if (FECHA.test(valor)) {
      const dias = Math.round(ms / 86400000);
      const d = new Date(`${valor}T12:00:00Z`);
      d.setUTCDate(d.getUTCDate() + dias);
      return d.toISOString().slice(0, 10);
    }
    return valor;
  }
  if (Array.isArray(valor)) return valor.map((v) => correr(v, ms));
  if (valor && typeof valor === "object") {
    return Object.fromEntries(Object.entries(valor).map(([k, v]) => [k, correr(v, ms)]));
  }
  return valor;
}

function claves(ruta: string): string[] {
  const [camino = ruta, consulta = ""] = ruta.split("?");
  const params = new URLSearchParams(consulta);
  params.delete("v"); // solo sirve para recargar
  const limpia = params.toString() ? `${camino}?${params}` : camino;
  const opciones = [limpia, camino];
  if (camino.startsWith("/pro/consumo/")) opciones.push(`${camino}?dias=7`);
  return opciones;
}

export class ErrorDemo extends Error {
  constructor(
    mensaje: string,
    readonly estado: number,
  ) {
    super(mensaje);
  }
}

export async function responderDemo(ruta: string, metodo: string): Promise<unknown> {
  if (metodo !== "GET") {
    if (ruta === "/auth/logout") {
      window.location.href = "https://mufa.pages.dev/";
      return undefined;
    }
    throw new ErrorDemo("Es una demo con datos de ejemplo: para hacerlo con tu red, instala mufa gratis.", 409);
  }
  const todo = await datos();
  // Horas completas: un horario de las 03:00 sigue siendo de las 03:00.
  const ms = todo._capturado ? Math.round((Date.now() - new Date(todo._capturado).getTime()) / 3600000) * 3600000 : 0;
  for (const clave of claves(ruta)) {
    if (clave in todo) return correr(todo[clave], ms);
  }
  throw new ErrorDemo("Esta parte no está en la demo. Instala mufa para verla con tu red.", 404);
}
