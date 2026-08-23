"""Genera la tabla de anchos de caracter de las fuentes reales.

Se corre UNA VEZ, en una maquina que tenga las fuentes instaladas (Windows).
Guarda solo METRICAS -- anchos por caracter en fracciones de em -- no el
archivo de la fuente, asi que el resultado se puede versionar y desplegar sin
depender de tener la tipografia en el servidor.
"""
import json
import pathlib
import sys

from PIL import ImageFont

SALIDA = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "font_metrics.json")

# nombre tal cual aparece en el PPTX -> archivo de fuente
FUENTES = {
    "Impact":                 "impact.ttf",
    "Franklin Gothic Medium": "framd.ttf",
    "Arial":                  "arial.ttf",
    "Calibri":                "calibri.ttf",
    "Verdana":                "verdana.ttf",
    "Tahoma":                 "tahoma.ttf",
    "Trebuchet MS":           "trebuc.ttf",
    "Georgia":                "georgia.ttf",
    "Times New Roman":        "times.ttf",
}

# ASCII imprimible + lo que aparece de verdad en descripciones y precios en
# espanol rioplatense.
CARACTERES = (
    "".join(chr(c) for c in range(32, 127))
    + "áéíóúÁÉÍÓÚñÑüÜ°ºª€“”‘’–—…·"
)

TAM = 200   # px: cuanto mas grande, menos error de redondeo al normalizar a em

tabla = {}
for nombre, archivo in FUENTES.items():
    try:
        fuente = ImageFont.truetype(archivo, TAM)
    except Exception:
        print(f"  falta   {nombre} ({archivo})")
        continue

    anchos = {}
    for ch in CARACTERES:
        try:
            anchos[ch] = round(fuente.getlength(ch) / TAM, 4)
        except Exception:
            continue
    # Ancho de reserva para cualquier caracter que no este en la tabla.
    promedio = round(sum(anchos.values()) / len(anchos), 4)
    tabla[nombre.lower()] = {"default": promedio, "chars": anchos}
    print(f"  OK      {nombre:<24} {len(anchos)} caracteres | promedio {promedio} em")

SALIDA.write_text(json.dumps(tabla, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print()
print(f"tabla: {SALIDA}  ({SALIDA.stat().st_size / 1024:.1f} KB, {len(tabla)} fuentes)")
