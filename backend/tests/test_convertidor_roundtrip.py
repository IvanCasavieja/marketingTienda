"""La salida del Convertidor tiene que poder volver a entrar sin perder nada.

El Convertidor está pensado para leer el export CRUDO de gestión y calcular
las variables. Pero su propia salida se vuelve a subir todo el tiempo --se
corrige una descripción, se unifican categorías, se guarda y se sube de
nuevo-- y ahí el archivo ya trae las variables resueltas.

Hasta el 08/09/2026, de las 13 columnas de un archivo ya convertido entraban
4. Los cuatro decimales, `mecanica` y `unidadMoneda` se perdían en silencio, y
los decimales ni siquiera se podían mapear a mano (no están en
VARIABLES_MAPEABLES). Se veía como "no me toma el decimal".
"""
from app.services.cenefas.convertidor_variables import construir_variables
from app.services.cenefas.variables import resolve


# Una fila cruda mínima, como sale de parse_input_excel.
CRUDA = {
    "codigo": "580735", "nombreArticulo": "ALMENDRAS FOREST",
    "moneda": "$", "precioAnterior": 429.0, "precio": 321.75,
    "oferta": "25% off", "ofertaDet": "% descuento",
    "descripcionWeb": "", "descripcionExcel": "", "comprador": "",
}


def _construir(mapeo):
    variables, _warnings = construir_variables(CRUDA, "Almendras FOREST FEAST. 120 g", mapeo)
    return variables


# ---------------------------------------------------------------------------
# Los encabezados de un archivo ya convertido se reconocen como variables
# ---------------------------------------------------------------------------

def test_los_encabezados_del_archivo_convertido_son_variables_canonicas():
    # Es la condición que dispara el auto-mapeo en parse_input_excel: si el
    # encabezado resuelve a una variable, su valor entra tal cual.
    columnas = ["codigo", "descripcion", "mecanica", "unidadMoneda",
                "precioRegular", "decimalPrecioRegular", "precioOferta",
                "decimalPrecioOferta", "ofertaUno", "decimalPrecioUno",
                "precioBanco", "decimalPrecioBanco", "banco"]
    for col in columnas:
        assert resolve(col) == col, col


# ---------------------------------------------------------------------------
# El decimal, que es lo que se perdía
# ---------------------------------------------------------------------------

def test_el_decimal_viene_de_su_columna_cuando_esta():
    # "321" + ",75" en columnas separadas. Derivando el decimal de "321" da
    # vacío: los centavos se perdían en cada ida y vuelta.
    v = _construir({"precioOferta": "321", "decimalPrecioOferta": ",75"})
    assert v["precioOferta"] == "321"
    assert v["decimalPrecioOferta"] == ",75"


def test_todos_los_decimales_entran_por_su_columna():
    v = _construir({
        "precioRegular": "429", "decimalPrecioRegular": ",10",
        "precioOferta":  "321", "decimalPrecioOferta":  ",75",
        "precioBanco":   "273", "decimalPrecioBanco":   ",49",
        "ofertaUno":     "25",  "decimalPrecioUno":     ",30",
    })
    assert (v["decimalPrecioRegular"], v["decimalPrecioOferta"],
            v["decimalPrecioBanco"], v["decimalPrecioUno"]) == (",10", ",75", ",49", ",30")


def test_sin_columna_de_decimal_se_sigue_derivando_del_precio():
    # El comportamiento de siempre, intacto: un export crudo no trae la
    # columna del decimal y el centavo sale de partir el precio.
    v = _construir({"precioOferta": "321,75"})
    assert v["precioOferta"] == "321"
    assert v["decimalPrecioOferta"] == ",75"


def test_una_columna_de_decimal_vacia_no_pisa_al_derivado():
    # El archivo trae la columna pero esa fila no tiene centavos: vale lo que
    # se derive del precio, no un vacío impuesto.
    v = _construir({"precioOferta": "321,75", "decimalPrecioOferta": ""})
    assert v["decimalPrecioOferta"] == ",75"


# ---------------------------------------------------------------------------
# Los textos que antes no tenían por dónde entrar
# ---------------------------------------------------------------------------

def test_la_mecanica_del_archivo_gana_sobre_la_calculada():
    # Un archivo ya convertido trae la mecánica redactada; recalcularla desde
    # OFERTA/OFERTADET es rehacer trabajo que ya estaba hecho y aprobado.
    v = _construir({"mecanica": "Comprando 2, $149,50 la unidad."})
    assert v["mecanica"] == "Comprando 2, $149,50 la unidad."


def test_la_moneda_del_archivo_gana():
    v = _construir({"unidadMoneda": "U$S"})
    assert v["unidadMoneda"] == "U$S"


def test_sin_columna_la_mecanica_se_sigue_calculando():
    # Export crudo: nada de esto cambia.
    v = _construir({})
    assert v["mecanica"] == "Precio Final"
    assert v["unidadMoneda"] == "$"


def test_el_codigo_combinado_de_un_grupo_unificado_sobrevive():
    # Una fila ya unificada vuelve a entrar con su código combinado entero.
    v = _construir({"precioOferta": "321", "decimalPrecioOferta": ",75"})
    assert v["codigo"] == "580735"
    otra = dict(CRUDA, codigo="580735 - 590183 - 595335")
    variables, _ = construir_variables(otra, "Almendras", {})
    assert variables["codigo"] == "580735 - 590183 - 595335"
