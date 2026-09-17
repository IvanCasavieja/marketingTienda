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
#
# Las que vienen con WINDOWS se miden en cualquier maquina. Las que vienen con
# OFFICE (las Franklin Gothic que no son Medium, y Aptos) solo se pueden medir
# en una maquina que tenga Office instalado -- en las demas se saltean con un
# aviso y la tabla conserva lo que ya tenia (ver la fusion, mas abajo).
FUENTES = {
    # Windows
    "Impact":                 "impact.ttf",
    "Franklin Gothic Medium": "framd.ttf",
    "Arial":                  "arial.ttf",
    # Arial Black NO es Arial en negrita: es una familia propia y bastante mas
    # ancha. Sin esta linea caia por parecido de nombre en "arial" y el motor
    # la media 16,7% mas angosta de lo que es -- del lado peligroso, creyendo
    # que entraba texto que no entra. Se agrego el 17/09/2026 despues de verlo
    # en las cenefas de la Fiesta de Alemania, que la usan 12 veces.
    "Arial Black":            "ariblk.ttf",
    "Calibri":                "calibri.ttf",
    "Verdana":                "verdana.ttf",
    "Tahoma":                 "tahoma.ttf",
    "Trebuchet MS":           "trebuc.ttf",
    "Georgia":                "georgia.ttf",
    "Times New Roman":        "times.ttf",
    # Office -- se miden solo en una maquina que lo tenga
    "Franklin Gothic Book":        "FRABK.TTF",
    "Franklin Gothic Demi":        "FRADM.TTF",
    "Franklin Gothic Demi Cond":   "FRADMCN.TTF",
    "Franklin Gothic Heavy":       "FRAHV.TTF",
    "Franklin Gothic Medium Cond": "FRAMDCN.TTF",
    "Aptos":                       "aptos.ttf",
}

# ASCII imprimible + lo que aparece de verdad en descripciones y precios en
# espanol rioplatense.
CARACTERES = (
    "".join(chr(c) for c in range(32, 127))
    + "áéíóúÁÉÍÓÚñÑüÜ°ºª€“”‘’–—…·"
)

TAM = 200   # px: cuanto mas grande, menos error de redondeo al normalizar a em

# Se FUSIONA con lo que ya haya, no se pisa.
#
# Si no, correr esto en una maquina que no tenga alguna de las fuentes le
# BORRABA esa entrada a la tabla, sin aviso y sin que nadie lo pidiera. Y es
# justo lo que va a pasar: las Franklin de Office solo se pueden medir en una
# maquina con Office, asi que el flujo normal es correrlo en dos maquinas
# distintas y que cada una aporte lo que puede.
tabla = {}
if SALIDA.exists():
    try:
        tabla = json.loads(SALIDA.read_text(encoding="utf-8"))
        print(f"tabla existente: {len(tabla)} fuentes -- se conservan las que no se puedan medir acá\n")
    except Exception as exc:
        print(f"no pude leer la tabla existente ({exc}); se arranca de cero\n")

faltantes = []
for nombre, archivo in FUENTES.items():
    try:
        fuente = ImageFont.truetype(archivo, TAM)
    except Exception:
        ya = "se conserva la que ya estaba" if nombre.lower() in tabla else "queda sin medir"
        print(f"  falta   {nombre:<28} ({archivo}) -- {ya}")
        faltantes.append(nombre)
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

SALIDA.write_text(
    json.dumps(tabla, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    encoding="utf-8")
print()
print(f"tabla: {SALIDA}  ({SALIDA.stat().st_size / 1024:.1f} KB, {len(tabla)} fuentes)")
if faltantes:
    print(f"\nsin medir en esta maquina ({len(faltantes)}): {', '.join(faltantes)}")
    print("Las de Office se miden corriendo ESTO MISMO en una maquina que lo tenga:")
    print("  python backend/scripts/generar_font_metrics.py backend/app/data/font_metrics.json")
    print("y commiteando el JSON. La fusion conserva lo que ya estaba medido.")
