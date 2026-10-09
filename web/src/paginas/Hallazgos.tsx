import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api";
import { TarjetaHallazgo } from "../componentes/TarjetaHallazgo";
import { Campo, Cargando, Encabezado, Formulario, MensajeError, Segmentado, Tarjeta, Vacio, ElegirArchivo } from "../componentes/ui";
import { useSesion } from "../sesion";
import type { Auditoria, HallazgoAbierto, Marca } from "../tipos";
import { puede, useDatos } from "../util";

const ORDEN: Record<string, number> = { crítico: 0, alto: 1, medio: 2, info: 3 };

export function Hallazgos() {
  const { usuario } = useSesion();
  const [parametros] = useSearchParams();
  const { datos, error, cargando } = useDatos<HallazgoAbierto[]>("/hallazgos");
  const [filtro, setFiltro] = useState<"todos" | "crítico" | "alto" | "medio">("todos");

  const enfocado = parametros.get("id");
  useEffect(() => {
    if (enfocado && datos) document.getElementById(`hallazgo-${enfocado}`)?.scrollIntoView({ behavior: "smooth" });
  }, [enfocado, datos]);

  const visibles = (datos ?? [])
    .filter((h) => filtro === "todos" || h.hallazgo.severidad === filtro)
    .sort((a, b) => (ORDEN[a.hallazgo.severidad] ?? 9) - (ORDEN[b.hallazgo.severidad] ?? 9));

  return (
    <>
      <Encabezado titulo="Hallazgos" subtitulo="De la última auditoría de cada equipo" />
      {puede(usuario?.rol, "auditar") && <AuditarArchivo />}
      <MensajeError mensaje={error} />
      <Segmentado
        etiqueta="Filtrar por severidad"
        valor={filtro}
        onCambio={setFiltro}
        opciones={[
          { valor: "todos", texto: "Todos" },
          { valor: "crítico", texto: "Críticos" },
          { valor: "alto", texto: "Altos" },
          { valor: "medio", texto: "Medios" },
        ]}
      />
      {cargando && !datos ? (
        <Cargando />
      ) : visibles.length === 0 ? (
        <Tarjeta><Vacio titulo="Sin hallazgos abiertos">Los equipos con usuario SSH se auditan solos una vez al día.</Vacio></Tarjeta>
      ) : (
        visibles.map((h) => <TarjetaHallazgo key={h.hallazgo.id} hallazgo={h.hallazgo} equipo={h.equipo} />)
      )}
    </>
  );
}

function AuditarArchivo() {
  const { datos: marcas } = useDatos<Marca[]>("/marcas");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [marca, setMarca] = useState("mikrotik");
  const [resultado, setResultado] = useState<Auditoria | null>(null);

  return (
    <Tarjeta titulo="Auditar un archivo">
      <p className="tenue" style={{ marginTop: 0 }}>
        Sube un export de configuración (MikroTik: <code>/export</code>; Cisco: <code>show running-config</code>) y mira qué encuentra mufa sin conectarse al equipo.
      </p>
      <Formulario
        textoBoton="Auditar"
        onEnviar={async () => {
          if (!archivo) throw new Error("Elige un archivo.");
          const formulario = new FormData();
          formulario.append("archivo", archivo);
          formulario.append("marca", marca);
          setResultado(await api<Auditoria>("/auditorias/archivo", { metodo: "POST", formulario }));
        }}
      >
        <div className="formulario">
          <Campo etiqueta="Archivo">
            <ElegirArchivo aceptar=".rsc,.txt,.cfg,.conf" archivo={archivo} onElegir={setArchivo} ayuda=".rsc, .txt o .cfg" />
          </Campo>
          <Campo etiqueta="Marca">
            <select value={marca} onChange={(e) => setMarca(e.target.value)}>
              {marcas?.filter((m) => m.con_adaptador).map((m) => <option key={m.marca} value={m.marca}>{m.nombre}</option>)}
            </select>
          </Campo>
        </div>
      </Formulario>
      {resultado && (
        <div className="pila" style={{ marginTop: 14 }}>
          <div className={resultado.hallazgos.length ? "aviso atencion" : "aviso ok"}>
            {resultado.hallazgos.length ? `${resultado.hallazgos.length} hallazgo(s) en ${resultado.etiqueta}` : `Sin hallazgos en ${resultado.etiqueta}`}
          </div>
          {resultado.hallazgos.map((h) => <TarjetaHallazgo key={h.id} hallazgo={h} />)}
        </div>
      )}
    </Tarjeta>
  );
}
