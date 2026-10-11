import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { Marco } from "./componentes/Marco";
import { Cargando } from "./componentes/ui";
import "./estilos.css";
import { Ajustes } from "./paginas/Ajustes";
import { Alertas } from "./paginas/Alertas";
import { EntradaOBienvenida } from "./paginas/Bienvenida";
import { DosPasos } from "./paginas/DosPasos";
import { EquipoDetalle } from "./paginas/EquipoDetalle";
import { Equipos } from "./paginas/Equipos";
import { Fibra } from "./paginas/Fibra";
import { Hallazgos } from "./paginas/Hallazgos";
import { Herramientas } from "./paginas/Herramientas";
import { Terminal } from "./paginas/Terminal";
import { Ipam } from "./paginas/Ipam";
import { Panel } from "./paginas/Panel";
import { Planes } from "./paginas/Planes";
import { PaginaPro } from "./paginas/Pro";
import { Respaldos } from "./paginas/Respaldos";
import { Registro } from "./paginas/Registro";
import { Usuarios } from "./paginas/Usuarios";
import { Vlans } from "./paginas/Vlans";
import { ProveedorDeSesion, useSesion } from "./sesion";
import { aplicarTema, temaGuardado } from "./tema";

aplicarTema(temaGuardado());

function Rutas() {
  const { usuario, cargando } = useSesion();
  if (cargando) return <Cargando />;
  if (!usuario) return <EntradaOBienvenida />;
  // Los roles con poder sobre la red no usan la app sin el segundo paso.
  if (usuario.dos_pasos_requerido) return <DosPasos obligatorio />;

  return (
    <Routes>
      <Route element={<Marco />}>
        <Route index element={<Panel />} />
        <Route path="equipos" element={<Equipos />} />
        <Route path="equipos/:id" element={<EquipoDetalle />} />
        <Route path="hallazgos" element={<Hallazgos />} />
        <Route path="ipam" element={<Ipam />} />
        <Route path="vlans" element={<Vlans />} />
        <Route path="fibra" element={<Fibra />} />
        <Route path="respaldos" element={<Respaldos />} />
        <Route path="herramientas" element={<Herramientas />} />
        <Route path="terminal" element={<Terminal />} />
        <Route path="planes" element={<Planes />} />
        <Route path="pro/:modulo" element={<PaginaPro />} />
        <Route path="alertas" element={<Alertas />} />
        <Route path="usuarios" element={<Usuarios />} />
        <Route path="registro" element={<Registro />} />
        <Route path="ajustes" element={<Ajustes />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <BrowserRouter>
      <ProveedorDeSesion>
        <Rutas />
      </ProveedorDeSesion>
    </BrowserRouter>
  </StrictMode>,
);
