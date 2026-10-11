"""Genera empaquetado/mufa.ico a partir del dibujo de web/public/favicon.svg.

uv run --no-project --with pillow python empaquetado/generar_icono.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

TAMANO = 256
ESCALA = TAMANO / 32
# Mismo trazo que el favicon: una "M" que sube y baja como una señal.
PUNTOS = [(8, 22), (8, 12), (12, 18), (16, 12), (20, 18), (24, 12), (24, 22)]

imagen = Image.new("RGBA", (TAMANO, TAMANO), (0, 0, 0, 0))
dibujo = ImageDraw.Draw(imagen)
dibujo.rounded_rectangle((0, 0, TAMANO - 1, TAMANO - 1), radius=int(8 * ESCALA), fill="#0A84FF")
ancho = round(2.4 * ESCALA)
puntos = [(x * ESCALA, y * ESCALA) for x, y in PUNTOS]
dibujo.line(puntos, fill="white", width=ancho, joint="curve")
for x, y in (puntos[0], puntos[-1]):
    dibujo.ellipse((x - ancho / 2, y - ancho / 2, x + ancho / 2, y + ancho / 2), fill="white")

destino = Path(__file__).parent / "mufa.ico"
imagen.save(
    destino, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
)
imagen.save(destino.with_suffix(".png"))
print(destino)
