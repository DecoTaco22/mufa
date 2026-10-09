import { Icono } from "./Icono";
import type { Rol } from "../tipos";
import { NOMBRES_DE_ROL, type Permiso, puede } from "../util";

// Para quién es cada rol, en una línea. Se muestra al elegirlo.
export const RESUMEN_DE_ROL: Record<Rol, string> = {
  lectura: "Solo mira: panel, equipos, IPAM, VLANs, hallazgos. Ideal para gerencia o auditores.",
  agente_n1: "Soporte y mesa de ayuda: mira todo y hace ping, traceroute, DNS y «¿Dónde está?», sin entrar a los equipos.",
  tecnico_n2: "Técnico de campo: además entra a los equipos del inventario por terminal, audita, respalda y lee configuraciones.",
  ingeniero_n3: "Ingeniería: además agrega, edita y borra equipos, redes, VLANs, sitios y el horario de respaldos.",
  senior: "Jefe de red: además ve el registro de eventos y decide qué sale de mufa (alertas y copia de respaldos).",
  admin: "Dueño de la instalación: además crea usuarios, restablece contraseñas y dos pasos, e instala la licencia.",
};

const FILAS: { texto: string; permiso: Permiso }[] = [
  { texto: "Ver panel, equipos, IPAM, VLANs, hallazgos y estado de respaldos", permiso: "ver" },
  { texto: "Ping, traceroute, DNS, puertos y «¿Dónde está?»", permiso: "diagnosticar" },
  { texto: "Terminal SSH, Telnet y serie; ver configuraciones respaldadas", permiso: "usar_credenciales" },
  { texto: "Auditar y respaldar un equipo, sondear por SNMP", permiso: "auditar" },
  { texto: "Agregar, editar y borrar equipos, redes, VLANs y sitios", permiso: "gestionar_equipos" },
  { texto: "Registro de eventos", permiso: "ver_registro" },
  { texto: "Alertas y copia de respaldos a un servidor", permiso: "configurar_alertas" },
  { texto: "Usuarios y licencia", permiso: "administrar_usuarios" },
];

const ROLES = Object.keys(NOMBRES_DE_ROL) as Rol[];
const CON_DOS_PASOS: Rol[] = ["tecnico_n2", "ingeniero_n3", "senior", "admin"];

export function CuadroDeRoles() {
  return (
    <div className="tabla-caja">
      <table className="cuadro-roles">
        <thead>
          <tr>
            <th />
            {ROLES.map((r) => <th key={r}>{NOMBRES_DE_ROL[r]}</th>)}
          </tr>
        </thead>
        <tbody>
          {FILAS.map((f) => (
            <tr key={f.permiso}>
              <td>{f.texto}</td>
              {ROLES.map((r) => (
                <td key={r} className="celda-rol">
                  {puede(r, f.permiso) ? <Icono nombre="check" className="si" titulo="Sí" /> : <span className="no" aria-label="No">—</span>}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <td>Verificación en dos pasos</td>
            {ROLES.map((r) => (
              <td key={r} className="celda-rol">{CON_DOS_PASOS.includes(r) ? <span className="pill info">Obligatoria</span> : <span className="no">Opcional</span>}</td>
            ))}
          </tr>
        </tbody>
      </table>
      <p className="tenue" style={{ fontSize: 12, margin: "10px 14px 14px" }}>
        Ningún rol puede hacer que mufa cambie algo en un equipo: la terminal solo manda lo que la persona escribe, y queda en el registro quién la abrió y cuándo.
      </p>
    </div>
  );
}
