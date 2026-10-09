// Cliente de la API de mufa. La sesión va en una cookie HttpOnly: este código
// nunca ve el token. Todo cambio lleva la cabecera anti-CSRF.

export class ErrorApi extends Error {
  constructor(
    mensaje: string,
    readonly estado: number,
    readonly cabeceras: Headers,
  ) {
    super(mensaje);
  }
}

type Opciones = {
  metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  cuerpo?: unknown;
  formulario?: FormData;
};

function mensajeDeError(detalle: unknown, estado: number): string {
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle) && detalle.length > 0) {
    // Errores de validación de FastAPI: [{loc, msg}, ...]
    return detalle
      .map((e: { loc?: unknown[]; msg?: string }) => {
        const campo = e.loc?.filter((p) => p !== "body").join(".");
        const msg = (e.msg ?? "").replace(/^Value error, /, "");
        return campo ? `${campo}: ${msg}` : msg;
      })
      .join(" · ");
  }
  return `Error ${estado}`;
}

export async function api<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  const metodo = opciones.metodo ?? "GET";
  const cabeceras: Record<string, string> = { "X-Mufa-Cliente": "web" };
  if (metodo !== "GET") cabeceras["X-Mufa-Csrf"] = "1";
  let cuerpo: BodyInit | undefined;
  if (opciones.formulario) {
    cuerpo = opciones.formulario;
  } else if (opciones.cuerpo !== undefined) {
    cabeceras["Content-Type"] = "application/json";
    cuerpo = JSON.stringify(opciones.cuerpo);
  }

  const respuesta = await fetch(`/api/v1${ruta}`, {
    method: metodo,
    headers: cabeceras,
    body: cuerpo,
    credentials: "same-origin",
  });

  if (respuesta.status === 401 && !ruta.startsWith("/auth/login")) {
    window.dispatchEvent(new Event("mufa:sesion-vencida"));
  }
  if (!respuesta.ok) {
    let detalle: unknown;
    try {
      detalle = (await respuesta.json()).detail;
    } catch {
      detalle = undefined;
    }
    throw new ErrorApi(mensajeDeError(detalle, respuesta.status), respuesta.status, respuesta.headers);
  }
  if (respuesta.status === 204) return undefined as T;
  return (await respuesta.json()) as T;
}

/** El plan gratis llegó a un límite: se muestra como invitación a Pro, no como error. */
export function esLimiteDelPlan(error: unknown): boolean {
  return error instanceof ErrorApi && error.estado === 402;
}

export function textoDeError(error: unknown): string {
  if (error instanceof ErrorApi) return error.message;
  // fetch() rechaza con TypeError cuando no hay conexión con el servidor.
  if (error instanceof TypeError) return "No se pudo conectar con el servidor.";
  if (error instanceof Error) return error.message;
  return String(error);
}

/**
 * POST que devuelve texto a medida que el servidor lo escribe (ping, traceroute en vivo).
 * Llama a `alLlegar` con cada pedazo; `senal` permite cortarlo (Detener).
 */
export async function transmitir(
  ruta: string,
  cuerpo: unknown,
  alLlegar: (texto: string) => void,
  senal?: AbortSignal,
): Promise<void> {
  const respuesta = await fetch(`/api/v1${ruta}`, {
    method: "POST",
    headers: { "X-Mufa-Cliente": "web", "X-Mufa-Csrf": "1", "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
    credentials: "same-origin",
    signal: senal,
  });
  if (respuesta.status === 401) window.dispatchEvent(new Event("mufa:sesion-vencida"));
  if (!respuesta.ok || !respuesta.body) {
    let detalle: unknown;
    try {
      detalle = (await respuesta.json()).detail;
    } catch {
      detalle = undefined;
    }
    throw new ErrorApi(mensajeDeError(detalle, respuesta.status), respuesta.status, respuesta.headers);
  }
  const lector = respuesta.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await lector.read();
    if (done) return;
    alLlegar(value);
  }
}
