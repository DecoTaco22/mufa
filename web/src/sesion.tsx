import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";
import type { Yo } from "./tipos";

type Sesion = {
  usuario: Yo | null;
  cargando: boolean;
  recargar: () => Promise<void>;
  salir: () => Promise<void>;
};

const Contexto = createContext<Sesion | null>(null);

export function ProveedorDeSesion({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Yo | null>(null);
  const [cargando, setCargando] = useState(true);

  const recargar = useCallback(async () => {
    try {
      setUsuario(await api<Yo>("/auth/yo"));
    } catch {
      setUsuario(null);
    } finally {
      setCargando(false);
    }
  }, []);

  const salir = useCallback(async () => {
    try {
      await api("/auth/logout", { metodo: "POST" });
    } finally {
      setUsuario(null);
    }
  }, []);

  useEffect(() => {
    void recargar();
    const vencida = () => setUsuario(null);
    window.addEventListener("mufa:sesion-vencida", vencida);
    return () => window.removeEventListener("mufa:sesion-vencida", vencida);
  }, [recargar]);

  return <Contexto.Provider value={{ usuario, cargando, recargar, salir }}>{children}</Contexto.Provider>;
}

export function useSesion(): Sesion {
  const sesion = useContext(Contexto);
  if (sesion === null) throw new Error("useSesion fuera de ProveedorDeSesion");
  return sesion;
}
