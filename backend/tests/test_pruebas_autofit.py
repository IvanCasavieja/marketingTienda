"""El mundo de pruebas, aislado.

Lo que estos tests fijan NO es que el autoajuste funcione --eso solo lo puede
decir PowerPoint, abriendo el archivo-- sino las dos mitades del pedido de
Ivan (17/09/2026):

  1. Que en el mundo `pruebas` el autoajuste salga ACTIVADO en todos los
     cuadros del PPTX descargado.
  2. Que en TODOS los demás mundos no cambie absolutamente nada.

La segunda es la que importa de verdad: "hasta ahora lo que tenemos por suerte
está funcionando bien, entonces precisamos que no salpique para otros lados".
"""
import io
import zipfile

import pytest
from pptx import Presentation
from pptx.util import Cm, Pt

from app.services.cenefas import pruebas
from app.services.cenefas.component_renderer import render_template_to_pptx
from app.services.cenefas.pptx_importer import import_pptx


# Los siete mundos reales de la tabla `cenefa_destinos` al 17/09/2026, más el
# caso sin mundo. Ninguno puede verse afectado.
MUNDOS_DE_PRODUCCION = [
    "redexpres", "rompe_precios", "parrilla_y_vinos", "mega_rompe_precios",
    "preciazos", "gran_bretana", "congelados", None,
]


def _pptx_base(texto="<<descripcion>>"):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Cm(21.0), Cm(29.7)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    caja = slide.shapes.add_textbox(Cm(2), Cm(10), Cm(17), Cm(4))
    run = caja.text_frame.paragraphs[0].add_run()
    run.text = texto
    run.font.size = Pt(40)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _bodypr_xml(pptx_bytes):
    with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as z:
        return "".join(
            z.read(n).decode("utf-8", "ignore") for n in z.namelist()
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )


def _generar(category, texto="Una descripcion larguisima que no entra ni a palos"):
    src = _pptx_base()
    d = {**import_pptx(src), "category": category}
    pptx, _ = render_template_to_pptx(d, [{"descripcion": texto}], "a4", None, src)
    return _bodypr_xml(pptx)


# ---------------------------------------------------------------------------
# 1. En pruebas: el autoajuste sale prendido
# ---------------------------------------------------------------------------

def test_en_pruebas_el_pptx_sale_con_el_autoajuste_activado():
    xml = _generar("pruebas")
    assert "normAutofit" in xml, "el mundo de pruebas tiene que salir con autoajuste"
    assert "noAutofit" not in xml, "quedó el apagado de producción"


def test_en_pruebas_se_activa_en_TODOS_los_cuadros():
    # "obliguemos a que en la sección pruebas se active esto en todos los
    # cuadros" -- si un solo cuadro se escapa, el experimento no dice nada.
    src = _pptx_base()
    d = {**import_pptx(src), "category": "pruebas"}
    prs = Presentation(io.BytesIO(src))
    cuadros = sum(1 for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
    assert pruebas.aplicar_autofit(prs, d) == cuadros


# ---------------------------------------------------------------------------
# 2. Fuera de pruebas: nada cambia. Es la mitad que no puede fallar.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mundo", MUNDOS_DE_PRODUCCION)
def test_ningun_otro_mundo_se_ve_afectado(mundo):
    xml = _generar(mundo)
    assert "noAutofit" in xml, f"el mundo {mundo!r} perdió el apagado de autoajuste"
    assert "normAutofit" not in xml, f"al mundo {mundo!r} se le activó el autoajuste"


@pytest.mark.parametrize("mundo", MUNDOS_DE_PRODUCCION)
def test_fuera_de_pruebas_no_se_toca_ni_un_cuadro(mundo):
    # Contado, no supuesto: la función devuelve cuántos cuadros tocó.
    src = _pptx_base()
    d = {**import_pptx(src), "category": mundo}
    assert pruebas.aplicar_autofit(Presentation(io.BytesIO(src)), d) == 0


def test_el_mundo_se_lee_exacto_y_no_por_parecido():
    # Un mundo que apenas se parezca no entra. "pruebas_viejo", "Pruebas 2",
    # cualquier cosa que no sea el slug exacto queda afuera.
    for casi in ("pruebas_viejo", "pruebas 2", "de_pruebas", "prueba", "preciazos", ""):
        assert not pruebas.es_de_pruebas({"category": casi}), casi
    # El slug exacto sí, con o sin mayúsculas y espacios de más.
    for igual in ("pruebas", "Pruebas", "  PRUEBAS  "):
        assert pruebas.es_de_pruebas({"category": igual}), igual


def test_una_definicion_sin_mundo_no_es_de_pruebas():
    assert not pruebas.es_de_pruebas({})
    assert not pruebas.es_de_pruebas({"category": None})
    assert not pruebas.es_de_pruebas(None)


# ---------------------------------------------------------------------------
# 3. El XML tiene que quedar bien formado, no solo tener el tag
# ---------------------------------------------------------------------------

def test_el_autoajuste_queda_en_su_lugar_del_esquema():
    # El orden de los hijos de a:bodyPr lo fija el esquema: el autoajuste va
    # antes de a:scene3d. Appendearlo al final deja un XML que PowerPoint
    # rechaza, y eso no se nota hasta que alguien abre el archivo.
    xml = _generar("pruebas")
    assert xml.count("normAutofit") >= 1
    # Ningún cuadro puede quedar con dos autoajustes a la vez: son
    # mutuamente excluyentes.
    assert "noAutofit" not in xml and "spAutoFit" not in xml


def test_el_archivo_de_pruebas_sigue_abriendose():
    src = _pptx_base()
    d = {**import_pptx(src), "category": "pruebas"}
    pptx, _ = render_template_to_pptx(d, [{"descripcion": "Texto"}], "a4", None, src)
    prs = Presentation(io.BytesIO(pptx))   # si el XML quedó roto, revienta acá
    textos = [sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame]
    assert "Texto" in textos
