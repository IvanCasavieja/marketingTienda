"""El achique de un pedazo VOLADO (superíndice), y por qué se mide así.

Caso real que lo motivó (Ivan, 17/09/2026): en Rompe Precios Congelados A4 el
diseño dejó `baseline=30000` sobre el precio ENTERO y no solo sobre el "$".
PowerPoint dibuja un run volado a ~2/3 de su cuerpo SIN cambiar el número, así
que el cartel salía con el precio mucho más chico de lo que decía la casilla
del tamaño -- y el equipo lo venía compensando a mano subiendo de 180 a 280 pt.
"""
import pytest

from app.services.cenefas.capacidad import capacidad_por_componente
from app.services.cenefas.component_renderer import _segmentos_medibles
from app.services.cenefas.font_metrics import FACTOR_VOLADITA, pt_efectivo


# ---------------------------------------------------------------------------
# La regla, que es la parte contraintuitiva
# ---------------------------------------------------------------------------

def test_sin_voladita_el_cuerpo_no_se_toca():
    assert pt_efectivo(220, 0) == 220
    assert pt_efectivo(220, None) == 220
    assert pt_efectivo(220, "") == 220


def test_con_voladita_el_cuerpo_se_achica():
    assert pt_efectivo(220, 30000) == pytest.approx(220 * FACTOR_VOLADITA)


@pytest.mark.parametrize("desplazamiento", [5000, 20000, 30000, 95000, -30000])
def test_el_achique_es_BINARIO_no_proporcional(desplazamiento):
    # Esto es lo que no se entiende a simple vista y es la clave del caso:
    # subir un pedazo 5 % o 95 % da EXACTAMENTE el mismo cuerpo. Lo único que
    # cambia es la altura. Por eso mover el "$" con las flechitas del panel
    # nunca parecía cambiarle el tamaño: ya estaba achicado antes de tocarlo,
    # y seguía igual de achicado después.
    assert pt_efectivo(108, desplazamiento) == pytest.approx(108 * FACTOR_VOLADITA)


def test_solo_el_cero_devuelve_el_cuerpo_completo():
    # El único desplazamiento que devuelve el tamaño real es 0.
    assert pt_efectivo(108, 0) == 108
    assert pt_efectivo(108, 1) != 108


# ---------------------------------------------------------------------------
# Que lo respete lo que MIDE
# ---------------------------------------------------------------------------

def _caja_precio(baseline_precio):
    """El cuadro real de Congelados A4: "$" volado 95 % + el precio."""
    return {
        "id": "c1", "type": "text",
        "base_bounds": {"x": 0.08, "y": 19.94, "width": 13.72, "height": 5.68},
        "style": {"font_size": 58.5, "font_family": "Impact"},
        "segments": [
            {"type": "variable", "value": "unidadMoneda",
             "style": {"font_size": 108, "baseline": 95000}},
            {"type": "variable", "value": "precioOferta",
             "style": {"font_size": 220, "baseline": baseline_precio}},
        ],
    }


def test_la_medicion_usa_el_cuerpo_dibujado_y_no_el_declarado():
    comp = _caja_precio(30000)
    piezas = dict(_segmentos_medibles(comp, {"unidadMoneda": "$", "precioOferta": "219"}))
    assert piezas["$"] == pytest.approx(108 * FACTOR_VOLADITA)
    assert piezas["219"] == pytest.approx(220 * FACTOR_VOLADITA)


def test_sin_voladita_la_medicion_usa_el_declarado():
    comp = _caja_precio(0)
    piezas = dict(_segmentos_medibles(comp, {"unidadMoneda": "$", "precioOferta": "219"}))
    assert piezas["219"] == 220, "un precio NO volado tiene que medirse a su cuerpo real"


def test_en_capacidad_entran_mas_digitos_cuando_el_precio_va_volado():
    # El relleno de capacidad decía que en el precio de Congelados A4 entraban
    # dos dígitos, midiendo a 220 pt. Se dibuja a ~145, así que entran más.
    volado = capacidad_por_componente({"components": [_caja_precio(30000)]})["c1"]
    derecho = capacidad_por_componente({"components": [_caja_precio(0)]})["c1"]
    assert len(volado) > len(derecho), (
        f"volado={volado!r} derecho={derecho!r}: el volado tiene que entrar en más dígitos")
