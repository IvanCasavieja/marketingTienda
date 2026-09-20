"""Fija que una regla de tamaño se vea en el preview igual que se imprime.

Pedido de Ivan (20/09/2026): "el preview tiene que poder mostrar los cambios en
vivo". El preview YA evalúa las reglas de tamaño por su cuenta --por eso el
cambio se ve al escribir la regla, sin generar nada-- pero las evaluaba distinto
que el backend en dos puntos, y los dos se notan recién con la primera regla
declarada (hoy hay cero en producción):

1. **El alto del renglón.** `line_height_pt` es el pedazo invisible con el que
   el diseño fuerza la altura del renglón cuando algo va volado. Lo tienen 22
   cuadros de precio en 9 plantillas. El backend lo escala junto con el cuerpo;
   el preview no lo tocaba, así que con una regla de 90 pt en Rompe Precios A4
   la pantalla armaba el renglón con 250 pt y el PPTX con 173,1 (en Fiesta
   Alemania, 140 contra 210): el precio se veía a una altura y se imprimía a
   otra.
2. **El redondeo.** El backend usa `round(x, 1)` de Python, que manda los
   empates al par; el preview usaba `toFixed(1)`, que los manda para arriba. En
   Inglaterra Rural un segmento de 11 pt con una regla de 90 sobre una caja de
   24 da 41,25: el PPTX escribía 41,2 y la pantalla mostraba 41,3.

Cómo se verificó el arreglo (20/09/2026): se corrieron los DOS motores sobre los
555 cuadros de texto de las 23 plantillas de producción con una regla de 90 pt
--`apply_font_sizes` en Python y `aplicarTamanos` transpilado con el TypeScript
del repo-- y dieron el mismo cuerpo en todos los segmentos y el mismo
`line_height_pt` en todos los cuadros. Antes del arreglo: 22 cuadros con distinto
alto de renglón y 3 con distinto redondeo.

Este test es la red que queda para que no se vuelvan a separar, y es rústico a
propósito: leer el .ts como texto no necesita Node ni build, así que corre en el
mismo job de CI que el resto del motor. Mismo criterio que
test_factor_voladita.py, que compara la constante de la voladita leyendo el .ts.
"""
import pathlib
import re

from app.services.cenefas.rules_engine import apply_font_sizes

_ESPEJO = (pathlib.Path(__file__).resolve().parents[2]
           / "frontend" / "lib" / "cenefas" / "reglas.ts")


def _fuente() -> str:
    assert _ESPEJO.exists(), f"se movió el espejo del preview: {_ESPEJO}"
    return _ESPEJO.read_text(encoding="utf-8")


# ----------------------------------------------------- el backend, con números


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


def test_el_backend_escala_el_alto_del_renglon_con_el_cuerpo():
    # La geometría real del cuadro del precio de Rompe Precios A4 (b0a80837).
    salida = apply_font_sizes([_cuadro(130.0, line_height_pt=250.0, segmentos=(130.0,))],
                              {"c": 90.0})[0]
    assert salida["style"]["font_size"] == 90.0
    assert salida["style"]["line_height_pt"] == 173.1, (
        "si esto cambió, el espejo del preview tiene que cambiar igual")
    assert salida["segments"][0]["style"]["font_size"] == 90.0


def test_el_backend_redondea_los_empates_al_par():
    # Inglaterra Rural: segmento de 11 pt, caja de 24, regla de 90 -> 41,25.
    salida = apply_font_sizes([_cuadro(24.0, segmentos=(11.0,))], {"c": 90.0})[0]
    assert salida["segments"][0]["style"]["font_size"] == 41.2


# ------------------------------------------------- el preview, leyendo el .ts


def test_el_preview_escala_el_alto_del_renglon():
    fuente = _fuente()
    assert "line_height_pt" in fuente, (
        "aplicarTamanos dejó de escalar line_height_pt: con una regla de tamaño "
        "el preview vuelve a poner el precio a otra altura que el PPTX. Ver "
        "apply_font_sizes en rules_engine.py.")
    escalado = re.search(r"line_height_pt:\s*aDecima\([^)]*\*\s*escala\s*\)", fuente)
    assert escalado, (
        "line_height_pt aparece en reglas.ts pero no escalado por `escala` con "
        "aDecima(): el backend hace line_height_pt * escala redondeado a una "
        "décima.")


def test_el_preview_redondea_como_el_backend():
    fuente = _fuente()
    assert "function aDecima" in fuente, (
        "se fue aDecima() de reglas.ts. Es el redondeo del backend "
        "(round(x, 1) de Python, empates al par).")
    assert not re.search(r"font_size:\s*\+\(.*toFixed\(1\)", fuente), (
        "volvió toFixed(1) para un cuerpo: redondea los empates para arriba y "
        "el backend los manda al par, así que la pantalla vuelve a mostrar una "
        "décima distinta de la que se imprime.")


def test_el_preview_escala_los_segmentos_con_la_misma_referencia():
    # El divisor de la escala tiene que ser el MISMO de los dos lados: el
    # font_size de la caja, y si no tiene, el del segmento más grande.
    fuente = _fuente()
    assert re.search(r"const\s+base\s*=\s*propio\s*\|\|", fuente), (
        "cambió la referencia de la escala en el preview. En el backend es "
        "`base = style.font_size` y si no hay, el máximo de los segmentos.")
    assert re.search(r"const\s+escala\s*=\s*base\s*\?\s*pt\s*/\s*base", fuente), (
        "cambió la fórmula de la escala en el preview: en el backend es "
        "pt / base.")
