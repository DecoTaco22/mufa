"""Interfaz gráfica de escritorio para mufa audit.

Capa fina sobre el mismo motor que usa la CLI (mufa.marcas, mufa.ssh,
mufa.engine, mufa.report): no duplica lógica de auditoría, solo la
presenta con clicks en vez de flags de terminal.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import paramiko

from mufa.engine import evaluar
from mufa.marcas import contexto_desde_archivo, leer_contexto
from mufa.models import Hallazgo
from mufa.report import generar_html
from mufa.ssh import KNOWN_HOSTS

COLUMNAS = ("severidad", "id", "titulo")


class VentanaMufa(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("mufa — auditor de RouterOS")
        self.geometry("820x560")
        self.minsize(700, 480)

        self._hallazgos: list[Hallazgo] = []
        self._etiqueta = ""
        # El hilo de trabajo no toca Tk: deja acá qué mostrar y la ventana lo
        # ejecuta desde su propio hilo (ver _revisar_resultados).
        self._resultados: queue.Queue[Callable[[], None]] = queue.Queue()

        self._construir_formulario()
        self._construir_resultados()
        self._construir_barra_estado()
        self._revisar_resultados()

    # --- construcción de widgets ---------------------------------------

    def _construir_formulario(self) -> None:
        marco = ttk.Frame(self, padding=10)
        marco.pack(fill="x")

        self.modo = tk.StringVar(value="offline")
        ttk.Radiobutton(
            marco,
            text="Archivo .rsc (offline)",
            variable=self.modo,
            value="offline",
            command=self._actualizar_modo,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            marco,
            text="Conectar por SSH",
            variable=self.modo,
            value="ssh",
            command=self._actualizar_modo,
        ).grid(row=0, column=1, sticky="w")

        self.marco_offline = ttk.Frame(marco)
        self.marco_offline.grid(row=1, column=0, columnspan=3, sticky="we", pady=(6, 0))
        self.ruta_archivo = tk.StringVar()
        ttk.Entry(self.marco_offline, textvariable=self.ruta_archivo, width=60).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(self.marco_offline, text="Elegir…", command=self._elegir_archivo).pack(
            side="left", padx=(6, 0)
        )

        self.marco_ssh = ttk.Frame(marco)
        self.marco_ssh.grid(row=1, column=0, columnspan=3, sticky="we", pady=(6, 0))
        self.host = tk.StringVar()
        self.usuario = tk.StringVar()
        self.password = tk.StringVar()
        self.puerto = tk.StringVar(value="22")

        campos = (
            ("Host/IP", self.host, False, 0),
            ("Usuario", self.usuario, False, 2),
            ("Contraseña", self.password, True, 4),
            ("Puerto", self.puerto, False, 6),
        )
        for etiqueta, variable, es_password, columna in campos:
            ttk.Label(self.marco_ssh, text=etiqueta).grid(row=0, column=columna, sticky="w")
            ancho = 6 if etiqueta == "Puerto" else 16
            ttk.Entry(
                self.marco_ssh,
                textvariable=variable,
                width=ancho,
                show="•" if es_password else "",
            ).grid(row=0, column=columna + 1, sticky="w", padx=(2, 10))

        self.marco_ssh.grid_remove()

        self.boton_auditar = ttk.Button(marco, text="Auditar", command=self._auditar)
        self.boton_auditar.grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.boton_guardar = ttk.Button(
            marco, text="Guardar informe HTML…", command=self._guardar_html, state="disabled"
        )
        self.boton_guardar.grid(row=2, column=1, sticky="w", pady=(10, 0))

    def _construir_resultados(self) -> None:
        marco = ttk.Frame(self, padding=(10, 0, 10, 10))
        marco.pack(fill="both", expand=True)

        self.tabla = ttk.Treeview(
            marco, columns=COLUMNAS, show="headings", height=8, selectmode="browse"
        )
        columnas = (
            ("severidad", "Severidad", 90),
            ("id", "ID", 120),
            ("titulo", "Título", 400),
        )
        for columna, titulo, ancho in columnas:
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor="w")
        self.tabla.pack(fill="both", expand=True)
        self.tabla.bind("<<TreeviewSelect>>", self._mostrar_detalle)

        self.detalle = tk.Text(marco, height=10, wrap="word", state="disabled")
        self.detalle.pack(fill="both", expand=False, pady=(8, 0))

    def _construir_barra_estado(self) -> None:
        self.estado = tk.StringVar(value="Listo.")
        ttk.Label(self, textvariable=self.estado, anchor="w", padding=(10, 4)).pack(fill="x")

    # --- interacción -----------------------------------------------------

    def _actualizar_modo(self) -> None:
        if self.modo.get() == "offline":
            self.marco_ssh.grid_remove()
            self.marco_offline.grid()
        else:
            self.marco_offline.grid_remove()
            self.marco_ssh.grid()

    def _elegir_archivo(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Elegir export .rsc",
            filetypes=[("Export RouterOS", "*.rsc"), ("Todos", "*.*")],
        )
        if ruta:
            self.ruta_archivo.set(ruta)

    def _auditar(self) -> None:
        # Los valores de los widgets se leen acá, en el hilo de Tk: tkinter no
        # es seguro entre hilos y el hilo de trabajo solo recibe datos planos.
        if self.modo.get() == "offline":
            ruta = self.ruta_archivo.get()
            if not ruta:
                messagebox.showwarning("Falta el archivo", "Elegí un archivo .rsc primero.")
                return
            trabajo = threading.Thread(
                target=self._ejecutar_offline, args=(Path(ruta),), daemon=True
            )
        else:
            host, usuario = self.host.get(), self.usuario.get()
            if not host or not usuario:
                messagebox.showwarning("Faltan datos", "Host y usuario son obligatorios.")
                return
            try:
                puerto = int(self.puerto.get() or "22")
            except ValueError:
                messagebox.showwarning("Puerto inválido", "El puerto tiene que ser un número.")
                return
            trabajo = threading.Thread(
                target=self._ejecutar_ssh,
                args=(host, usuario, self.password.get() or None, puerto),
                daemon=True,
            )

        self.estado.set("Auditando…")
        self.boton_auditar.configure(state="disabled")
        self.boton_guardar.configure(state="disabled")
        trabajo.start()

    def _revisar_resultados(self) -> None:
        while not self._resultados.empty():
            self._resultados.get_nowait()()
        self.after(100, self._revisar_resultados)

    def _ejecutar_offline(self, ruta: Path) -> None:
        try:
            hallazgos = evaluar(contexto_desde_archivo(ruta))
        except Exception as error:  # noqa: BLE001 — último borde antes de mostrarlo en la GUI
            mensaje = str(error)
            self._resultados.put(lambda: self._mostrar_error(mensaje))
            return
        self._resultados.put(lambda: self._mostrar_hallazgos(hallazgos, str(ruta)))

    def _ejecutar_ssh(self, host: str, usuario: str, password: str | None, puerto: int) -> None:
        try:
            hallazgos = evaluar(leer_contexto(host, usuario, password=password, port=puerto))
        except paramiko.BadHostKeyException:
            mensaje = (
                f"La clave SSH de {host} no coincide con la guardada en {KNOWN_HOSTS}.\n\n"
                "Puede ser un equipo haciéndose pasar por el router. Si el router se "
                "reinstaló, borrá su línea de ese archivo y volvé a intentar."
            )
            self._resultados.put(lambda: self._mostrar_error(mensaje))
            return
        except Exception as error:  # noqa: BLE001 — último borde antes de mostrarlo en la GUI
            mensaje = str(error)
            self._resultados.put(lambda: self._mostrar_error(mensaje))
            return
        self._resultados.put(lambda: self._mostrar_hallazgos(hallazgos, host))

    def _mostrar_error(self, mensaje: str) -> None:
        self.estado.set("Error.")
        self.boton_auditar.configure(state="normal")
        messagebox.showerror("No se pudo auditar", mensaje)

    def _mostrar_hallazgos(self, hallazgos: list[Hallazgo], etiqueta: str) -> None:
        self._hallazgos = hallazgos
        self._etiqueta = etiqueta
        self.boton_auditar.configure(state="normal")

        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        for hallazgo in hallazgos:
            self.tabla.insert(
                "",
                "end",
                iid=hallazgo.id,
                values=(hallazgo.severidad.value, hallazgo.id, hallazgo.titulo),
            )

        self.boton_guardar.configure(state="normal" if hallazgos else "disabled")
        if hallazgos:
            self.estado.set(f"{len(hallazgos)} hallazgo(s) en {etiqueta}.")
        else:
            self.estado.set(f"Sin hallazgos en {etiqueta}.")

    def _mostrar_detalle(self, _evento: tk.Event[tk.Misc]) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        hallazgo = next((h for h in self._hallazgos if h.id == seleccion[0]), None)
        if hallazgo is None:
            return

        texto = (
            f"Qué pasa: {hallazgo.evidencia}\n\n"
            f"Qué puede provocar: {hallazgo.impacto}\n\n"
            "Cómo se arregla:\n" + "\n".join(hallazgo.remediacion)
        )
        self.detalle.configure(state="normal")
        self.detalle.delete("1.0", "end")
        self.detalle.insert("1.0", texto)
        self.detalle.configure(state="disabled")

    def _guardar_html(self) -> None:
        ruta = filedialog.asksaveasfilename(
            title="Guardar informe",
            defaultextension=".html",
            filetypes=[("HTML", "*.html")],
        )
        if not ruta:
            return
        contenido = generar_html(self._hallazgos, host=self._etiqueta)
        Path(ruta).write_text(contenido, encoding="utf-8")
        self.estado.set(f"Informe guardado en {ruta}")


def main() -> None:
    VentanaMufa().mainloop()


if __name__ == "__main__":
    main()
