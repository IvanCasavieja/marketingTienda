#!/usr/bin/env python3
"""Piezas de mentira para entregar en el entorno de pruebas (como la agencia).

    python imagenes_de_prueba.py --salida $S/piezas 1920x400 1080x1080 1080x1350 --zip

Cada imagen es un PNG con su medida escrita en grande y un color distinto, así
en las capturas se ve cuál es cuál. Con --zip arma además piezas.zip con todas
(para probar la entrega con ZIP). Para probar el aviso de piezas que faltan,
dejá afuera a propósito una de las medidas que pidió el equipo.

Necesita Pillow (`pip install pillow`).
"""
from __future__ import annotations

import argparse
import pathlib
import zipfile

COLORES = ["#0047BA", "#F6323E", "#1E8E3E", "#F29900", "#7B1FA2", "#00838F"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("medidas", nargs="+", help="ANCHOxALTO, por ejemplo 1920x400")
    ap.add_argument("--salida", default="piezas")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--nombre", default="pieza", help="prefijo de los archivos")
    a = ap.parse_args()

    from PIL import Image, ImageDraw, ImageFont

    out = pathlib.Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    hechas = []
    for i, m in enumerate(a.medidas):
        w, h = (int(x) for x in m.lower().split("x"))
        im = Image.new("RGB", (w, h), COLORES[i % len(COLORES)])
        d = ImageDraw.Draw(im)
        tam = max(18, min(w, h) // 5)
        try:
            fuente = ImageFont.truetype("DejaVuSans-Bold.ttf", tam)
        except OSError:
            try:
                fuente = ImageFont.truetype("arial.ttf", tam)
            except OSError:
                fuente = ImageFont.load_default()
        texto = f"{w}×{h}"
        caja = d.textbbox((0, 0), texto, font=fuente)
        d.text(((w - (caja[2] - caja[0])) / 2, (h - (caja[3] - caja[1])) / 2), texto, fill="white", font=fuente)
        archivo = out / f"{a.nombre}-{w}x{h}.png"
        im.save(archivo, optimize=True)
        hechas.append(archivo)
        print(archivo)
    if a.zip:
        z = out / f"{a.nombre}s.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in hechas:
                zf.write(f, f.name)
        print(z)


if __name__ == "__main__":
    main()
