#!/usr/bin/env python3
"""Graba el video de presentación recorriendo la demo de mufa (unos 70 segundos).

    uvx --with playwright python scripts/video_demo.py https://mufa.pages.dev/demo carpeta-salida

Usa el Edge instalado (sin descargar navegadores). Deja un .webm en la carpeta;
para MP4: ffmpeg -i video.webm -c:v libx264 -pix_fmt yuv420p -movflags +faststart mufa.mp4
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

DEMO = sys.argv[1].rstrip("/")
SALIDA = Path(sys.argv[2])

SUBTITULO = """
(texto) => {
  let c = document.getElementById('subtitulo-video');
  if (!c) {
    c = document.createElement('div');
    c.id = 'subtitulo-video';
    c.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:99999;' +
      'max-width:86%;padding:14px 26px;border-radius:16px;background:rgba(10,132,255,.94);color:#fff;' +
      'font:600 26px/1.3 "Segoe UI",system-ui,sans-serif;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.45);' +
      'transition:opacity .35s ease;';
    document.body.appendChild(c);
  }
  c.style.opacity = '0';
  setTimeout(() => { c.textContent = texto; c.style.opacity = texto ? '1' : '0'; }, 250);
}
"""

TARJETA = """
(lineas) => {
  // El sitio no deja usar style="..." en HTML (CSP): los estilos se ponen por código.
  const t = document.createElement('div');
  t.style.cssText = 'position:fixed;inset:0;z-index:100000;display:flex;flex-direction:column;gap:18px;' +
    'align-items:center;justify-content:center;background:linear-gradient(160deg,#0b1220,#13254d);color:#fff;' +
    'font-family:"Segoe UI",system-ui,sans-serif;opacity:0;transition:opacity .6s ease;text-align:center;';
  for (const [texto, estilo] of lineas) {
    const d = document.createElement('div');
    d.textContent = texto;
    d.style.cssText = estilo;
    t.appendChild(d);
  }
  document.body.appendChild(t);
  requestAnimationFrame(() => (t.style.opacity = '1'));
}
"""


def ir(page: Page, ruta: str) -> None:
    """Cambia de pantalla dentro de la app, sin recargar (como un clic en el menú)."""
    page.evaluate(SUBTITULO, "")
    page.wait_for_timeout(300)
    page.evaluate(
        "(r) => { history.pushState({}, '', r); window.dispatchEvent(new PopStateEvent('popstate')); }",
        f"/demo{ruta}",
    )
    page.wait_for_timeout(900)


def decir(page: Page, texto: str, segundos: float) -> None:
    page.evaluate(SUBTITULO, texto)
    page.wait_for_timeout(int(segundos * 1000))


def bajar(page: Page, pixeles: int, pasos: int = 12) -> None:
    for _ in range(pasos):
        page.mouse.wheel(0, pixeles / pasos)
        page.wait_for_timeout(60)


def clic(page: Page, texto: str) -> None:
    try:
        # Dentro de la pantalla (main), no en el menú lateral que repite nombres.
        page.locator("main").get_by_text(texto, exact=True).first.click(timeout=3000)
    except Exception as error:  # noqa: BLE001 - una pantalla que cambió no frena la grabación
        print(f"sin clic en {texto!r}: {error}")


with sync_playwright() as p:
    navegador = p.chromium.launch(channel="msedge", headless=True)
    contexto = navegador.new_context(
        viewport={"width": 1440, "height": 900},
        device_scale_factor=1,
        locale="es-GT",
        color_scheme="dark",
        record_video_dir=str(SALIDA),
        record_video_size={"width": 1440, "height": 900},
    )
    contexto.add_init_script("try { localStorage.setItem('mufa.idioma', 'es') } catch (e) {}")
    page = contexto.new_page()
    inicio = time.monotonic()
    page.goto(f"{DEMO}/", wait_until="networkidle")
    page.wait_for_timeout(1200)

    decir(page, "¿Sabes qué cambió anoche en el router de tu ISP?", 3.2)
    decir(page, "mufa: monitoreo, seguridad y respaldos de tu red, en un solo lugar.", 3.6)

    ir(page, "/equipos")
    decir(page, "Todos tus equipos por SNMP: MikroTik, Cisco, Huawei, Ubiquiti y más.", 4)

    ir(page, "/hallazgos")
    decir(page, "Audita la seguridad de cada equipo…", 2.8)
    bajar(page, 260)
    decir(page, "…y te dice qué arreglar, con los comandos exactos.", 3.4)

    ir(page, "/equipos/1")
    clic(page, "Respaldos")
    page.wait_for_timeout(700)
    decir(page, "Respaldo diario de la configuración, cifrado.", 2.8)
    clic(page, "Qué cambió")
    page.wait_for_timeout(600)
    decir(page, "Y ves exactamente qué línea cambió, y cuándo.", 3.6)
    page.keyboard.press("Escape")

    ir(page, "/mapa")
    page.wait_for_timeout(600)
    decir(page, "Mapa de la red armado solo, con LLDP y CDP.", 4)

    ir(page, "/pro/olt")
    decir(page, "OLT GPON: cada ONU, su señal y sus caídas.", 3.2)
    bajar(page, 380)
    decir(page, "Te avisa si es un corte de fibra… o si una señal baja día a día.", 3.8)

    ir(page, "/pro/consumo")
    decir(page, "Consumo de cada cliente con NetFlow, con su nombre del IPAM.", 3.6)
    clic(page, "Ferretería El Sol")
    page.wait_for_timeout(500)
    bajar(page, 420)
    decir(page, "Hora por hora: quién usa el ancho de banda.", 3.2)

    ir(page, "/pro/capacidad")
    decir(page, "Predicción: cuándo se va a saturar cada enlace.", 3.6)

    ir(page, "/pro/mantenimiento")
    decir(page, "Ventanas de mantenimiento: cero alertas falsas.", 3.2)

    page.goto(f"{DEMO}/estado/demo", wait_until="networkidle")
    page.wait_for_timeout(700)
    decir(page, "Y una página de estado para que tus clientes vean la falla antes de llamar.", 4.2)

    decir(page, "", 0.4)
    page.evaluate(
        TARJETA,
        [
            ["mufa", "font-size:96px;font-weight:800;letter-spacing:-2px"],
            ["Gratis hasta 10 equipos · Pro 14 días sin tarjeta", "font-size:36px;font-weight:600"],
            [
                "Solo lectura · En tu propio servidor · Español e inglés",
                "font-size:28px;color:#9ecbff",
            ],
            [
                "mufa.pages.dev",
                "margin-top:24px;padding:18px 44px;border-radius:20px;background:#0a84ff;font-size:46px;font-weight:700",
            ],
            [
                "Pruébalo en vivo: mufa.pages.dev/demo",
                "font-size:26px;color:#c7d2e5;margin-top:6px",
            ],
        ],
    )
    page.wait_for_timeout(5500)
    print(f"duración: {time.monotonic() - inicio:.0f} s")
    video = page.video
    contexto.close()
    navegador.close()
    if video:
        destino = SALIDA / "mufa-demo.webm"
        Path(video.path()).replace(destino)
        print(destino)
