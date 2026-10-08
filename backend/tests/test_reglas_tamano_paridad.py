"""Fija qué significa el número de una regla de tamaño, y que el preview muestre
lo mismo que se imprime.

El contrato, decidido por Ivan el 20/09/2026: **el número de la regla es el
número que sale, en todos los pedazos del cuadro.** "Si yo pongo 90 en el cuadro
entero, todo tiene que medir 90 y punto". Para tocar un solo pedazo está la
regla por segmento, que pone el número exacto donde se lo pide.

Con una excepción, pedida por Ivan el 08/10/2026 con las cenefas de Non Food en
la mano: los pedazos VOLADOS (el símbolo de moneda y los centavos, con
`baseline`) y el aire entre ellos NO toman el número, conservan la proporción
del diseño respecto del pedazo que manda. Con el contrato a secas, el "U$S" de
120 volado junto al precio de 228 pasaba a 164 cuando la regla bajaba el precio
a 164 --más grande que en el diseño-- y como la voladita es un porcentaje de su
propio cuerpo, subía y dejaba de estar centrado con el número. Ver
_cuerpo_del_pedazo en rules_engine.py.

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


def test_el_preview_no_calcula_ninguna_escala_contra_la_caja():
    fuente = _fuente()
    bloque = re.search(r"export function aplicarTamanos.*?\n}", fuente, re.S)
    assert bloque, "no se encontró aplicarTamanos en reglas.ts"
    cuerpo = bloque.group(0)
    assert "escala" not in cuerpo, (
        "volvió la escala a aplicarTamanos: el preview vuelve a mostrar un "
        "cuerpo distinto del que pide la regla. Ver apply_font_sizes en "
        "rules_engine.py: el pt va tal cual a cada pedazo que manda.")
    assert re.search(r"font_size:\s*cuerpoDelPedazo\(seg, comp\.style, pt, principal\)", cuerpo), (
        "aplicarTamanos dejó de resolver el cuerpo de cada pedazo con cuerpoDelPedazo.")
    assert re.search(r"cuerpoPrincipal\(nuevo\.segments, comp\.style\)", cuerpo), (
        "el divisor de la proporción tiene que ser el pedazo que manda, no la caja.")
    # Las dos funciones del espejo, con la misma cuenta que el backend.
    pedazo = re.search(r"function cuerpoDelPedazo.*?\n}", fuente, re.S)
    assert pedazo and "return pt;" in pedazo.group(0), "cuerpoDelPedazo no devuelve pt al pedazo que manda"
    assert re.search(r"Math\.floor\(\(propio \* pt\) / principal \* 10 \+ 0\.5\) / 10", pedazo.group(0)), (
        "el redondeo del espejo dejó de ser floor(x*10+0.5)/10, el mismo del backend")
    principal = re.search(r"function cuerpoPrincipal.*?\n}", fuente, re.S)
    assert principal and "esVolado(seg, caja) || esAire(seg)" in principal.group(0), (
        "cuerpoPrincipal tiene que saltear los volados y el aire, como _cuerpo_principal")
    volado = re.search(r"function esVolado.*?\n}", fuente, re.S)
    assert volado and "seg.style?.baseline ?? caja?.baseline" in volado.group(0), (
        "esVolado tiene que heredar la voladita de la caja, como _es_volado")


def test_el_preview_no_toca_el_alto_del_renglon():
    fuente = _fuente()
    bloque = re.search(r"export function aplicarTamanos.*?\n}", fuente, re.S)
    assert "line_height_pt" not in bloque.group(0), (
        "aplicarTamanos volvió a tocar line_height_pt, y el backend no lo toca: "
        "el renglón queda a una altura en pantalla y a otra en el papel.")


# ------------------------------- la excepción: los volados siguen al que manda


def _exclusivos_a4():
    # La geometría real del precio de Exclusivos TI A4 (08/10/2026): símbolo
    # 120 volado, dos espacios volados, precio 228, centavos 132 volados.
    return {"id": "c", "type": "text", "style": {"font_size": 120.0, "line_height_pt": 228.0}, "segments": [
        {"type": "variable", "value": "unidadMoneda", "style": {"font_size": 120.0, "baseline": 30000}},
        {"type": "static", "value": "  ", "style": {"font_size": 120.0, "baseline": 30000, "font_bold": True}},
        {"type": "variable", "value": "precioOferta", "style": {"font_size": 228.0}},
        {"type": "variable", "value": "decimalPrecioOferta", "style": {"font_size": 132.0, "baseline": 30000}},
    ]}


def test_los_pedazos_volados_conservan_la_proporcion_con_el_precio():
    salida = apply_font_sizes([_exclusivos_a4()], {"c": 164.0})[0]
    assert salida["style"]["font_size"] == 164.0
    assert [s["style"]["font_size"] for s in salida["segments"]] == [86.3, 86.3, 164.0, 94.9], (
        "el símbolo y los centavos volados tienen que achicarse en la misma "
        "proporción que el precio (164/228); con el número a secas el U$S "
        "quedaba a 164, más grande que en el diseño, y se subía")
    assert salida["style"]["line_height_pt"] == 228.0


def test_la_voladita_no_cambia_con_la_regla():
    # La posición del volado la da su baseline, que sigue siendo del diseño.
    salida = apply_font_sizes([_exclusivos_a4()], {"c": 164.0})[0]
    assert [s["style"].get("baseline") for s in salida["segments"]] == [30000, 30000, None, 30000]


def test_exclusivos_3xa4_simbolo_con_espacios_en_el_mismo_pedazo():
    # "<<UM>>   " en un solo run de 60 volado, precio 100, centavos 66 volados.
    cuadro = {"id": "c", "type": "text", "style": {"font_size": 60.0}, "segments": [
        {"type": "variable", "value": "unidadMoneda", "style": {"font_size": 60.0, "baseline": 30000}},
        {"type": "static", "value": "   ", "style": {"font_size": 60.0, "baseline": 30000}},
        {"type": "variable", "value": "precioOferta", "style": {"font_size": 100.0}},
        {"type": "variable", "value": "decimalPrecioOferta", "style": {"font_size": 66.0, "baseline": 30000}},
    ]}
    salida = apply_font_sizes([cuadro], {"c": 68.0})[0]
    assert [s["style"]["font_size"] for s in salida["segments"]] == [40.8, 40.8, 68.0, 44.9]


def test_sin_voladita_sigue_valiendo_el_numero_en_todos_los_pedazos():
    # El contrato del 20/09 intacto para lo que no va volado: el "$" chico que
    # comparte la línea de base con el precio toma el número de la regla.
    cuadro = {"id": "c", "type": "text", "style": {"font_size": 24.0}, "segments": [
        {"type": "variable", "value": "unidadMoneda", "style": {"font_size": 24.0}},
        {"type": "variable", "value": "precioRegular", "style": {"font_size": 28.0}},
        {"type": "static", "value": " unidad", "style": {"font_size": 20.0}},
    ]}
    salida = apply_font_sizes([cuadro], {"c": 20.0})[0]
    assert [s["style"]["font_size"] for s in salida["segments"]] == [20.0, 20.0, 20.0]


def test_si_todos_los_pedazos_van_volados_no_hay_quien_mande_y_vale_el_numero():
    cuadro = {"id": "c", "type": "text", "style": {"font_size": 100.0, "baseline": 30000}, "segments": [
        {"type": "variable", "value": "unidadMoneda", "style": {"font_size": 60.0}},
        {"type": "variable", "value": "precioOferta", "style": {"font_size": 100.0}},
    ]}
    salida = apply_font_sizes([cuadro], {"c": 80.0})[0]
    assert [s["style"]["font_size"] for s in salida["segments"]] == [80.0, 80.0]


def test_el_volado_hereda_la_voladita_de_la_caja():
    # Igual que al medir (_segmentos_medibles) y al dibujar: baseline en la
    # caja y un pedazo sin la suya es un pedazo volado.
    cuadro = {"id": "c", "type": "text", "style": {"font_size": 100.0, "baseline": 30000}, "segments": [
        {"type": "variable", "value": "unidadMoneda", "style": {"font_size": 60.0}},
        {"type": "variable", "value": "precioOferta", "style": {"font_size": 100.0, "baseline": 0}},
    ]}
    salida = apply_font_sizes([cuadro], {"c": 50.0})[0]
    assert [s["style"]["font_size"] for s in salida["segments"]] == [30.0, 50.0]


def test_la_regla_por_segmento_sigue_mandando_sobre_el_volado():
    # Quien quiere el símbolo en un número exacto lo dice con la regla del pedazo.
    salida = apply_font_sizes([_exclusivos_a4()], {"c": 164.0}, {"c": {0: 100.0}})[0]
    assert [s["style"]["font_size"] for s in salida["segments"]] == [100.0, 86.3, 164.0, 94.9]


def test_el_mismo_redondeo_en_las_dos_puntas():
    # floor(x*10+0.5)/10 en Python y en el .ts: Math.round y round() no empatan
    # en los .x5 (round() de Python va al par).
    from app.services.cenefas.rules_engine import _cuerpo_del_pedazo
    seg = {"type": "static", "value": "$", "style": {"font_size": 85.0, "baseline": 30000}}
    assert _cuerpo_del_pedazo(seg, {}, 50.0, 100.0) == 42.5
    assert _cuerpo_del_pedazo(seg, {}, 55.0, 100.0) == 46.8   # 46.75 -> 46.8, no 46.7
