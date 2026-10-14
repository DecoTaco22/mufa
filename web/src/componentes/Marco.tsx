import { AvisoActualizacion } from "./Actualizacion";
import { Icono, type NombreIcono } from "./Icono";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { useSesion } from "../sesion";
import { aplicarTema, type Tema, temaGuardado } from "../tema";
import { NOMBRES_DE_ROL, type Permiso, puede } from "../util";
import { Segmentado } from "./ui";

type Enlace = { ruta: string; icono: NombreIcono; texto: string; permiso?: Permiso; pro?: boolean };

const SECCIONES: { titulo: string | null; enlaces: Enlace[] }[] = [
  { titulo: null, enlaces: [{ ruta: "/", icono: "panel", texto: "Panel" }] },
  {
    titulo: "Red",
    enlaces: [
      { ruta: "/equipos", icono: "equipo", texto: "Equipos" },
      { ruta: "/hallazgos", icono: "hallazgos", texto: "Hallazgos" },
      { ruta: "/respaldos", icono: "descarga", texto: "Respaldos" },
      { ruta: "/ipam", icono: "red", texto: "IPAM" },
      { ruta: "/vlans", icono: "capas", texto: "VLANs" },
      { ruta: "/fibra", icono: "onda", texto: "Fibra óptica" },
      { ruta: "/terminal", icono: "terminal", texto: "Terminal", permiso: "usar_credenciales" },
      { ruta: "/herramientas", icono: "herramienta", texto: "Herramientas", permiso: "diagnosticar" },
    ],
  },
  {
    titulo: "Operación",
    enlaces: [
      { ruta: "/alertas", icono: "campana", texto: "Alertas", permiso: "configurar_alertas" },
      { ruta: "/pro/avisos", icono: "usuarios", texto: "Avisos al equipo", pro: true },
      { ruta: "/pro/informes", icono: "documento", texto: "Informes PDF", pro: true },
      { ruta: "/pro/capacidad", icono: "grafica", texto: "Capacidad", pro: true },
      { ruta: "/pro/olt", icono: "enchufe", texto: "OLT GPON", pro: true },
    ],
  },
  {
    titulo: "Administración",
    enlaces: [
      { ruta: "/usuarios", icono: "usuarios", texto: "Usuarios", permiso: "administrar_usuarios" },
      { ruta: "/registro", icono: "reloj", texto: "Registro de eventos", permiso: "ver_registro" },
      { ruta: "/ajustes", icono: "engranaje", texto: "Ajustes" },
      { ruta: "/planes", icono: "estrella", texto: "Planes" },
    ],
  },
];

export function Marco() {
  const { usuario, salir } = useSesion();
  const [tema, setTema] = useState<Tema>(temaGuardado());
  const [abierta, setAbierta] = useState(false);
  const ubicacion = useLocation();

  useEffect(() => aplicarTema(tema), [tema]);
  useEffect(() => setAbierta(false), [ubicacion.pathname]);

  return (
    <div className="app">
      <div className="fondo-app" aria-hidden="true"><span /><span /></div>
      <div className="barra-movil">
        <button className="boton chico" onClick={() => setAbierta(!abierta)} aria-expanded={abierta}>
          Menú
        </button>
        <strong>mufa</strong>
      </div>

      <nav className={abierta ? "lateral abierta" : "lateral"} aria-label="Secciones">
        <div className="marca">
          <img src="/favicon.svg" alt="" />
          mufa
        </div>
        {SECCIONES.map((seccion) => {
          const visibles = seccion.enlaces.filter((e) => !e.permiso || puede(usuario?.rol, e.permiso));
          if (visibles.length === 0) return null;
          return (
            <div key={seccion.titulo ?? "inicio"}>
              {seccion.titulo && <div className="seccion-lateral">{seccion.titulo}</div>}
              {visibles.map((e) => (
                <NavLink key={e.ruta} to={e.ruta} end={e.ruta === "/"} className={({ isActive }) => (isActive ? "activo" : "")}>
                  <Icono nombre={e.icono} tamano={17} />
                  <span className="crece">{e.texto}</span>
                  {e.pro && <span className="insignia-pro">Pro</span>}
                </NavLink>
              ))}
            </div>
          );
        })}

        <div className="pie-lateral">
          <div>
            <div className="tenue" style={{ fontSize: 12, marginBottom: 6 }}>Apariencia</div>
            <Segmentado
              etiqueta="Apariencia"
              valor={tema}
              onCambio={setTema}
              opciones={[
                { valor: "oscuro", texto: "Oscuro" },
                { valor: "claro", texto: "Claro" },
                { valor: "automatico", texto: "Auto" },
              ]}
            />
          </div>
          {usuario && (
            <div className="entre" style={{ fontSize: 13 }}>
              <div>
                <div style={{ fontWeight: 600 }}>{usuario.nombre}</div>
                <div className="tenue" style={{ fontSize: 12 }}>{NOMBRES_DE_ROL[usuario.rol]}</div>
              </div>
              <button className="boton chico" onClick={() => void salir()}>Salir</button>
            </div>
          )}
        </div>
      </nav>

      {/* La clave reinicia la animación de entrada en cada cambio de página. */}
      <main className="contenido" key={ubicacion.pathname}>
        <AvisoActualizacion />
        <Outlet />
      </main>
    </div>
  );
}
