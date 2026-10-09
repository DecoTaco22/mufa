import { useCallback, useEffect, useState } from "react";
import { api, textoDeError } from "./api";
import type { Rol } from "./tipos";

// --- permisos: el mismo cuadro que src/mufa/permisos.py ------------------

export type Permiso =
  | "ver"
  | "diagnosticar"
  | "auditar"
  | "gestionar_equipos"
  | "usar_credenciales"
  | "administrar_usuarios"
  | "ver_registro"
  | "configurar_alertas";

const BASE: Permiso[] = ["ver"];
const AGENTE: Permiso[] = [...BASE, "diagnosticar"];
const TECNICO: Permiso[] = [...AGENTE, "auditar", "usar_credenciales"];
const INGENIERO: Permiso[] = [...TECNICO, "gestionar_equipos"];
const SENIOR: Permiso[] = [...INGENIERO, "ver_registro", "configurar_alertas"];

const PERMISOS: Record<Rol, Permiso[]> = {
  lectura: BASE,
  agente_n1: AGENTE,
  tecnico_n2: TECNICO,
  ingeniero_n3: INGENIERO,
  senior: SENIOR,
  admin: [...SENIOR, "administrar_usuarios"],
};

export function puede(rol: Rol | undefined, permiso: Permiso): boolean {
  return rol !== undefined && PERMISOS[rol].includes(permiso);
}

export const NOMBRES_DE_ROL: Record<Rol, string> = {
  lectura: "Lectura",
  agente_n1: "Agente N1",
  tecnico_n2: "Técnico N2",
  ingeniero_n3: "Ingeniero N3",
  senior: "Senior",
  admin: "Admin",
};

// --- datos ---------------------------------------------------------------

export function useDatos<T>(ruta: string | null) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(ruta !== null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (ruta === null) return;
    let vigente = true;
    setCargando(true);
    api<T>(ruta)
      .then((d) => {
        if (vigente) {
          setDatos(d);
          setError(null);
        }
      })
      .catch((e: unknown) => vigente && setError(textoDeError(e)))
      .finally(() => vigente && setCargando(false));
    return () => {
      vigente = false;
    };
  }, [ruta, version]);

  const recargar = useCallback(() => setVersion((v) => v + 1), []);
  return { datos, error, cargando, recargar };
}

// --- formato -------------------------------------------------------------

const FECHA = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" });

export function fecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  // El servidor guarda UTC; SQLite devuelve la fecha sin zona.
  const valor = /[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  return FECHA.format(new Date(valor));
}

export function hace(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  const valor = /[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  const segundos = Math.max(0, (Date.now() - new Date(valor).getTime()) / 1000);
  if (segundos < 60) return "hace un momento";
  if (segundos < 3600) return `hace ${Math.round(segundos / 60)} min`;
  if (segundos < 86400) return `hace ${Math.round(segundos / 3600)} h`;
  return `hace ${Math.round(segundos / 86400)} d`;
}

export function bps(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  const unidades = ["bps", "Kbps", "Mbps", "Gbps", "Tbps"];
  let v = valor;
  let i = 0;
  while (v >= 1000 && i < unidades.length - 1) {
    v /= 1000;
    i++;
  }
  return `${v.toLocaleString("es", { maximumFractionDigits: v < 10 ? 1 : 0 })} ${unidades[i]}`;
}

export function duracion(segundos: number | null | undefined): string {
  if (segundos === null || segundos === undefined) return "—";
  const d = Math.floor(segundos / 86400);
  const h = Math.floor((segundos % 86400) / 3600);
  const m = Math.floor((segundos % 3600) / 60);
  if (d > 0) return `${d} d ${h} h`;
  if (h > 0) return `${h} h ${m} min`;
  return `${m} min`;
}

export function claseSeveridad(severidad: string): string {
  return { crítico: "critico", alto: "alto", medio: "medio", info: "info" }[severidad] ?? "gris";
}

export function descargar(nombre: string, texto: string): void {
  const enlace = document.createElement("a");
  enlace.href = URL.createObjectURL(new Blob([texto], { type: "text/plain;charset=utf-8" }));
  enlace.download = nombre;
  enlace.click();
  URL.revokeObjectURL(enlace.href);
}
