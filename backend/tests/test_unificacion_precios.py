"""Fija cómo ve Tinín los precios al unificar categorías.

Un grupo unificado imprime UN cartel para varios SKU: una descripción y un
precio. Si dos miembros no están al mismo precio, ese cartel miente para
alguno. La decisión es de Tinín -- acá se fija que le llegue lo que necesita
para tomarla bien.

El punto fino: en toda la plataforma el precio viaja partido en dos columnas
(entero y decimal). Mostrado así, $276,75 y $276 se leen iguales mirando la
columna entera, que es justo el falso positivo que se quiere evitar. Por eso
el precio se arma ENTERO antes de pasárselo.
"""
from app.services.cenefas.convertidor_ai import (
    _UNIFY_SYSTEM_PROMPT,
    _build_unify_prompt,
    _linea_precios,
    _monto,
)


# ---------------------------------------------------------------------------
# El precio armado a partir de sus dos columnas
# ---------------------------------------------------------------------------

def test_el_decimal_se_escribe_siempre():
    # Si no se escribe, no se puede ver la diferencia: es la que separa a
    # $276,75 de $276.
    assert _monto("276", ",75") == "276,75"
    assert _monto("276", "") == "276,00"
    assert _monto("276", ",75") != _monto("276", "")


def test_el_punto_de_la_columna_entera_es_separador_de_miles():
    # 1.124 son mil ciento veinticuatro. Se conserva tal cual, que es como lo
    # lee una persona.
    assert _monto("1.124", ",50") == "1.124,50"
    assert _monto("1.124", "") == "1.124,00"


def test_un_decimal_de_un_digito_se_completa():
    # ",5" son cincuenta centavos, no cinco.
    assert _monto("276", ",5") == "276,50"


def test_lo_que_no_es_un_precio_pasa_tal_cual():
    # Una mecánica escrita en la celda no es un precio, pero es lo que hay en
    # esa fila y Tinín tiene que verlo igual.
    assert _monto("2x1", "") == "2x1"


def test_sin_precio_no_inventa_un_cero():
    assert _monto("", "") == ""
    assert _monto(None, None) == ""


# ---------------------------------------------------------------------------
# La línea que efectivamente lee Tinín
# ---------------------------------------------------------------------------

def _fila(**extra):
    base = {
        "row_id": 1, "codigo": "1001", "nombreArticulo": "SALSA TIPTREE KETCHUP",
        "descripcion": "", "unidadMoneda": "$",
        "precioRegular": "369", "decimalPrecioRegular": "",
        "precioOferta": "276", "decimalPrecioOferta": ",75",
        "precioBanco": "235", "decimalPrecioBanco": ",24",
        "ofertaUno": "", "decimalPrecioUno": "", "mecanica": "", "banco": "",
    }
    base.update(extra)
    return base


def test_la_linea_trae_los_tres_precios_con_su_moneda():
    linea = _linea_precios(_fila())
    assert "regular $369,00" in linea
    assert "oferta $276,75" in linea
    assert "banco $235,24" in linea


def test_no_arrastra_campos_vacios():
    # Una fila sin precio de banco no tiene por qué gastar lugar en el prompt
    # diciendo que no lo tiene.
    linea = _linea_precios(_fila(precioBanco="", decimalPrecioBanco=""))
    assert "banco" not in linea
    assert "oferta $276,75" in linea


def test_la_linea_trae_las_condiciones_que_cambian_el_cartel():
    linea = _linea_precios(_fila(ofertaUno="25", banco="Scotiabank",
                                 mecanica="2da unidad al 50%."))
    assert "% off: 25" in linea
    assert "banco: Scotiabank" in linea
    assert "mecánica: 2da unidad al 50%." in linea


def test_dolares_se_ven_como_dolares():
    assert "U$S" in _linea_precios(_fila(unidadMoneda="U$S"))


def test_el_prompt_le_muestra_el_precio_de_cada_producto():
    # Sin esto Tinin agrupa a ciegas: hasta 09/2026 solo recibia el nombre.
    prompt = _build_unify_prompt([
        _fila(),
        _fila(row_id=2, codigo="1002", nombreArticulo="SALSA TIPTREE BROWN",
              precioRegular="299", decimalPrecioRegular=""),
    ])
    assert "SALSA TIPTREE KETCHUP" in prompt
    assert "regular $369,00" in prompt
    assert "regular $299,00" in prompt


def test_la_regla_del_precio_esta_en_las_instrucciones():
    # La decision es de Tinin, asi que la regla tiene que estar escrita donde
    # la lee, no en un filtro posterior.
    assert "$276,75 NO es $276" in _UNIFY_SYSTEM_PROMPT
    assert "centavos" in _UNIFY_SYSTEM_PROMPT
