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
    assert m["precioOferta"] == 175.0       # el REAL de la columna PRECIO (2026-09-04)
    assert m["promoOferta"] == 299.0        # el TOTAL, ahora en promoOferta

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
    assert m["tipoOferta"] == ""            # y la cocarda queda vacía (16/09/2026)

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
        ("Combo",       "2x$299",            175.0, {"tipoOferta": "2x",         "precioOferta": 175.0, "promoOferta": 299.0}),
        ("Combo",       "3x99",              None,  {"tipoOferta": "3x",         "promoOferta": 99.0}),
        ("MxN",         "6x4",               120.0, {"tipoOferta": "",           "promoOferta": "6x4"}),
        ("Unidad al",   "2da unidad al 50%", 90.0,  {"tipoOferta": "2da al 50%", "promoOferta": ""}),
        ("Precio Fijo", "Precio Oferta",     148.0, {"tipoOferta": "",           "mecanica": "Precio Final"}),
    ],
)
def test_los_ejemplos_del_conocimiento_dan_lo_que_dice(ofertadet, oferta, precio, esperado):
    m, _ = resolver_mecanica(ofertadet, oferta, precio=precio)
    for campo, valor in esperado.items():
        assert m[campo] == valor, f"{ofertadet}/{oferta}: {campo} dio {m[campo]!r}, se esperaba {valor!r}"


# ---------------------------------------------------------------------------
# El orden de la descripción: producto, marca, variedad, gramaje (Ivan, 2026-10-06)
# ---------------------------------------------------------------------------

def test_el_orden_de_la_descripcion_es_producto_marca_variedad_gramaje():
    """Ivan fijó el orden el 2026-10-06 con un ejemplo: "Vino Tienda inglesa
    blanco. 500ml" (el gramaje se escribe "500 ml", con espacio, como en las
    448 descripciones que aprobó el 29/09 para la Fiesta Alemania fase 2), y
    esa misma tarde sumó el punto después de la marca, con la variedad
    arrancando en mayúscula: "Vino TIENDA INGLESA. Blanco. 500 ml". Tiene que estar escrito, con el orden enunciado y no solo
    ejemplificado, en las reglas que ve el modelo cuando genera (_STYLE_RULES,
    que comparten las descripciones sueltas y las de grupos unificados) y en
    lo que Tinín explica. Y los ejemplos viejos con la variedad delante de la
    marca no pueden seguir ahí, porque contradicen la regla."""
    from app.services.cenefas.convertidor_ai import _STYLE_RULES, _SYSTEM_PROMPT, _UNIFY_SYSTEM_PROMPT

    assert _STYLE_RULES in _SYSTEM_PROMPT and _STYLE_RULES in _UNIFY_SYSTEM_PROMPT, (
        "las reglas de estilo tienen que llegar a los dos generadores"
    )

    ejemplo = "Vino TIENDA INGLESA. Blanco. 500 ml"
    orden = re.compile(r"producto.*marca.*variedad.*gramaje", re.IGNORECASE)
    for texto, donde in ((_STYLE_RULES, "_STYLE_RULES"), (_CONOCIMIENTO, "_CONOCIMIENTO")):
        assert ejemplo in texto, f"{donde} no trae el ejemplo del orden"
        # El punto y el gramaje no son opcionales, y van como en las 448
        # descripciones que Ivan aprobó el 29/09/2026 (Fiesta Alemania fase 2):
        # espacio entre número y unidad, el envase después del punto.
        assert "Lata 500 ml" in texto and "x 12" in texto, (
            f"{donde} perdió las formas del documento aprobado (\"Lata 500 ml\", \"x 12\")")
        # Después de la marca va punto y la variedad arranca con mayúscula
        # (Ivan, 06/10/2026, tercera vuelta): ningún ejemplo vigente puede
        # traer la variedad pegada a la marca.
        assert "CLAUSTHALER. Pomelo." in texto, f"{donde} no trae el punto después de la marca"
        assert "CLAUSTHALER pomelo" not in texto, f"{donde} sigue con la variedad pegada a la marca"
        assert any(orden.search(linea) for linea in texto.splitlines()), (
            f"{donde} no enuncia el orden producto, marca, variedad, gramaje en una misma línea"
        )
        for viejo in (
            "Aceite alto oleico CAÑUELAS",
            "Yogur natural YOGURISIMO",
            "Panceta ahumada VILLA MARGARITA",
            "Morcilla dulce DON JOAQUIN",
        ):
            assert viejo not in texto, f"{donde} sigue con la variedad delante de la marca: {viejo!r}"
    assert "NO SON OPCIONALES" in _STYLE_RULES, "el punto y el gramaje tienen que estar declarados obligatorios"
    assert '"Vino TIENDA INGLESA blanco"' not in _STYLE_RULES, (
        "un ejemplo sin gramaje ni punto le enseña al modelo a omitirlos (pasó el 06/10/2026)")


# ---------------------------------------------------------------------------
# Las variedades: con "o", y más de tres son "Distintas variedades" (Ivan, 2026-10-08)
# ---------------------------------------------------------------------------

def test_las_variedades_van_con_o_y_mas_de_tres_son_distintas_variedades():
    """Dos reglas que Ivan fijó el 08/10/2026 mirando el PPTX de marca propia.

    Entre variedades va "o", nunca "y": "Naranja, frutilla o coco". Con "y" la
    gente entiende que la promo es por llevarse las tres juntas, cuando la
    oferta es por una U otra. Y hasta tres variedades se nombran; con más de
    tres no se enumera ninguna: va "Distintas variedades" en su lugar.

    Tienen que estar en las reglas que ve el modelo (_STYLE_RULES, que llegan
    a las descripciones sueltas y a los grupos) y en lo que Tinín explica. Y
    el ejemplo del unificador no puede seguir enseñando lo contrario: hasta
    ese día decía "Chocolate, tradicional y vainilla"."""
    from app.services.cenefas.convertidor_ai import _STYLE_RULES, _UNIFY_SYSTEM_PROMPT

    for texto, donde in ((_STYLE_RULES, "_STYLE_RULES"), (_CONOCIMIENTO, "_CONOCIMIENTO")):
        assert "Naranja, frutilla o coco" in texto, f"{donde} no trae el ejemplo con \"o\""
        assert re.search(r'nunca con "y"', texto, re.IGNORECASE), f"{donde} no prohíbe la \"y\" entre variedades"
        assert "Distintas variedades" in texto, f"{donde} no trae \"Distintas variedades\""
        assert re.search(r"m[áa]s de tres", texto, re.IGNORECASE), f"{donde} no dice desde cuántas se deja de enumerar"

    for texto, donde in ((_UNIFY_SYSTEM_PROMPT, "_UNIFY_SYSTEM_PROMPT"), (_CONOCIMIENTO, "_CONOCIMIENTO")):
        assert "tradicional y vainilla" not in texto, f"{donde} sigue con el ejemplo que une variedades con \"y\""
        assert "tradicional o vainilla" in texto, f"{donde} perdió el ejemplo del unificador con \"o\""
    assert "Distintas variedades" in _UNIFY_SYSTEM_PROMPT, "la opción neutra del unificador tiene que decir exactamente eso"
    assert "En 3 variedades" not in _UNIFY_SYSTEM_PROMPT and "Variedades surtidas" not in _UNIFY_SYSTEM_PROMPT, (
        "la frase neutra la fijó Ivan: \"Distintas variedades\", no otras formas")


# ---------------------------------------------------------------------------
# Marca TIENDA INGLESA / TIENDA CASA, gramaje sin cantidad y unidad con espacio (Ivan, 2026-10-08)
# ---------------------------------------------------------------------------

def test_marca_tienda_inglesa_tienda_casa_gramaje_sin_cantidad_y_unidad_con_espacio():
    """Segunda tanda del 08/10/2026, mirando el PPTX de marca propia:

    - "TI"/"IT" en el nombre de gestión es la marca TIENDA INGLESA, escrita entera.
    - TIENDA CASA es marca propia de Tienda Inglesa y se escribe TIENDA CASA; en
      bowls, platos y tazas había quedado el código del proveedor ("RAYLON").
    - Con el gramaje del pack no va la cantidad: "485 g", no "485 g x 8".
    - La unidad va SIEMPRE con espacio, también en los de corte: "100 g". Hasta
      ese día la regla pedía "100g" pegado."""
    from app.services.cenefas.convertidor_ai import _STYLE_RULES

    for texto, donde in ((_STYLE_RULES, "_STYLE_RULES"), (_CONOCIMIENTO, "_CONOCIMIENTO")):
        assert re.search(r'"TI".{0,400}TIENDA INGLESA', texto), f"{donde} no dice que TI es TIENDA INGLESA"
        assert "TIENDA CASA" in texto and "RAYLON" in texto, f"{donde} no explica TIENDA CASA (ni el caso RAYLON)"
        assert "485 g x 8" in texto and "Frankfurters TIENDA INGLESA. 485 g" in texto, (
            f"{donde} no trae el ejemplo del pack sin cantidad")
        assert '"100 g"' in texto, f"{donde} no escribe la unidad de corte con espacio"
        assert "NATURALACT. 100g" not in texto, f"{donde} sigue con el ejemplo de 100g pegado"
    assert 'exactamente "100 g" o "Kg"' in _STYLE_RULES
    assert '"150g", "100g" o "1kg" están MAL' in _STYLE_RULES


# ---------------------------------------------------------------------------
# MH = MEAT HOUSE (Ivan, 2026-10-08)
# ---------------------------------------------------------------------------

def test_mh_es_la_marca_meat_house_y_se_escribe_entera():
    """Tercera tanda del 08/10/2026, mirando las sugerencias de "Otros
    productos": "Asado corte inglés MH. Kg". "MH" de gestión es MEAT HOUSE, la
    marca exclusiva de carnes de Tienda Inglesa (y a la vez propia); va entera
    como cualquier marca y esos productos llevan sus propias cenefas."""
    from app.services.cenefas.convertidor_ai import _STYLE_RULES

    for texto, donde in ((_STYLE_RULES, "_STYLE_RULES"), (_CONOCIMIENTO, "_CONOCIMIENTO")):
        assert re.search(r'"MH".{0,80}MEAT HOUSE', texto), f"{donde} no dice que MH es MEAT HOUSE"
        assert "Colita de cuadril MEAT HOUSE. Kg" in texto, f"{donde} no trae el ejemplo escrito entero"
        assert "Lomo MH. Kg" in texto, f"{donde} no muestra la sigla como el caso malo"
        assert "exclusiva" in texto.split("MEAT HOUSE", 1)[1][:200], f"{donde} no dice que es marca exclusiva"
    assert "propias cenefas" in _CONOCIMIENTO


def test_la_sigla_mh_se_expande_en_codigo_no_solo_en_el_prompt():
    """La regla escrita es probabilística; la expansión es determinística: en el
    nombre que ve el modelo y en lo que devuelve."""
    from app.services.cenefas.convertidor_ai import _build_prompt, expandir_siglas_de_marca

    assert expandir_siglas_de_marca("COLITA DE CUADRIL  MH") == "COLITA DE CUADRIL  MEAT HOUSE"
    assert expandir_siglas_de_marca("Lomo MH. Kg") == "Lomo MEAT HOUSE. Kg"
    assert expandir_siglas_de_marca("MH ENTRAÑA") == "MEAT HOUSE ENTRAÑA"
    assert expandir_siglas_de_marca("PARLANTE 40 MHZ") == "PARLANTE 40 MHZ"   # pegada a otras letras, no es la sigla
    assert expandir_siglas_de_marca("") == ""
    prompt = _build_prompt([{"row_id": 1, "codigo": "22145", "nombreArticulo": "LOMO MH", "descripcionWeb": ""}])
    assert 'nombre ERP: "LOMO MEAT HOUSE"' in prompt and " MH" not in prompt


# ---------------------------------------------------------------------------
# TIENDA CASA por familia (Ivan y Ana, 2026-10-08)
# ---------------------------------------------------------------------------

def test_la_familia_decide_entre_tienda_inglesa_y_tienda_casa():
    """Gestión escribe "TI" para las dos marcas propias; 15 papeleras, alfombras,
    felpudos y lámparas salieron como TIENDA INGLESA por aplicar "TI = TIENDA
    INGLESA" sin mirar la familia. Ahora el comprador viaja con la fila, el
    prompt lo marca y la salida se corrige en código."""
    from app.services.cenefas.convertidor_ai import (
        _STYLE_RULES, _build_prompt, es_familia_tienda_casa, marca_propia_por_familia,
    )

    for texto, donde in ((_STYLE_RULES, "_STYLE_RULES"), (_CONOCIMIENTO, "_CONOCIMIENTO")):
        assert "Papelera TIENDA CASA. 12 L" in texto, f"{donde} sigue con la papelera como TIENDA INGLESA"
        assert "Papelera TIENDA INGLESA. 12 L" not in texto.replace('no "Papelera TIENDA INGLESA"', ""), f"{donde} muestra la papelera como TIENDA INGLESA"
        assert "Cuadernola tapa dura TIENDA INGLESA" in texto, f"{donde} no deja la papelería como TIENDA INGLESA"
    assert es_familia_tienda_casa("DECORACION") and es_familia_tienda_casa("BAZAR") and es_familia_tienda_casa("TEXTILES")
    assert es_familia_tienda_casa("Decoración") and not es_familia_tienda_casa("LIBROS Y PAPELERIA") and not es_familia_tienda_casa("")
    assert marca_propia_por_familia("Papelera TIENDA INGLESA. 12 L", "DECORACION") == "Papelera TIENDA CASA. 12 L"
    assert marca_propia_por_familia("Cuadernola TIENDA INGLESA. 100 hojas", "LIBROS Y PAPELERIA") == "Cuadernola TIENDA INGLESA. 100 hojas"
    assert marca_propia_por_familia("Bowl TIENDA CASA. 18 cm", "BAZAR") == "Bowl TIENDA CASA. 18 cm"
    prompt = _build_prompt([{"row_id": 1, "codigo": "597792", "nombreArticulo": "PAPELERA TI 12L", "descripcionWeb": "", "comprador": "DECORACION"}])
    assert "[BAZAR, DECORACIÓN O TEXTIL" in prompt
    prompt = _build_prompt([{"row_id": 1, "codigo": "598729", "nombreArticulo": "CUADERNOLA TI", "descripcionWeb": "", "comprador": "LIBROS Y PAPELERIA"}])
    assert "[BAZAR" not in prompt

