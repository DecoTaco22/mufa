// Idioma de la app. El español es el original; en inglés, los textos se traducen
// al dibujarse con el diccionario de en.ts, así las pantallas no cambian.
//
// Se traduce el texto visible y los atributos que se leen (placeholder, title,
// aria-label, alt). Nunca lo que es dato de la red: nombres de equipos, IPs,
// configuraciones, la terminal. Para eso, un elemento con translate="no", o con la
// clase «mono», queda tal cual (igual que un campo de texto o un <pre>).
import { EN } from "./en";

export type Idioma = "es" | "en";

const CLAVE = "mufa.idioma";

function leerIdioma(): Idioma {
  try {
    const guardado = localStorage.getItem(CLAVE);
    if (guardado === "es" || guardado === "en") return guardado;
  } catch {
    // Sin almacenamiento (modo privado): se usa el del navegador.
  }
  return navigator.language.toLowerCase().startsWith("es") ? "es" : "en";
}

export const IDIOMA: Idioma = leerIdioma();
/** Para Intl y toLocaleString: fechas y números como en el idioma elegido. */
export const LOCALE = IDIOMA === "en" ? "en" : "es";

export function cambiarIdioma(idioma: Idioma): void {
  try {
    localStorage.setItem(CLAVE, idioma);
  } catch {
    // Sin almacenamiento: dura hasta recargar.
  }
  window.location.reload();
}

// --- traducción ---------------------------------------------------------------

type Patron = { regex: RegExp; texto: string };

// Las claves con «{0}» son plantillas: «En {0} días» reconoce «En 12 días».
const PATRONES: Patron[] = Object.entries(EN)
  .filter(([clave]) => /\{\d+\}/.test(clave))
  .map(([clave, texto]) => {
    const partes = clave.split(/(\{\d+\})/).map((p) => (/^\{\d+\}$/.test(p) ? "(.+?)" : p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    return { regex: new RegExp(`^${partes.join("")}$`, "s"), texto };
  });

/** El texto en el idioma de la app (con sus espacios de los costados). */
export function t(texto: string): string {
  if (IDIOMA === "es") return texto;
  const limpio = texto.replace(/\s+/g, " ").trim();
  if (!limpio) return texto;
  let traducido = EN[limpio];
  if (traducido === undefined) {
    for (const p of PATRONES) {
      const m = p.regex.exec(limpio);
      if (m) {
        // La parte que cambia también puede ser un texto conocido («nunca»).
        traducido = p.texto.replace(/\{(\d+)\}/g, (_, n: string) => t(m[Number(n) + 1] ?? ""));
        break;
      }
    }
  }
  if (traducido === undefined) return texto;
  const antes = /^\s*/.exec(texto)?.[0] ?? "";
  const despues = /\s*$/.exec(texto)?.[0] ?? "";
  return antes + traducido + despues;
}

const ATRIBUTOS = ["placeholder", "title", "aria-label", "alt"];
const NO_TRADUCIR = '[translate="no"], .mono, .xterm, pre, code, textarea, script, style';

function excluido(elemento: Element | null): boolean {
  return !elemento || elemento.closest(NO_TRADUCIR) !== null;
}

function traducirTexto(nodo: Text): void {
  if (excluido(nodo.parentElement)) return;
  const valor = nodo.nodeValue ?? "";
  const nuevo = t(valor);
  if (nuevo !== valor) nodo.nodeValue = nuevo;
}

function traducirAtributos(elemento: Element): void {
  // Un campo «mono» (para escribir una IP) igual muestra su ayuda traducida.
  if (elemento.closest('[translate="no"]')) return;
  for (const atributo of ATRIBUTOS) {
    const valor = elemento.getAttribute(atributo);
    if (valor) {
      const nuevo = t(valor);
      if (nuevo !== valor) elemento.setAttribute(atributo, nuevo);
    }
  }
  // Los botones <input type="submit" value="..."> muestran su value.
  if (elemento instanceof HTMLInputElement && (elemento.type === "submit" || elemento.type === "button")) {
    const nuevo = t(elemento.value);
    if (nuevo !== elemento.value) elemento.value = nuevo;
  }
}

function traducirArbol(raiz: Node): void {
  if (raiz.nodeType === Node.TEXT_NODE) {
    traducirTexto(raiz as Text);
    return;
  }
  if (!(raiz instanceof Element)) return;
  traducirAtributos(raiz);
  const recorrido = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  for (let n = recorrido.nextNode(); n; n = recorrido.nextNode()) {
    if (n.nodeType === Node.TEXT_NODE) traducirTexto(n as Text);
    else traducirAtributos(n as Element);
  }
}

/** En inglés, traduce la página ahora y todo lo que React dibuje después. */
export function iniciarIdioma(): void {
  document.documentElement.lang = IDIOMA;
  if (IDIOMA === "es") return;
  traducirArbol(document.body);
  const titulo = document.querySelector("title");
  if (titulo) titulo.textContent = t(titulo.textContent ?? "");
  // Los cambios se traducen antes de que el navegador pinte: no se ve el español.
  new MutationObserver((cambios) => {
    for (const c of cambios) {
      if (c.type === "characterData") traducirTexto(c.target as Text);
      else if (c.type === "attributes") traducirAtributos(c.target as Element);
      else c.addedNodes.forEach(traducirArbol);
    }
  }).observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: [...ATRIBUTOS, "value"],
  });
}
