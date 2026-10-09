// Íconos de línea propios (24×24, trazo 1.75), al estilo de SF Symbols.
// Heredan el color del texto: se tiñen con `color` en el CSS.

import type { CSSProperties } from "react";

const TRAZOS = {
  editar: "M4 20h4l10.5-10.5a2.1 2.1 0 0 0-4-4L4 16v4zM13.5 6.5l4 4",
  papelera: "M4 7h16M10 11v6M14 11v6M5.5 7l1 12a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2l1-12M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7",
  buscar: "M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15zM16 16l5 5",
  equipo: "M3 5.5A1.5 1.5 0 0 1 4.5 4h15A1.5 1.5 0 0 1 21 5.5v4A1.5 1.5 0 0 1 19.5 11h-15A1.5 1.5 0 0 1 3 9.5zM3 14.5A1.5 1.5 0 0 1 4.5 13h15a1.5 1.5 0 0 1 1.5 1.5v4a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5zM7 7.5h.01M7 16.5h.01",
  ubicacion: "M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21zM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  pregunta: "M9.2 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4.5M12 18h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
  lista: "M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01",
  llave: "M14.5 14a5.5 5.5 0 1 0-5.2-3.7L3 16.6V21h4.4l1-1v-2h2v-2h2l1.1-1.1c.3 0 .7.1 1 .1zM16.5 7.5h.01",
  terminal: "M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5zM8 9l3 3-3 3M13 15h3",
  intercambio: "M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7",
  cable: "M12 3v5M8 3v3M16 3v3M6 8h12v3a6 6 0 0 1-12 0zM12 17v4",
  recargar: "M20 11a8 8 0 0 0-14.7-4.3L3 9M3 4v5h5M4 13a8 8 0 0 0 14.7 4.3L21 15M21 20v-5h-5",
  alerta: "M12 9v4M12 17h.01M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  mas: "M12 5v14M5 12h14",
  check: "M5 12.5l4.5 4.5L19 7",
  cerrar: "M6 6l12 12M18 6 6 18",
  usuarios: "M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM21 20v-1.5a4 4 0 0 0-3-3.9M15.5 4.1a3.5 3.5 0 0 1 0 6.8",
  reloj: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  luna: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z",
  mano: "M8 13V5.5a1.5 1.5 0 0 1 3 0V11M11 10.5V4a1.5 1.5 0 0 1 3 0v6.5M14 10.5V5.5a1.5 1.5 0 0 1 3 0V13M17 11a1.5 1.5 0 0 1 3 0v3a7 7 0 0 1-7 7h-1a7 7 0 0 1-5.9-3.2L3.6 15a1.6 1.6 0 0 1 2.6-1.8L8 15",
  grafica: "M3 20h18M5 16l4-5 4 3 6-8",
  tendencia: "M3 7l6 6 4-4 8 8M21 11v6h-6",
  fuego: "M12 21a6 6 0 0 0 6-6c0-4-3-6-4-9-1 2-2 3-3.5 3.5C9 7 9 5 9 3c-3 2-5 6-5 10a8 8 0 0 0 8 8z",
  escudo: "M12 21s8-3.5 8-10V5l-8-2-8 2v6c0 6.5 8 10 8 10zM9 12l2 2 4-4",
  rayo: "M13 2 4 14h7l-1 8 9-12h-7z",
  enchufe: "M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5",
  tijera: "M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8.1 7.9 20 20M8.1 16.1 20 4",
  candado: "M5 11.5A1.5 1.5 0 0 1 6.5 10h11a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 19.5zM8 10V7a4 4 0 0 1 8 0v3",
  calendario: "M4 6.5A1.5 1.5 0 0 1 5.5 5h13A1.5 1.5 0 0 1 20 6.5v12a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5zM4 10h16M8 3v4M16 3v4",
  prediccion: "M12 3a7 7 0 0 1 7 7c0 2.6-1.4 4.8-3.5 6H8.5A7 7 0 0 1 12 3zM8 19h8M9.5 22h5M12 7v3l2 1",
  barras: "M5 20V11M10 20V5M15 20v-7M20 20V9",
  silencio: "M18 8a6 6 0 0 0-9.3-5M6 6.5V8c0 7-3 9-3 9h13M13.7 21a2 2 0 0 1-3.4 0M3 3l18 18",
  descarga: "M12 4v11M7 10l5 5 5-5M5 20h14",
  panel: "M4 5.5A1.5 1.5 0 0 1 5.5 4h4A1.5 1.5 0 0 1 11 5.5v5A1.5 1.5 0 0 1 9.5 12h-4A1.5 1.5 0 0 1 4 10.5zM13 5.5A1.5 1.5 0 0 1 14.5 4h4A1.5 1.5 0 0 1 20 5.5v2A1.5 1.5 0 0 1 18.5 9h-4A1.5 1.5 0 0 1 13 7.5zM13 12.5a1.5 1.5 0 0 1 1.5-1.5h4a1.5 1.5 0 0 1 1.5 1.5v6a1.5 1.5 0 0 1-1.5 1.5h-4a1.5 1.5 0 0 1-1.5-1.5zM4 15.5A1.5 1.5 0 0 1 5.5 14h4a1.5 1.5 0 0 1 1.5 1.5v3A1.5 1.5 0 0 1 9.5 20h-4A1.5 1.5 0 0 1 4 18.5z",
  hallazgos: "M12 21s8-3.5 8-10V5l-8-2-8 2v6c0 6.5 8 10 8 10zM12 8v4M12 15.5h.01",
  red: "M12 4v5M6 15v-2a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2M9.5 4h5v5h-5zM3.5 15h5v5h-5zM15.5 15h5v5h-5z",
  capas: "M12 3 3 8l9 5 9-5-9-5zM3 12.5l9 5 9-5M3 17l9 5 9-5",
  onda: "M2 12c2-4 4-4 6 0s4 4 6 0 4-4 6 0 2 2 2 2",
  herramienta: "M14.7 6.3a4 4 0 0 0 5 5L21 13l-8 8-3-3 1.3-1.3a4 4 0 0 1-5-5L3 8.5 8.5 3l3.2 3.3",
  campana: "M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9zM13.7 21a2 2 0 0 1-3.4 0",
  documento: "M14 3H7.5A1.5 1.5 0 0 0 6 4.5v15A1.5 1.5 0 0 0 7.5 21h9a1.5 1.5 0 0 0 1.5-1.5V7zM14 3v4h4M9 13h6M9 17h6",
  engranaje: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 14.4H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 3.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.9h.1a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  estrella: "M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z",
} as const;

export type NombreIcono = keyof typeof TRAZOS;

export function Icono(props: { nombre: NombreIcono; tamano?: number; className?: string; style?: CSSProperties; titulo?: string }) {
  const t = props.tamano ?? 16;
  return (
    <svg
      width={t}
      height={t}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={props.className ? `icono ${props.className}` : "icono"}
      style={props.style}
      role={props.titulo ? "img" : undefined}
      aria-label={props.titulo}
      aria-hidden={props.titulo ? undefined : true}
      focusable="false"
    >
      <path d={TRAZOS[props.nombre]} />
    </svg>
  );
}
