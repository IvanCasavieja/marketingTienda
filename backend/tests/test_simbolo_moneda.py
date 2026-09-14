"""Fija que ningún cuadro cambie de tamaño si no lo dice una regla.

Bug real que originó este módulo (Red Expres 17 A4, 11/09/2026): en un PPTX de
264 hojas el "$" salía a 128 pt en los combos y a 166 pt en precio fijo,
siempre en la misma caja. El achique automático lo medía contra la CAJA
declarada del precio de al lado: en un combo <<promoOferta>> tiene texto y su
caja arranca adentro de la franja del "$", así que el motor veía 2,97 cm libres
y lo bajaba, aunque el texto real del "$" y el del "50" quedaban a 1,8 cm uno
del otro.

Criterio de Ivan, y la razón por la que el achique automático se eliminó
entero el 14/09/2026: el tamaño lo decide una persona, no una medición. Lo que
antes había que garantizar caso por caso --que un vecino no te achique el
símbolo-- ahora es estructural: NADA achica nada. Estos tests fijan eso, que es
la garantía fuerte, y de paso siguen cubriendo la geometría real de la
plantilla que destapó el bug.
"""
from app.services.cenefas.component_renderer import preparar_componentes

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
# "1.599" desborda su caja a 180 pt. Antes esto disparaba el achique; ahora no
# dispara nada, que es exactamente lo que se quiere fijar.
DESBORDA = {"unidadMoneda": "$", "precioOferta": "1.599", "promoOferta": "", "tipoOferta": ""}


def _pt(comps, producto, id_, reglas=()):
    preparados = preparar_componentes(comps, list(reglas), producto)
    return next(c for c in preparados if c["id"] == id_)["style"]["font_size"]


def test_el_simbolo_sale_igual_en_combo_y_en_precio_fijo():
    # El caso original: en la misma plantilla el "$" no puede cambiar de tamaño
    # según la mecánica del producto.
    assert _pt(_plantilla(), COMBO, "moneda") == _pt(_plantilla(), PRECIO_FIJO, "moneda")


def test_sin_reglas_todos_los_cuadros_salen_con_el_cuerpo_del_diseno():
    # La garantía fuerte: sin una regla que diga otra cosa, lo que puso el
    # diseñador es lo que se imprime, para CUALQUIER producto -- incluido uno
    # cuyo texto no entra en la caja.
    for producto in (COMBO, PRECIO_FIJO, DOLARES, DESBORDA):
        preparados = preparar_componentes(_plantilla(), [], producto)
        assert [c["style"]["font_size"] for c in preparados] == [90, 180, 180, 166], producto


def test_un_texto_que_desborda_ya_no_achica_nada():
    # "1.599" a 180 pt no entra en su caja. Antes bajaba solo (y de paso
    # arrastraba a sus vecinos); ahora desborda visiblemente y se avisa por
    # separado -- ver detectar_solapes. Que se note es lo buscado: el desborde
    # se arregla poniéndole una regla, no tapándolo con un achique silencioso.
    assert _pt(_plantilla(), DESBORDA, "precio") == 180


def test_una_regla_toca_su_cuadro_y_ninguno_mas():
    # El precio baja porque lo dice la regla; el símbolo de al lado, que es
    # justo lo que el motor viejo achicaba de rebote, no se entera.
    regla = [{
        "id": "r1", "target_component_id": "precio",
        "condition": {"field": "precioOferta", "operator": "length_greater_than", "value": 3},
        "action": {"type": "set_font_size", "value": 120},
    }]
    assert _pt(_plantilla(), DESBORDA, "precio", regla) == 120
    assert _pt(_plantilla(), DESBORDA, "moneda", regla) == 166
    # Y un producto que no matchea la condición sale con el cuerpo del diseño.
    assert _pt(_plantilla(), PRECIO_FIJO, "precio", regla) == 180
