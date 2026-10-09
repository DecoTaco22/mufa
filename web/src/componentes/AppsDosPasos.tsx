// Apps con las que funciona la verificación en dos pasos de mufa.
// mufa usa TOTP estándar (RFC 6238): 6 dígitos que cambian cada 30 segundos.
// Cualquier app que lea un código QR «otpauth://» sirve; estas son las más usadas.

import type { Rol } from "../tipos";

/** Roles que no pueden entrar sin el segundo paso (igual que mufa/dos_pasos.py). */
export const ROLES_CON_DOS_PASOS: Rol[] = ["tecnico_n2", "ingeniero_n3", "senior", "admin"];

const APPS: { nombre: string; donde: string; nota?: string }[] = [
  { nombre: "Google Authenticator", donde: "iPhone · Android" },
  { nombre: "Microsoft Authenticator", donde: "iPhone · Android" },
  { nombre: "Contraseñas de Apple", donde: "iPhone · iPad · Mac", nota: "iOS 15 o posterior" },
  { nombre: "1Password", donde: "Todas" },
  { nombre: "Bitwarden Authenticator", donde: "iPhone · Android" },
  { nombre: "Proton Pass / Authenticator", donde: "Todas" },
  { nombre: "Authy", donde: "iPhone · Android" },
  { nombre: "2FAS", donde: "iPhone · Android", nota: "código abierto" },
  { nombre: "Aegis", donde: "Android", nota: "código abierto" },
];

export function AppsDosPasos(props: { compacto?: boolean }) {
  return (
    <div className={props.compacto ? "apps-2fa compacto" : "apps-2fa"}>
      <div className="apps-2fa-lista">
        {APPS.map((a) => (
          <span key={a.nombre} className="app-2fa" title={a.nota ? `${a.donde} · ${a.nota}` : a.donde}>
            <strong>{a.nombre}</strong>
            {!props.compacto && <span>{a.donde}{a.nota ? ` · ${a.nota}` : ""}</span>}
          </span>
        ))}
      </div>
      <span className="tenue" style={{ fontSize: 12 }}>
        O cualquier otra app de códigos de 6 dígitos (TOTP). Elige una con respaldo cifrado: si pierdes el teléfono, la recuperas.
      </span>
    </div>
  );
}
