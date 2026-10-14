"""mufa de escritorio: una aplicación con su propia ventana (Windows y macOS).

Arranca el servidor de mufa en 127.0.0.1 (nadie más de la red puede entrar)
y lo muestra en una ventana nativa con WebView2 en Windows o WebKit en macOS.
Mientras arranca, la ventana muestra una pantalla de carga animada. No hay
terminal: los mensajes van a <datos>/mufa-escritorio.log.

Para un equipo de trabajo, mufa se instala como servidor (Docker) y se usa
desde el navegador.

Variables útiles:
  MUFA_SIN_VENTANA=1   solo el servidor, sin ventana (pruebas automáticas).
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

HOST = "127.0.0.1"
PUERTOS_PREFERIDOS = (8080, 8081, 8082, 8090)
TITULO = "mufa"

# La pantalla de carga: el logo respira, una barra de luz recorre la línea y
# el texto cambia según lo que está pasando. Todo en línea (no hay servidor todavía).
PANTALLA_DE_CARGA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><style>
  :root { color-scheme: dark; }
  html, body { margin: 0; height: 100%; background: #0b0b0d; overflow: hidden;
    font: 15px -apple-system, BlinkMacSystemFont, "Segoe UI Variable", "Segoe UI", sans-serif; color: #f5f5f7;
    -webkit-user-select: none; user-select: none; cursor: default; }
  .luz { position: fixed; border-radius: 50%; filter: blur(90px); opacity: .5;
    animation: flotar 9s ease-in-out infinite alternate; }
  .luz.a { width: 420px; height: 420px; background: #0a84ff; left: 12%; top: 18%; }
  .luz.b { width: 360px; height: 360px; background: #5e5ce6; right: 10%; bottom: 12%; animation-delay: -4s; }
  @keyframes flotar { to { transform: translate(60px, -40px) scale(1.15); } }
  .centro { position: relative; height: 100%; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 22px;
    animation: entrar .9s cubic-bezier(.22,1,.36,1) both; transition: opacity .35s, transform .35s, filter .35s; }
  .centro.saliendo { opacity: 0; transform: scale(1.04); filter: blur(8px); }
  @keyframes entrar { from { opacity: 0; transform: scale(.94); filter: blur(10px); } }
  .logo { width: 88px; height: 88px; border-radius: 22px; background: #0a84ff;
    display: grid; place-items: center;
    box-shadow: 0 0 0 0 rgba(10,132,255,.55), 0 20px 50px rgba(10,132,255,.35);
    animation: latir 2.4s ease-in-out infinite; }
  @keyframes latir { 50% { box-shadow: 0 0 0 14px rgba(10,132,255,0), 0 20px 60px rgba(10,132,255,.5); transform: scale(1.03); } }
  .logo svg { width: 56px; height: 56px; }
  .logo path { stroke-dasharray: 60; stroke-dashoffset: 60; animation: trazo 1.4s .2s cubic-bezier(.22,1,.36,1) forwards; }
  @keyframes trazo { to { stroke-dashoffset: 0; } }
  .nombre { font-size: 28px; font-weight: 700; letter-spacing: -.02em; }
  .barra { width: 180px; height: 3px; border-radius: 3px; background: rgba(255,255,255,.1); overflow: hidden; }
  .barra::after { content: ""; display: block; width: 40%; height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, transparent, #2997ff, transparent);
    animation: recorrer 1.3s ease-in-out infinite; }
  @keyframes recorrer { from { transform: translateX(-100%); } to { transform: translateX(260%); } }
  #estado { color: #a1a1a6; font-size: 13px; min-height: 18px; transition: opacity .25s; }
  .error #estado { color: #ff6961; max-width: 460px; text-align: center; line-height: 1.5; }
  .error .barra { display: none; }
  @media (prefers-reduced-motion: reduce) { *, *::after { animation: none !important; } .logo path { stroke-dashoffset: 0; } }
</style></head><body>
  <div class="luz a"></div><div class="luz b"></div>
  <div class="centro" id="centro">
    <div class="logo"><svg viewBox="0 0 32 32"><path d="M8 22V12l4 6 4-6 4 6 4-6v10" fill="none" stroke="#fff"
      stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
    <div class="nombre">mufa</div>
    <div class="barra"></div>
    <div id="estado">Abriendo…</div>
  </div>
</body></html>"""


def _directorio_de_datos() -> Path:
    return Path(os.environ.get("MUFA_DIR_DATOS", str(Path.home() / ".mufa")))


def _sin_consola() -> None:
    """En la app con ventana no hay consola: stdout y stderr van a un archivo."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    datos = _directorio_de_datos()
    datos.mkdir(parents=True, exist_ok=True)
    registro = open(datos / "mufa-escritorio.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = registro
    sys.stderr = registro


def _puerto_libre() -> int:
    for puerto in PUERTOS_PREFERIDOS:
        with socket.socket() as prueba:
            try:
                prueba.bind((HOST, puerto))
                return puerto
            except OSError:
                continue
    with socket.socket() as prueba:
        prueba.bind((HOST, 0))
        return int(prueba.getsockname()[1])


def _esperar(url: str, segundos: float = 60) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(f"{url}/api/v1/salud", timeout=2):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class Servidor:
    """El servidor de mufa corriendo en un hilo de esta misma aplicación."""

    def __init__(self) -> None:
        self.url = ""
        self.token: str | None = None
        self.actualizador: Any = None
        self._uvicorn: Any = None
        self._hilo: threading.Thread | None = None

    def arrancar(self) -> None:
        import uvicorn

        from mufa.api import crear_app

        # Solo se le habla por 127.0.0.1: ningún otro nombre (DNS rebinding).
        os.environ.setdefault("MUFA_HOSTS_PERMITIDOS", f"{HOST},localhost")
        app = crear_app()
        puerto = _puerto_libre()
        self.url = f"http://{HOST}:{puerto}"
        self.token = app.state.mufa.token_inicial
        self.actualizador = app.state.mufa.actualizador
        self._uvicorn = uvicorn.Server(
            uvicorn.Config(app, host=HOST, port=puerto, server_header=False, log_level="warning")
        )
        self._hilo = threading.Thread(target=self._uvicorn.run, name="mufa-servidor", daemon=True)
        self._hilo.start()
        if not _esperar(self.url):
            raise RuntimeError("el servidor no respondió a tiempo")

    @property
    def destino(self) -> str:
        return f"{self.url}/?token={self.token}" if self.token else self.url

    def detener(self) -> None:
        if self._uvicorn is not None:
            self._uvicorn.should_exit = True
        if self._hilo is not None:
            self._hilo.join(10)


def _estado(ventana: Any, texto: str) -> None:
    ventana.evaluate_js(f"document.getElementById('estado').textContent = {texto!r}")


def _preparar(ventana: Any, servidor: Servidor) -> None:
    """Corre detrás de la pantalla de carga y, cuando el servidor está listo, abre la app."""
    try:
        _estado(ventana, "Preparando tus datos…")
        servidor.arrancar()
        if servidor.actualizador is not None:
            # Al instalar una versión nueva, mufa se cierra para que el instalador
            # pueda reemplazar sus archivos (y la vuelve a abrir al terminar).
            servidor.actualizador.al_cerrar = ventana.destroy
        _estado(ventana, "Listo")
        ventana.evaluate_js("document.getElementById('centro').classList.add('saliendo')")
        time.sleep(0.35)
        ventana.load_url(servidor.destino)
    except Exception as error:  # noqa: BLE001 - se muestra en la ventana: no hay consola
        print(f"mufa no pudo arrancar: {error!r}", file=sys.stderr)
        ventana.evaluate_js("document.body.classList.add('error')")
        _estado(
            ventana,
            f"mufa no pudo arrancar: {error}. "
            f"El detalle está en {_directorio_de_datos() / 'mufa-escritorio.log'}",
        )


def _sin_ventana() -> None:
    servidor = Servidor()
    servidor.arrancar()
    print(f"mufa está corriendo en {servidor.url}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        servidor.detener()


def main() -> None:
    _sin_consola()
    if os.environ.get("MUFA_SIN_VENTANA") == "1":
        _sin_ventana()
        return

    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    servidor = Servidor()
    ventana = webview.create_window(
        TITULO,
        html=PANTALLA_DE_CARGA,
        width=1320,
        height=860,
        min_size=(900, 600),
        background_color="#0B0B0D",
        text_select=True,
        zoomable=True,
    )
    datos = _directorio_de_datos()
    datos.mkdir(parents=True, exist_ok=True)
    try:
        # Sesión y preferencias (tema) se guardan entre aperturas, en los datos de mufa.
        webview.start(
            _preparar,
            (ventana, servidor),
            private_mode=False,
            storage_path=str(datos / "ventana"),
        )
    finally:
        servidor.detener()


if __name__ == "__main__":
    main()
