#!/usr/bin/env python3
"""Prepara una captura para el cuaderno: la achica, la pasa a JPG y marca el problema.

    python evidencia.py captura.png --salida $S/cuaderno/cuaderno/recorridos/2026-11-25/H-012.jpg
    python evidencia.py captura.png --salida .../H-012.jpg --marco 120,80,300,60   # x,y,ancho,alto
    python evidencia.py antes.png despues.png --salida .../H-012-antes-despues.jpg  # lado a lado

- Máximo 1000 px de ancho y calidad 70: el cuaderno vive en el repo y no
  tiene que pesar (una captura queda en ~60-120 KB).
- --marco dibuja un recuadro rojo (coordenadas de la captura original, las
  mismas de click-xy) para que se vea de una dónde está el problema.
- Con dos capturas arma una imagen lado a lado con «Antes» y «Después».

Necesita Pillow.
"""
from __future__ import annotations

import argparse
import pathlib


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

    imgs = [abrir(p) for p in a.capturas[:2]]
    if len(imgs) == 2:
        alto = max(i.height for i in imgs)
        barra = 34
        lienzo = Image.new("RGB", (imgs[0].width + imgs[1].width + 24, alto + barra), "white")
        d = ImageDraw.Draw(lienzo)
        d.text((8, 10), "Antes", fill="black")
        d.text((imgs[0].width + 32, 10), "Después", fill="black")
        lienzo.paste(imgs[0], (0, barra))
        lienzo.paste(imgs[1], (imgs[0].width + 24, barra))
        im = lienzo
    else:
        im = imgs[0]
    ancho = a.ancho * (2 if len(imgs) == 2 else 1)
    if im.width > ancho:
        im = im.resize((ancho, int(im.height * ancho / im.width)))
    salida = pathlib.Path(a.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    im.save(salida, "JPEG", quality=70, optimize=True)
    print(f"{salida} ({salida.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
