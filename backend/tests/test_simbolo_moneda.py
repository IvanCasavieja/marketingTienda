"""Fija que el símbolo de moneda no cambie de tamaño por culpa de otro cuadro.

Bug real (Red Expres 17 A4, 11/09/2026): en un PPTX de 264 hojas el "$" salía
a 128 pt en los combos y a 166 pt en precio fijo, siempre en la misma caja. El
achique automático lo medía contra la CAJA declarada del precio de al lado:
en un combo <<promoOferta>> tiene texto y su caja arranca adentro de la franja
del "$", así que el motor veía 2,97 cm libres y lo bajaba, aunque el texto
real del "$" y el del "50" quedaban a 1,8 cm uno del otro.

Criterio de Ivan: el achique automático es para que el contenido de un cuadro
entre en ESE cuadro, no para achicar un cuadro distinto. Si el número de
verdad toca al símbolo, el que cede es el número.

La geometría es la de la plantilla real.
"""
from app.services.cenefas.component_renderer import _fit_text_to_box

ANCHO_HOJA_A4 = 21.0


def _cuadro(id_, variable, x, y, w, h, pt, segmentado=False):
    c = {
        "id": id_, "type": "text", "name": variable,
        "base_bounds": {"x": x, "y": y, "width": w, "height": h},
        "style": {"font_size": pt, "align": "center"},
    }
    if segmentado:
        c["segments"] = [{"type": "variable", "value": variable,
                          "style": {"font_size": pt}}]
    else:
        c["variable"] = variable
    return c


def _plantilla():
    return [
        _cuadro("tipo",   "tipoOferta",   4.04, 6.71, 12.897, 4.014, 90),
        _cuadro("precio", "precioOferta", 0.0,  9.14, 21.0,   7.352, 180),
        _cuadro("promo",  "promoOferta",  4.11, 9.10, 12.75,  7.44,  180),
        # El símbolo es un <<unidadMoneda>> segmentado, como lo deja el importer.
        _cuadro("moneda", "unidadMoneda", 0.64, 10.6, 6.82,   5.57,  166, segmentado=True),
    ]


COMBO = {"unidadMoneda": "$", "precioOferta": "25", "promoOferta": "50", "tipoOferta": "2x"}
PRECIO_FIJO = {"unidadMoneda": "$", "precioOferta": "129", "promoOferta": "", "tipoOferta": ""}
DOLARES = {"unidadMoneda": "U$S", "precioOferta": "129", "promoOferta": "", "tipoOferta": ""}


def _pt_moneda(comps, producto):
    ajustados = _fit_text_to_box(comps, producto, ANCHO_HOJA_A4)
    return next(c for c in ajustados if c["id"] == "moneda")["style"]["font_size"]


def test_el_simbolo_sale_igual_en_combo_y_en_precio_fijo():
    # En la misma plantilla, el "$" no puede cambiar de tamaño según la mecánica.
    assert _pt_moneda(_plantilla(), COMBO) == _pt_moneda(_plantilla(), PRECIO_FIJO)


def test_el_simbolo_que_entra_en_su_caja_no_se_achica():
    # El "$" entra de sobra en sus 6,82 cm: tiene que quedar con el tamaño del diseño.
    assert _pt_moneda(_plantilla(), COMBO) == 166
    assert _pt_moneda(_plantilla(), PRECIO_FIJO) == 166


def test_el_tamano_del_simbolo_no_depende_de_los_vecinos():
    # La prueba directa del criterio: medido solo o rodeado de los otros
    # cuadros, el símbolo tiene que dar lo mismo, para cualquier producto.
    solo = [c for c in _plantilla() if c["id"] == "moneda"]
    for producto in (COMBO, PRECIO_FIJO, DOLARES):
        assert _pt_moneda(_plantilla(), producto) == _pt_moneda(solo, producto), producto


def test_u_s_se_achica_solo_si_no_entra_en_su_propia_caja():
    # "U$S" es más ancho: si se achica, es porque su contenido no entra en su
    # caja, y nunca por encima del tamaño del diseño.
    assert _pt_moneda(_plantilla(), DOLARES) <= 166
