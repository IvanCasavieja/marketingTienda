"""Dos bugs reales del export de Rompe Precios Congelados A4 (11/09/2026).

1. La imagen roja de Club Card vive DENTRO de un grupo junto con el precio. Al
   exportar, el motor la reemplazaba y la pegaba al final de la hoja: quedaba
   encima de todo y tapaba el precio, el decimal y "unidad". En el archivo los
   textos estaban, pero no se veían.
2. Los tamaños puestos a mano en los segmentos del precio grande ("$" a 102,
   número a 160) no se respetaban: como la CAJA no tenía tamaño manual, el
   motor los achicaba contra los cuadros vecinos y el alto, hasta el mínimo.

Criterio de Ivan: lo que se pone a mano manda donde se pone, y solo baja si no
entra en su propia caja.
"""
import io

from PIL import Image
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Cm, Emu, Pt

from app.services.cenefas.component_renderer import _fit_text_to_box, render_template_to_pptx
from app.services.cenefas.pptx_importer import import_pptx

ANCHO_HOJA_A4 = 21.0


# ---------------------------------------------------------------------------
# 1. Imagen dentro de un grupo
# ---------------------------------------------------------------------------

def _png():
    buf = io.BytesIO()
    Image.new("RGB", (60, 20), (220, 30, 40)).save(buf, "PNG")
    return buf.getvalue()


def _pptx_con_grupo():
    prs = Presentation()
    prs.slide_width = Cm(21.0)
    prs.slide_height = Cm(29.7)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    grupo = slide.shapes.add_group_shape()
    grupo.shapes.add_picture(io.BytesIO(_png()), Cm(13), Cm(20), Cm(6), Cm(2.4))
    precio = grupo.shapes.add_textbox(Cm(15), Cm(20.2), Cm(3.5), Cm(2))
    run = precio.text_frame.paragraphs[0].add_run()
    run.text = "<<precioBanco>>"
    run.font.size = Pt(30)
    unidad = slide.shapes.add_textbox(Cm(15), Cm(21.5), Cm(3.5), Cm(1))
    run = unidad.text_frame.paragraphs[0].add_run()
    run.text = "unidad"
    run.font.size = Pt(20)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _hoja_exportada():
    src = _pptx_con_grupo()
    pptx, _ = render_template_to_pptx(import_pptx(src), [{"precioBanco": "186"}], "a4", None, src)
    return Presentation(io.BytesIO(pptx)).slides[0]


def test_la_imagen_de_un_grupo_no_queda_arriba_de_todo():
    slide = _hoja_exportada()
    dibujados = [el for el in slide.shapes._spTree if el.tag in (qn("p:sp"), qn("p:pic"), qn("p:grpSp"))]
    # Lo último que se dibuja sigue siendo el texto "unidad", no una imagen suelta.
    assert dibujados[-1].tag == qn("p:sp")
    assert not any(el.tag == qn("p:pic") for el in dibujados)


def test_la_imagen_vuelve_adentro_del_grupo_debajo_del_precio_y_en_su_lugar():
    slide = _hoja_exportada()
    grupo = next(el for el in slide.shapes._spTree if el.tag == qn("p:grpSp"))
    hijos = [el for el in grupo if el.tag in (qn("p:sp"), qn("p:pic"))]
    assert [el.tag for el in hijos] == [qn("p:pic"), qn("p:sp")]
    # La posición se escribió en las coordenadas del grupo: la imagen se ve
    # donde estaba en el diseño.
    imagen = next(s for s in slide.shapes if s.shape_type is not None and hasattr(s, "shapes")).shapes[0]
    assert abs(Emu(imagen.left).cm - 13) < 0.05 and abs(Emu(imagen.top).cm - 20) < 0.05


# ---------------------------------------------------------------------------
# 2. Tamaños puestos a mano en los segmentos, con la caja sin tamaño manual
# ---------------------------------------------------------------------------

def _caja(id_, x, y, w, h, fs, **extra):
    c = {
        "id": id_, "type": "text", "name": id_,
        "base_bounds": {"x": x, "y": y, "width": w, "height": h},
        "style": {"font_size": fs, "align": "center", "font_family": "Impact", "font_bold": True},
    }
    c.update(extra)
    return c


def _precio(w=11.99, h=5.68):
    return _caja("precio", 0.24, 19.18, w, h, 59.4, segments=[
        {"type": "variable", "value": "unidadMoneda", "_manual_font_override": True,
         "style": {"font_size": 102, "baseline": 60000}},
        {"type": "variable", "value": "precioRegular", "_manual_font_override": True,
         "style": {"font_size": 160, "baseline": 30000}},
    ])


def _vecinos():
    # La geometría real de la plantilla: "Oferta" arriba, el decimal pisando la
    # caja del precio y "unidad" abajo.
    return [
        _caja("oferta", 1.88, 16.27, 10.16, 2.05, 42, static_value="Oferta"),
        _caja("decimal", 10.47, 18.42, 4.17, 9.66, 60, segments=[
            {"type": "variable", "value": "decimalPrecioOferta", "style": {"font_size": 60, "baseline": 30000}}]),
        _caja("unidad", 1.91, 24.03, 10.16, 1.62, 32, static_value="unidad"),
    ]


PRODUCTO = {"unidadMoneda": "$", "precioRegular": "253", "decimalPrecioOferta": ""}


def _tamanos(comps):
    precio = next(c for c in _fit_text_to_box(comps, PRODUCTO, ANCHO_HOJA_A4) if c["id"] == "precio")
    return [s["style"]["font_size"] for s in precio["segments"]]


def test_segmentos_a_mano_no_se_achican_por_los_vecinos():
    # Los vecinos no cuentan: con o sin ellos, el precio sale igual. Antes
    # salía al mínimo (56 y 88) solo por tenerlos al lado.
    con_vecinos = _tamanos([_precio(), *_vecinos()])
    solo = _tamanos([_precio()])
    assert con_vecinos == solo
    # "$253" en negrita a 102/160 roza el ancho útil de su caja de 12 cm: a lo
    # sumo baja un poquito, nunca a la mitad.
    assert con_vecinos[1] > 150


def test_segmentos_a_mano_bajan_si_no_entran_en_su_propia_caja():
    # Caja angosta: "$253" a 102/160 mide ~10,8 cm y no entra en 8 cm. Baja,
    # y los dos en la misma proporción.
    simbolo, numero = _tamanos([_precio(w=8.0), *_vecinos()])
    assert numero < 160 and simbolo < 102
    assert abs(simbolo / numero - 102 / 160) < 0.01
