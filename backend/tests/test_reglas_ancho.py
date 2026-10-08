"""Fija la regla de ANCHO por cantidad de caracteres (Ivan, 08/10/2026).

Nació por el cuadro del código. Un grupo unificado imprime los SKU de todos sus
productos ("504891 - 504893 - 504894 - 514453") en un cuadro que el diseñador
dibujó para UNO: el texto se partía hacia abajo y pisaba la descripción. En la
3xA4 de marca propia el cuadro mide 4,25 cm y ya dos códigos no entran.

Mismo criterio que el cuerpo (test_reglas_tamano.py): lo declara una persona
con una condición sobre el largo del texto, el motor no mide nada, y `len()`
da lo mismo en Python que en TypeScript. Dos diferencias a propósito: si
matchean varias gana la MÁS ANCHA (la que más lugar deja), y el cuadro crece
desde su CENTRO, la mitad hacia cada lado.
"""
import pathlib

from app.services.cenefas.component_renderer import _rect_texto_real, preparar_componentes
from app.services.cenefas.rules_engine import (
    apply_widths, evaluate_font_size_rules, evaluate_rules, evaluate_width_rules,
)

_ESPEJO = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "cenefas" / "reglas.ts"
_CANVAS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "components" / "cenefas" / "editor" / "Canvas.tsx"


def _cod(width=4.25, x=11.79):
    return {
        "id": "cod", "type": "text",
        "base_bounds": {"x": x, "y": 0.87, "width": width, "height": 0.6},
        "style": {"font_size": 10.0, "align": "center", "font_family": "Arial"},
        "segments": [
            {"type": "static", "value": "COD.: ", "style": {"font_size": 10.0}},
            {"type": "variable", "value": "codigo", "transform": "none", "style": {"font_size": 10.0}},
        ],
    }


def _regla(cm, largo, id_="r", campo="codigo", segmento=None):
    r = {
        "id": id_, "target_component_id": "cod",
        "condition": {"field": campo, "operator": "length_greater_than", "value": largo},
        "action": {"type": "set_width", "value": cm},
    }
    if segmento is not None:
        r["target_segment_index"] = segmento
    return r


GRUPO = {"codigo": "504891 - 504893 - 504894 - 514453"}   # 33 caracteres, 4 SKU
SOLO = {"codigo": "504891"}


# ------------------------------------------------------------ evaluación


def test_sin_guion_no_matchea_y_el_cuadro_queda_como_lo_dibujo_el_diseno():
    assert evaluate_width_rules([_regla(7.9, 12)], SOLO) == {}
    salida = preparar_componentes([_cod()], [_regla(7.9, 12)], SOLO)[0]
    assert salida["base_bounds"] == _cod()["base_bounds"]


def test_con_grupo_matchea():
    assert evaluate_width_rules([_regla(7.9, 12)], GRUPO) == {"cod": 7.9}


def test_si_matchean_varias_gana_la_mas_ancha_sin_importar_el_orden():
    escalera = [_regla(4.6, 12, "a"), _regla(6.2, 21, "b"), _regla(7.9, 30, "c"), _regla(9.5, 39, "d")]
    assert evaluate_width_rules(escalera, GRUPO) == {"cod": 7.9}
    assert evaluate_width_rules(list(reversed(escalera)), GRUPO) == {"cod": 7.9}


def test_una_regla_sin_ancho_valido_se_ignora():
    assert evaluate_width_rules([_regla("ancho", 12)], GRUPO) == {}
    assert evaluate_width_rules([_regla(0, 12)], GRUPO) == {}
    assert evaluate_width_rules([_regla(-3, 12)], GRUPO) == {}


def test_una_regla_sobre_un_pedazo_no_cuenta():
    # Un ancho es del cuadro entero: apuntada a un segmento no hace nada.
    assert evaluate_width_rules([_regla(7.9, 12, segmento=1)], GRUPO) == {}


def test_una_regla_de_ancho_no_oculta_ni_cambia_el_cuerpo():
    assert evaluate_rules([_regla(7.9, 12)], GRUPO) == {}
    assert evaluate_font_size_rules([_regla(7.9, 12)], GRUPO) == {}


# ------------------------------------------------------------ aplicación


def test_el_cuadro_crece_desde_el_centro():
    original = _cod(width=4.25, x=11.79)
    salida = apply_widths([original], {"cod": 7.9})[0]
    b = salida["base_bounds"]
    assert b["width"] == 7.9
    # mismo centro: 11,79 + 4,25/2 = 13,915
    assert abs((b["x"] + b["width"] / 2) - (11.79 + 4.25 / 2)) < 1e-6
    assert b["y"] == 0.87 and b["height"] == 0.6


def test_apply_widths_devuelve_copias_y_no_toca_el_original():
    original = _cod()
    apply_widths([original], {"cod": 7.9})
    assert original["base_bounds"]["width"] == 4.25


def test_computed_bounds_se_ensancha_con_la_misma_escala():
    # Un diseño escalado al doble al render: computed = base x 2.
    c = _cod(width=4.0, x=10.0)
    c["computed_bounds"] = {"x": 20.0, "y": 1.74, "width": 8.0, "height": 1.2}
    salida = apply_widths([c], {"cod": 6.0})[0]
    assert salida["base_bounds"]["width"] == 6.0 and salida["base_bounds"]["x"] == 9.0
    assert salida["computed_bounds"]["width"] == 12.0 and salida["computed_bounds"]["x"] == 18.0


def test_preparar_componentes_aplica_el_ancho_y_el_texto_deja_de_partirse():
    comp = _cod()
    sin = preparar_componentes([comp], [], GRUPO)[0]
    con = preparar_componentes([comp], [_regla(7.9, 12)], GRUPO)[0]
    assert con["base_bounds"]["width"] == 7.9
    # Con 4,25 cm el código de 4 SKU se parte en varios renglones; con 7,9 va en uno.
    alto_sin = _rect_texto_real(sin, GRUPO)["height"]
    alto_con = _rect_texto_real(con, GRUPO)["height"]
    assert alto_con < alto_sin


# ------------------------------------------------------------ el espejo del preview


def test_el_preview_evalua_la_misma_regla():
    fuente = _ESPEJO.read_text(encoding="utf-8")
    assert "set_width" in fuente, "reglas.ts no conoce la acción set_width"
    assert "export function anchosDeCuadro" in fuente and "export function aplicarAncho" in fuente
    # gana la más ancha, no la última
    assert "cm > previo" in fuente, "el espejo tiene que elegir la más ancha"
    # y crece desde el centro
    assert "(b.width - cm) / 2" in fuente, "el espejo tiene que conservar el centro"
    canvas = _CANVAS.read_text(encoding="utf-8")
    assert "aplicarAncho(" in canvas, "el canvas no dibuja el ancho de la regla"
    assert "corrimientoPorAncho" in canvas, (
        "el canvas tiene que descontar el ensanche al guardar: si no, el ancho de la regla queda horneado en la plantilla")
