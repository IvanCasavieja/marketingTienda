"""Fija el pase del símbolo de moneda tipeado ADENTRO de un cuadro compuesto a
<<unidadMoneda>> (20/09/2026), y las dos cosas que ese pase podía romper.

De dónde sale: el 17/09 se convirtieron los 41 cuadros cuyo texto entero era el
símbolo (`scripts/simbolo_a_variable.py`), y los compuestos quedaron afuera a
propósito. Quedaban 68 segmentos con el "$" tipeado en 15 plantillas, así que
un producto en dólares seguía imprimiendo "$" -- en el precio de oferta de
Rompe Precios A4, en los "PRECIO REGULAR: $" de Mega, en el "2x $ 299" de
Preciazos.

Lo que estos tests protegen, que es más que la conversión en sí:

1. **El símbolo no puede faltar.** Un cuadro con <<unidadMoneda>> imprime lo
   que diga la fila, y una fila sin esa columna imprimía el precio pelado. Ahora
   `process_row` garantiza "$" (pesos, el mismo default del Convertidor).
2. **Los espacios del diseño se conservan.** Un segmento es texto O variable,
   así que " $ " se parte en tres pedazos; si se perdieran los espacios,
   "3x $ 299" pasaría a "3x$299" en 24 cuadros.
3. **Las reglas siguen apuntando al mismo pedazo.** Apuntan por número de
   posición, y partir un segmento corre a los de atrás. En Congelados 3xA4 una
   regla de persona apunta a " unidad" (índice 2): sin renumerar pasaría a
   apuntar al precio regular y lo haría desaparecer de casi todos los carteles.
4. **Las dos guardas del motor siguen reconociendo al símbolo** aunque ahora
   esté a un espacio de distancia y sea una variable: la del símbolo duplicado
   ("$$899") y la del literal repetido a los dos lados del separador
   ("4x3 $ 4x3", caso Budweiser de Preciazos).
"""
import io
import sys
import pathlib

import openpyxl
from pptx import Presentation

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from app.services.cenefas.component_renderer import render_template_to_pptx
from app.services.cenefas.data_engine import load_products_from_bytes
from simbolo_en_segmento_a_variable import (  # noqa: E402
    convertir_componente,
    convertir_definicion,
)


# ---------------------------------------------------------------- utilidades


def _xlsx(*filas) -> bytes:
    """Un .xlsx en memoria, primera fila de encabezados (molde de
    test_division_stock_sucursal)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cenefas"
    for fila in filas:
        ws.append(list(fila))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cuadro(id_, segmentos, pt=40):
    """Un cuadro compuesto. `segmentos` son tuplas (tipo, valor)."""
    return {
        "id": id_, "type": "text", "name": id_, "visible": True,
        "base_bounds": {"x": 1.0, "y": 1.0, "width": 18.0, "height": 3.0},
        "style": {"font_size": pt, "align": "center"},
        "segments": [{"type": t, "value": v, "style": {"font_size": pt}} for t, v in segmentos],
    }


def _textos(pptx_bytes):
    prs = Presentation(io.BytesIO(pptx_bytes))
    return [sh.text_frame.text for sl in prs.slides for sh in sl.shapes
            if sh.has_text_frame and sh.text_frame.text.strip()]


def _render(componentes, fila, reglas=None):
    definicion = {
        "name": "t", "master_format": "a4", "formats": ["a4"],
        "components": componentes, "rules": reglas or [],
    }
    return _textos(render_template_to_pptx(definicion, [fila], "a4")[0])


# ------------------------------------- 1) el símbolo no puede faltar en la fila


def test_un_excel_sin_columna_de_moneda_igual_trae_el_simbolo():
    # El caso peligroso: un Excel cargado a mano, sin pasar por el Convertidor.
    # Antes del 20/09 la variable llegaba vacía y el cartel salía "149" pelado.
    productos = load_products_from_bytes(_xlsx(
        ("CODIGO", "DESCRIPCION", "PRECIO OFERTA"),
        ("123", "Cerveza PATRICIA 1L", "149,50"),
    ))
    assert productos[0]["unidadMoneda"] == "$"


def test_la_moneda_del_excel_gana_sobre_el_default():
    productos = load_products_from_bytes(_xlsx(
        ("CODIGO", "DESCRIPCION", "PRECIO OFERTA", "unidadMoneda"),
        ("123", "Vino", "149,50", "U$S"),
    ))
    assert productos[0]["unidadMoneda"] == "U$S"


# --------------------------------------- 2) los espacios del diseño se conservan


def test_el_simbolo_solo_se_convierte_y_los_espacios_quedan():
    comp, mapa, cambios = convertir_componente(_cuadro("c", [
        ("variable", "tipoOferta"), ("static", " $ "), ("variable", "promoOferta"),
    ]))
    assert [(s["type"], s["value"]) for s in comp["segments"]] == [
        ("variable", "tipoOferta"),
        ("static", " "),
        ("variable", "unidadMoneda"),
        ("static", " "),
        ("variable", "promoOferta"),
    ]
    assert cambios and mapa[1] == 2, "el mapa apunta al pedazo DEL SÍMBOLO"


def test_una_etiqueta_con_el_simbolo_al_final_se_parte_en_dos():
    comp, _, _ = convertir_componente(_cuadro("c", [
        ("static", "PRECIO REGULAR: $"), ("variable", "precioRegular"),
    ]))
    assert [(s["type"], s["value"]) for s in comp["segments"]] == [
        ("static", "PRECIO REGULAR: "),
        ("variable", "unidadMoneda"),
        ("variable", "precioRegular"),
    ]


def test_el_simbolo_en_el_medio_de_una_frase_no_se_toca():
    # "Llevá 2 y pagá $ menos" no se parte: adivinar dónde corta una frase no
    # es tarea del script. Queda para que lo mire una persona.
    original = _cuadro("c", [("static", "Llevá 2 y pagá $ menos"), ("variable", "precioOferta")])
    comp, mapa, cambios = convertir_componente(original)
    assert not cambios and not mapa and comp == original


def test_el_estilo_del_simbolo_lo_heredan_los_tres_pedazos():
    cuadro = _cuadro("c", [("variable", "tipoOferta"), ("static", " $ "), ("variable", "promoOferta")])
    cuadro["segments"][1]["style"] = {"font_size": 28.7, "color": "#ff0000"}
    cuadro["segments"][1]["_manual_font_override"] = True
    comp, _, _ = convertir_componente(cuadro)
    for seg in comp["segments"][1:4]:
        assert seg["style"] == {"font_size": 28.7, "color": "#ff0000"}
        assert seg["_manual_font_override"] is True


def test_convertir_dos_veces_no_cambia_nada():
    definicion = {"components": [_cuadro("c", [
        ("static", "PRECIO REGULAR: $"), ("variable", "precioRegular"),
    ])], "rules": []}
    una, detalle, _ = convertir_definicion(definicion)
    assert detalle
    otra, detalle2, _ = convertir_definicion(una)
    assert not detalle2 and otra["components"] == una["components"]


# ------------------------------------------- 3) las reglas no cambian de pedazo


def test_una_regla_de_persona_sigue_apuntando_a_su_segmento():
    # La geometría real de Rompe Precios Congelados 3xA4.
    regla = {
        "id": "r1", "name": 'Mostrar " unidad" si codigo contiene',
        "action": {"type": "show"},
        "condition": {"field": "codigo", "operator": "contains", "value": "-"},
        "target_component_id": "c", "target_segment_index": 2,
    }
    definicion = {"components": [_cuadro("c", [
        ("static", "PRECIO REGULAR: $"), ("variable", "precioRegular"), ("static", " unidad"),
    ])], "rules": [regla]}
    nueva, _, (personas, sistema) = convertir_definicion(definicion)
    assert (personas, sistema) == (1, 0)
    assert nueva["rules"][0]["target_segment_index"] == 3
    segs = nueva["components"][0]["segments"]
    assert segs[3]["value"] == " unidad", "la regla tiene que seguir apuntando a ' unidad'"


def test_las_reglas_fijas_vuelven_a_apuntar_al_simbolo():
    definicion = {"components": [_cuadro("c", [
        ("variable", "tipoOferta"), ("static", " $ "), ("variable", "promoOferta"),
    ])], "rules": []}
    nueva, _, _ = convertir_definicion(definicion)
    fijas = [r for r in nueva["rules"] if r.get("bloqueada")]
    assert len(fijas) == 2, "las dos reglas fijas del símbolo"
    assert {r["target_segment_index"] for r in fijas} == {2}
    assert nueva["components"][0]["segments"][2]["value"] == "unidadMoneda"


# --------------------------------- 4) las dos guardas reconocen al símbolo lejos


def test_el_literal_repetido_no_se_imprime_dos_veces_con_el_simbolo_en_medio():
    # Budweiser "4x3": el Convertidor copia el mismo literal en tipoOferta y en
    # promoOferta (familia mxn), y el diseño de Preciazos los dibuja con el
    # símbolo entre los dos. Antes del pase a variable el motor lo resolvía
    # comparando contra el estático pegado; ahora el símbolo está a un espacio.
    comp, _, _ = convertir_componente(_cuadro("c", [
        ("variable", "tipoOferta"), ("static", " $ "), ("variable", "promoOferta"),
    ]))
    salida = _render([comp], {"tipoOferta": "4x3", "promoOferta": "4x3", "unidadMoneda": "$"})
    assert salida == ["4x3"], f"el literal se imprimió dos veces: {salida!r}"


def test_un_combo_si_imprime_el_simbolo_y_el_total():
    comp, _, _ = convertir_componente(_cuadro("c", [
        ("variable", "tipoOferta"), ("static", " $ "), ("variable", "promoOferta"),
    ]))
    assert _render([comp], {"tipoOferta": "2x", "promoOferta": "299", "unidadMoneda": "$"}) == ["2x $ 299"]
    assert _render([comp], {"tipoOferta": "2x", "promoOferta": "299", "unidadMoneda": "U$S"}) == ["2x U$S 299"]


def test_no_queda_el_simbolo_duplicado_cuando_el_precio_ya_lo_trae():
    # Un Excel cargado a mano con "$899" en la columna del precio, en un cuadro
    # que además dibuja el símbolo. El motor saca la copia; con el símbolo como
    # variable y un espacio en el medio tiene que seguir haciéndolo.
    comp, _, _ = convertir_componente(_cuadro("c", [
        ("static", "$  "), ("variable", "precioBanco"),
    ]))
    assert [(s["type"], s["value"]) for s in comp["segments"]] == [
        ("variable", "unidadMoneda"), ("static", "  "), ("variable", "precioBanco"),
    ]
    salida = _render([comp], {"precioBanco": "$899", "unidadMoneda": "$"})
    assert salida == ["$  899"], f"quedó el símbolo duplicado: {salida!r}"
