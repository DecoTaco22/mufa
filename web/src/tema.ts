// Apariencia: oscuro (por defecto), claro o automático (sigue al sistema).

export type Tema = "oscuro" | "claro" | "automatico";
const CLAVE = "mufa.tema";

export function temaGuardado(): Tema {
  try {
    const valor = localStorage.getItem(CLAVE);
    if (valor === "claro" || valor === "automatico" || valor === "oscuro") return valor;
  } catch {
    // Almacenamiento bloqueado: queda el tema por defecto.
  }
  return "oscuro";
}

const consulta = window.matchMedia("(prefers-color-scheme: light)");

export function aplicarTema(tema: Tema): void {
  const efectivo = tema === "automatico" ? (consulta.matches ? "claro" : "oscuro") : tema;
  document.documentElement.dataset.tema = efectivo;
  try {
    localStorage.setItem(CLAVE, tema);
  } catch {
    // Sin almacenamiento el tema dura lo que la pestaña.
  }
}

consulta.addEventListener("change", () => {
  if (temaGuardado() === "automatico") aplicarTema("automatico");
});
