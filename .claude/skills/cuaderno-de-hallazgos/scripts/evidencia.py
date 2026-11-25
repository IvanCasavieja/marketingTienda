#!/usr/bin/env python3
"""Prepara una captura para el cuaderno: la achica, la pasa a JPG y marca el problema.

    python evidencia.py captura.png --salida $S/cuaderno/cuaderno/recorridos/2026-11-25/H-012.jpg
    python evidencia.py captura.png --salida .../H-012.jpg --marco 120,80,300,60   # x,y,ancho,alto
    python evidencia.py antes.png despues.png --salida .../H-012-antes-despues.jpg  # antes y ahora

- Máximo 1000 px de ancho y calidad 70: el cuaderno vive en el repo y no
  tiene que pesar (una captura queda en ~60-120 KB).
- --marco dibuja un recuadro rojo (coordenadas de la captura original, las
  mismas de click-xy) para que se vea de una dónde está el problema.
- Con dos capturas arma una sola imagen con «ANTES» (franja roja) y «AHORA»
  (franja verde), en letra grande. Las de celular (más altas que anchas) van
  lado a lado; las de notebook, una arriba de la otra, para que en el mail
  del celular se lean (Ivan, 25/11/2026: el mail "no se entiende", y el
  rótulo salía «Despu?s»: la letra que trae Pillow por defecto no tiene tildes
  y es diminuta).

Necesita Pillow.
"""
from __future__ import annotations

import argparse
import pathlib

ROJO = "#C81E1E"
VERDE = "#0F7B3F"
# Letras con tildes, de la más común en Linux a la de Windows. Si no hay
# ninguna, la que trae Pillow (desde la 10.1 se puede agrandar).
LETRAS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def letra(tam: int):
    from PIL import ImageFont

    for ruta in LETRAS:
        if pathlib.Path(ruta).exists():
            return ImageFont.truetype(ruta, tam)
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:  # Pillow viejo
        return ImageFont.load_default()


def con_rotulo(im, texto: str, color: str):
    """La captura con una franja de color arriba y el rótulo en blanco."""
    from PIL import Image, ImageDraw

    franja = max(44, im.width // 18)
    lienzo = Image.new("RGB", (im.width, im.height + franja), color)
    lienzo.paste(im, (0, franja))
    ImageDraw.Draw(lienzo).text((16, franja // 2), texto, fill="white", font=letra(int(franja * 0.6)), anchor="lm")
    return lienzo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capturas", nargs="+")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--marco", action="append", default=[], help="x,y,ancho,alto (repetible)")
    ap.add_argument("--ancho", type=int, default=1000)
    a = ap.parse_args()

    from PIL import Image, ImageDraw

    def abrir(p: str):
        im = Image.open(p).convert("RGB")
        d = ImageDraw.Draw(im)
        for m in a.marco:
            x, y, w, h = (int(float(v)) for v in m.split(","))
            for g in range(4):
                d.rectangle((x - g, y - g, x + w + g, y + h + g), outline="#F6323E")
        return im

    def a_lo_ancho(im, ancho: int):
        return im if im.width <= ancho else im.resize((ancho, int(im.height * ancho / im.width)))

    imgs = [abrir(p) for p in a.capturas[:2]]
    if len(imgs) == 2:
        de_celular = all(i.height > i.width for i in imgs)
        # Cada una a su ancho final ANTES de rotular: así la letra queda del
        # mismo tamaño en las dos y no se achica con la imagen.
        ancho = a.ancho // 2 if de_celular else a.ancho
        antes = con_rotulo(a_lo_ancho(imgs[0], ancho), "ANTES", ROJO)
        ahora = con_rotulo(a_lo_ancho(imgs[1], ancho), "AHORA", VERDE)
        hueco = 16
        if de_celular:
            lienzo = Image.new("RGB", (antes.width + ahora.width + hueco, max(antes.height, ahora.height)), "white")
            lienzo.paste(antes, (0, 0))
            lienzo.paste(ahora, (antes.width + hueco, 0))
        else:
            lienzo = Image.new("RGB", (max(antes.width, ahora.width), antes.height + ahora.height + hueco), "white")
            lienzo.paste(antes, (0, 0))
            lienzo.paste(ahora, (0, antes.height + hueco))
        im = lienzo
    else:
        im = a_lo_ancho(imgs[0], a.ancho)
    salida = pathlib.Path(a.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    im.save(salida, "JPEG", quality=70, optimize=True)
    print(f"{salida} ({salida.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
