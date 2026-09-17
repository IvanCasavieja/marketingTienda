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
import re
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


def _generar(category, texto="Una descripcion larguisima que no entra ni a palos", filas=1):
    src = _pptx_base()
    d = {**import_pptx(src), "category": category}
    pptx, _ = render_template_to_pptx(d, [{"descripcion": texto}] * filas, "a4", None, src)
    return _bodypr_xml(pptx)


def _autoajuste_por_hoja(pptx_bytes):
    """Qué autoajuste quedó en cada hoja, en orden."""
    salida = []
    with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as z:
        nombres = sorted(
            (n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")),
            key=lambda n: int("".join(ch for ch in n if ch.isdigit())),
        )
        for n in nombres:
            xml = z.read(n).decode("utf-8", "ignore")
            if "spAutoFit" in xml:
                salida.append("spAutoFit")
            elif "normAutofit" in xml:
                escala = re.search(r'normAutofit[^/>]*fontScale="(\d+)"', xml)
                salida.append(f"normAutofit:{escala.group(1)}" if escala else "normAutofit")
            else:
                salida.append("noAutofit")
    return salida


# ---------------------------------------------------------------------------
# 1. En pruebas: el autoajuste sale prendido
# ---------------------------------------------------------------------------

def test_en_pruebas_cada_hoja_lleva_su_variante_del_ciclo():
    # El experimento: un solo PPTX donde lo UNICO que cambia entre hojas es el
    # autoajuste. Si dos hojas salieran iguales, compararlas no diria nada.
    src = _pptx_base()
    d = {**import_pptx(src), "category": "pruebas"}
    largo = "YERBA CANARIAS TRADICIONAL 1 KG con una coletilla larga"
    pptx, _ = render_template_to_pptx(d, [{"descripcion": largo}] * 5, "a4", None, src)
    hojas = _autoajuste_por_hoja(pptx)
    assert len(hojas) == 5
    assert hojas[0] == "noAutofit", "la hoja 1 es el control: lo mismo que produccion"
    assert hojas[1] == "normAutofit", "la hoja 2 va sin escala, a proposito"
    assert hojas[2] == "normAutofit:50000", "la hoja 3 lleva el 50% puesto a mano"
    assert hojas[3].startswith("normAutofit"), "la hoja 4 lleva la escala medida"
    assert hojas[4] == "spAutoFit"
    assert len(set(hojas)) == 5, f"dos hojas salieron iguales: {hojas}"


def test_la_escala_medida_achica_un_texto_que_no_entra():
    # Un texto que desborda tiene que salir con una escala MENOR al 100%; si
    # saliera al 100% el modo no estaria midiendo nada.
    src = _pptx_base()
    d = {**import_pptx(src), "category": "pruebas"}
    largo = "UNA DESCRIPCION DESMESURADAMENTE LARGA QUE NO ENTRA NI A PALOS EN ESA CAJITA"
    pptx, _ = render_template_to_pptx(d, [{"descripcion": largo}] * 4, "a4", None, src)
    hoja4 = _autoajuste_por_hoja(pptx)[3]
    assert ":" in hoja4, f"la hoja de escala medida salio sin escala: {hoja4}"
    escala = int(hoja4.split(":")[1])
    assert 25000 <= escala < 100000, f"escala fuera de rango: {escala}"


def test_la_escala_medida_no_achica_lo_que_ya_entra():
    src = _pptx_base()
    d = {**import_pptx(src), "category": "pruebas"}
    pptx, _ = render_template_to_pptx(d, [{"descripcion": "Corto"}] * 4, "a4", None, src)
    assert _autoajuste_por_hoja(pptx)[3] == "normAutofit", "achico un texto que entraba"


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

def test_ningun_cuadro_queda_con_dos_autoajustes():
    # Son mutuamente excluyentes en el esquema. Un cuadro con dos es un XML
    # que PowerPoint rechaza, y eso no se nota hasta que alguien lo abre.
    src = _pptx_base()
    d = {**import_pptx(src), "category": "pruebas"}
    pptx, _ = render_template_to_pptx(d, [{"descripcion": "Texto"}] * 5, "a4", None, src)
    with zipfile.ZipFile(io.BytesIO(pptx)) as z:
        for n in z.namelist():
            if not (n.startswith("ppt/slides/slide") and n.endswith(".xml")):
                continue
            xml = z.read(n).decode("utf-8", "ignore")
            for body in re.findall(r"<a:bodyPr.*?(?:</a:bodyPr>|/>)", xml, re.S):
                cuantos = sum(body.count(t) for t in ("noAutofit", "normAutofit", "spAutoFit"))
                assert cuantos <= 1, f"{n}: un bodyPr con {cuantos} autoajustes -> {body[:120]}"


def test_el_archivo_de_pruebas_sigue_abriendose():
    src = _pptx_base()
    d = {**import_pptx(src), "category": "pruebas"}
    pptx, _ = render_template_to_pptx(d, [{"descripcion": "Texto"}], "a4", None, src)
    prs = Presentation(io.BytesIO(pptx))   # si el XML quedó roto, revienta acá
    textos = [sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame]
    assert "Texto" in textos
