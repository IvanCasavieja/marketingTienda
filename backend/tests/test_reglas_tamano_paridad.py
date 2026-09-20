"""Fija qué significa el número de una regla de tamaño, y que el preview muestre
lo mismo que se imprime.

El contrato, decidido por Ivan el 20/09/2026: **el número de la regla es el
número que sale, en todos los pedazos del cuadro.** "Si yo pongo 90 en el cuadro
entero, todo tiene que medir 90 y punto". Y si eso aplasta la proporción que el
diseño le daba al símbolo de moneda, es una decisión de quien escribió la regla:
para tocar un solo pedazo está la regla por segmento, que pone el número exacto
donde se lo pide.

Lo que había antes y por qué se fue: el motor calculaba una escala --el pt de la
regla dividido el font_size de la CAJA-- y multiplicaba cada pedazo por ella,
para conservar las proporciones del diseño. El problema no era la idea sino el
divisor: el font_size de la caja no es un número que alguien elija, lo llena el
importador con el del PRIMER pedazo del cuadro, que en un cuadro de precio es
casi siempre el "$". Medido sobre las 23 plantillas: de 112 cuadros de varios
pedazos, en 83 es el del primer pedazo y en 26 no es ni el primero ni el mayor.
En Congelados A4 la caja dice 58,5 con pedazos de 108 y 220, así que una regla
de 90 dejaba el precio en 338,5: escrita para achicar, agrandaba un 54%.

El preview evalúa las reglas por su cuenta --por eso el cambio se ve al escribir
la regla, sin generar nada-- así que cualquier cambio acá tiene que ir también a
`aplicarTamanos` en frontend/lib/cenefas/reglas.ts, o la pantalla vuelve a
mentir. Este test vigila las dos puntas: los números del lado Python y, leyendo
el .ts como texto, que el espejo diga lo mismo. Leerlo como texto es rústico a
propósito: no necesita Node ni build, así que corre en el mismo job de CI que el
resto del motor (mismo criterio que test_factor_voladita.py).
"""
import pathlib
import re

from app.services.cenefas.rules_engine import apply_font_sizes

_ESPEJO = (pathlib.Path(__file__).resolve().parents[2]
           / "frontend" / "lib" / "cenefas" / "reglas.ts")


def _fuente() -> str:
    assert _ESPEJO.exists(), f"se movió el espejo del preview: {_ESPEJO}"
    return _ESPEJO.read_text(encoding="utf-8")


def _cuadro(font_size, line_height_pt=None, segmentos=()):
    estilo = {"font_size": font_size}
    if line_height_pt is not None:
        estilo["line_height_pt"] = line_height_pt
    cuadro = {"id": "c", "type": "text", "style": estilo}
    if segmentos:
        cuadro["segments"] = [
            {"type": "variable", "value": "precioOferta", "style": {"font_size": pt}}
            for pt in segmentos
        ]
    return cuadro


# ------------------------------------------- el backend: el 90 es 90 en todo


def test_una_regla_sobre_el_cuadro_pone_el_mismo_pt_en_todos_los_pedazos():
    # La geometría real del precio de Rompe Precios Congelados A4 (63609775):
    # caja 58,5 --el fósil del achique viejo-- y pedazos de 108 ("$") y 220.
    salida = apply_font_sizes([_cuadro(58.5, segmentos=(108.0, 220.0))], {"c": 90.0})[0]
    assert salida["style"]["font_size"] == 90.0
    assert [s["style"]["font_size"] for s in salida["segments"]] == [90.0, 90.0], (
        "el número de la regla tiene que salir tal cual en cada pedazo: con la "
        "escala vieja esto daba [166,2, 338,5]")


def test_el_pt_no_depende_del_tamano_guardado_de_la_caja():
    # El mismo cuadro con tres cajas distintas --el número invisible que el
    # importador dejó-- tiene que dar el mismo resultado.
    for caja in (18.2, 58.5, 220.0):
        salida = apply_font_sizes([_cuadro(caja, segmentos=(108.0, 220.0))], {"c": 90.0})[0]
        assert [s["style"]["font_size"] for s in salida["segments"]] == [90.0, 90.0], (
            f"con la caja en {caja} el resultado cambió: volvió la escala")


def test_el_alto_del_renglon_no_lo_toca_la_regla():
    # `line_height_pt` no es una letra: es el pedazo invisible con el que el
    # diseño fuerza la altura del renglón. Si la regla achica el precio, el
    # renglón queda donde el diseño lo puso.
    salida = apply_font_sizes([_cuadro(130.0, line_height_pt=250.0, segmentos=(130.0,))],
                              {"c": 90.0})[0]
    assert salida["style"]["line_height_pt"] == 250.0


def test_un_pedazo_sin_tamano_propio_igual_recibe_el_de_la_regla():
    cuadro = {"id": "c", "type": "text", "style": {"font_size": 40.0}, "segments": [
        {"type": "static", "value": "$"},
        {"type": "variable", "value": "precioOferta", "style": {"font_size": 120.0}},
    ]}
    salida = apply_font_sizes([cuadro], {"c": 90.0})[0]
    assert [s["style"]["font_size"] for s in salida["segments"]] == [90.0, 90.0]


def test_la_regla_de_un_pedazo_manda_sobre_la_del_cuadro():
    # Las dos juntas: el cuadro va a 90 y el pedazo que se eligió, a 40.
    salida = apply_font_sizes([_cuadro(58.5, segmentos=(108.0, 220.0))],
                              {"c": 90.0}, {"c": {0: 40.0}})[0]
    assert [s["style"]["font_size"] for s in salida["segments"]] == [40.0, 90.0]


# ----------------------------------------- el preview, leyendo el .ts como texto


def test_el_preview_no_calcula_ninguna_escala():
    fuente = _fuente()
    bloque = re.search(r"export function aplicarTamanos.*?\n}", fuente, re.S)
    assert bloque, "no se encontró aplicarTamanos en reglas.ts"
    cuerpo = bloque.group(0)
    assert "escala" not in cuerpo, (
        "volvió la escala a aplicarTamanos: el preview vuelve a mostrar un "
        "cuerpo distinto del que pide la regla. Ver apply_font_sizes en "
        "rules_engine.py: el pt va tal cual a cada pedazo.")
    assert re.search(r"font_size:\s*pt", cuerpo), (
        "aplicarTamanos dejó de poner el pt de la regla en los segmentos.")


def test_el_preview_no_toca_el_alto_del_renglon():
    fuente = _fuente()
    bloque = re.search(r"export function aplicarTamanos.*?\n}", fuente, re.S)
    assert "line_height_pt" not in bloque.group(0), (
        "aplicarTamanos volvió a tocar line_height_pt, y el backend no lo toca: "
        "el renglón queda a una altura en pantalla y a otra en el papel.")
