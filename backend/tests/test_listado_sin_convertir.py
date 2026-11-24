"""El listado de gestión subido directo al generador de cenefas (24/11/2026).

Valentina subió "Listado - mailing diciembre" a Generar cenefas sin pasarlo
por el Convertidor: el generador entendía solo CODIGO y dibujó 1013 cenefas
con el código, el "$" y la vigencia. Ahora frena y dice qué hacer.
"""
import io

import openpyxl

from app.services.cenefas.data_engine import load_products_con_headers
from app.services.cenefas.revision_previa import listado_sin_convertir

GESTION = ["CODIGO", "SECCION", "NRO_OFERTA", "NOMBREARTICULO", "MONEDA", "PRECIOANT", "PRECIO",
           "COMENTARIOS", "COMPRADOR", "OFERTA", "OFERTADET", " DESCRIPCIONWEB"]


def _excel(encabezados, filas) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(encabezados)
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_el_listado_de_gestion_sin_convertir_se_frena_con_que_hacer():
    datos = _excel(GESTION, [
        ["97051", 21, 13627, ".BIZCOCHOS 12 UNS.", "$", 199, 199, "-", "PANADERIA", "0", "Precio fijo", ""],
        ["97042", 21, 13627, ".BIZCOCHOS FRIOPAN", "$", 239, 239, "-", "PANADERIA", "0", "Precio fijo", ""],
    ])
    productos, headers = load_products_con_headers(datos, "1/12/26 al 6/1/27")
    # Lo que pasaba: solo el código (y lo que viene fijo).
    assert [p.get("codigo") for p in productos] == ["97051", "97042"]
    assert not any(p.get("descripcion") or p.get("precioOferta") for p in productos)
    motivo = listado_sin_convertir(headers, productos)
    assert motivo and "Convertidor de Excel" in motivo and "las 2 cenefas" in motivo


def test_el_excel_del_convertidor_pasa():
    datos = _excel(["codigo", "descripcion", "precioOferta", "decimalPrecioOferta"],
                   [["97051", "Bizcochos x12", "199", ""]])
    productos, headers = load_products_con_headers(datos, "")
    assert listado_sin_convertir(headers, productos) is None


def test_si_algo_se_entiende_no_se_frena():
    # Un Excel armado a mano que trae alguna columna de gestión pero ya tiene
    # la descripción: la revisión de siempre avisa lo que falte, no se frena.
    datos = _excel(["codigo", "descripcion", "NOMBREARTICULO", "PRECIO"],
                   [["97051", "Bizcochos x12", ".BIZCOCHOS", 199]])
    productos, headers = load_products_con_headers(datos, "")
    assert listado_sin_convertir(headers, productos) is None


def test_sin_productos_nada():
    assert listado_sin_convertir(GESTION, []) is None
