"""Renderiza la salida real de una prueba (texto) a una imagen tipo terminal.

No inventa contenido: pinta exactamente el texto del archivo de salida indicado.
Uso: python render_terminal.py <entrada.txt> <salida.png> <titulo>
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FUENTE = r"C:\Windows\Fonts\consola.ttf"
FONDO = (11, 18, 34)
TEXTO = (226, 232, 240)
TITULO = (147, 197, 253)
VERDE = (110, 231, 183)
ROJO = (253, 164, 175)
GRIS = (139, 154, 180)


def color_de(linea: str) -> tuple[int, int, int]:
    if "passed" in linea and "failed" not in linea:
        return VERDE
    if "FAILED" in linea or "failed" in linea or "Error" in linea:
        return ROJO
    if linea.startswith("===") or linea.startswith("---"):
        return GRIS
    return TEXTO


def main() -> None:
    entrada, salida, titulo = sys.argv[1], sys.argv[2], sys.argv[3]
    lineas = Path(entrada).read_text(encoding="utf-8").replace("\t", "    ").splitlines()
    fuente = ImageFont.truetype(FUENTE, 15)
    fuente_titulo = ImageFont.truetype(FUENTE, 19)

    ancho_caracter = fuente.getlength("M")
    max_linea = max([len(lineas[0]) if lineas else 0, len(titulo), 60])
    ancho = min(1700, int(ancho_caracter * (max_linea + 2)) + 40)
    columnas = max(60, int((ancho - 40) / ancho_caracter))

    envueltas: list[str] = []
    for linea in lineas:
        if len(linea) <= columnas:
            envueltas.append(linea)
            continue
        resto = linea
        while len(resto) > columnas:
            envueltas.append(resto[:columnas])
            resto = resto[columnas:]
        envueltas.append(resto)

    alto = 70 + len(envueltas) * 21 + 20
    imagen = Image.new("RGB", (ancho, alto), FONDO)
    dibujo = ImageDraw.Draw(imagen)
    dibujo.text((20, 16), titulo, font=fuente_titulo, fill=TITULO)
    dibujo.line((20, 50, ancho - 20, 50), fill=(42, 56, 84))
    y = 60
    for linea in envueltas:
        dibujo.text((20, y), linea, font=fuente, fill=color_de(linea))
        y += 21
    imagen.save(salida)
    print(f"{salida} ({ancho}x{alto})")


if __name__ == "__main__":
    main()
