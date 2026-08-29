"""Lo que Tinín le enseña a la gente tiene que coincidir con lo que el motor hace.

Por qué existe: el 2026-08-29 se corrigió la regla del combo en el motor
(tipoOferta pasó de "2x$299" a "2x") y en M x N se movió el literal de
precioOferta a promoOferta. El motor quedó bien; el conocimiento de Tinín no.
Durante días contestó con seguridad la regla vieja, y es —según el propio
archivo— "la que más se pregunta".

El desfasaje no lo agarra nadie: el agente responde con la misma soltura esté
bien o mal, y solo se nota cruzando su respuesta con una corrida real. Estos
tests hacen ese cruce: sacan los valores del motor y los buscan en el texto.
"""
import re

import pytest

from app.services.cenefas.convertidor_variables import resolver_mecanica
from app.services.cenefas.tinin_agent import _CONOCIMIENTO


# ---------------------------------------------------------------------------
# El texto no puede contradecir al motor
# ---------------------------------------------------------------------------

def test_el_combo_ensena_solo_la_cantidad():
    """tipoOferta de un combo es "2x", no el literal entero."""
    m, _ = resolver_mecanica("Combo", "2x$299", precio=175.0)
    assert m["tipoOferta"] == "2x"          # lo que el motor hace hoy
    assert m["precioOferta"] == 299.0       # el TOTAL
    assert m["promoOferta"] == ""           # vacía en combo

    # La frase vieja decía: Combo -> tipoOferta "2x$299".
    vieja = re.search(r'tipoOferta\s+"2x\$299"', _CONOCIMIENTO)
    assert vieja is None, (
        'el conocimiento sigue diciendo que en un combo tipoOferta lleva '
        '"2x$299" — el motor pone solo "2x"'
    )
    assert 'tipoOferta "2x"' in _CONOCIMIENTO, (
        "el conocimiento tiene que decir explícitamente que va solo la cantidad"
    )


def test_mxn_manda_el_literal_a_promo_oferta_y_no_a_precio_oferta():
    m, _ = resolver_mecanica("MxN", "2x1", precio=49.5)
    assert m["precioOferta"] == 49.5        # un NÚMERO, el de la columna PRECIO
    assert m["promoOferta"] == "2x1"        # el literal va acá
    assert m["tipoOferta"] == "2x1"

    assert "precioOferta también el literal" not in _CONOCIMIENTO, (
        "el conocimiento sigue diciendo que en M x N precioOferta lleva el "
        "literal — lleva el número; el literal va a promoOferta"
    )
    assert "promoOferta" in _CONOCIMIENTO, (
        "el conocimiento ni menciona promoOferta, que es donde va el literal"
    )


def test_precio_oferta_se_declara_siempre_como_precio():
    """La regla de fondo que evita las dos confusiones de arriba."""
    for ofertadet, oferta, precio in (
        ("Combo", "2x$299", 175.0),
        ("MxN", "2x1", 49.5),
        ("Unidad al", "2da unidad al 50%", 90.0),
        ("Precio Fijo", "Precio Oferta", 148.0),
    ):
        m, _ = resolver_mecanica(ofertadet, oferta, precio=precio)
        valor = m["precioOferta"]
        assert valor == "" or isinstance(valor, (int, float)), (
            f"{ofertadet}: precioOferta salió {valor!r} — tiene que ser un "
            f"número o vacío, nunca un literal"
        )

    assert "precioOferta ES UN PRECIO" in _CONOCIMIENTO, (
        "la regla de fondo tiene que estar escrita en el conocimiento"
    )


# ---------------------------------------------------------------------------
# Las mecánicas que Tinín nombra tienen que existir de verdad
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ofertadet,oferta,precio,esperado",
    [
        ("Combo",       "2x$299",            175.0, {"tipoOferta": "2x",         "precioOferta": 299.0}),
        ("Combo",       "3x99",              None,  {"tipoOferta": "3x",         "precioOferta": 99.0}),
        ("MxN",         "6x4",               120.0, {"tipoOferta": "6x4",        "promoOferta": "6x4"}),
        ("Unidad al",   "2da unidad al 50%", 90.0,  {"tipoOferta": "2da al 50%", "promoOferta": ""}),
        ("Precio Fijo", "Precio Oferta",     148.0, {"tipoOferta": "",           "mecanica": "Precio Final"}),
    ],
)
def test_los_ejemplos_del_conocimiento_dan_lo_que_dice(ofertadet, oferta, precio, esperado):
    m, _ = resolver_mecanica(ofertadet, oferta, precio=precio)
    for campo, valor in esperado.items():
        assert m[campo] == valor, f"{ofertadet}/{oferta}: {campo} dio {m[campo]!r}, se esperaba {valor!r}"
