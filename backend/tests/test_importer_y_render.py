"""Fija el importer de PPTX y el render — los bugs visuales de esta semana.

Los PPTX de prueba se arman en memoria con python-pptx: no hay archivos
binarios en el repo ni dependencia de las plantillas reales de la base.
"""
import io
import re
import zipfile

from pptx import Presentation
from pptx.util import Cm, Pt

from app.services.cenefas.component_renderer import (
    preparar_componentes,
    render_template_to_pptx,
)
from app.services.cenefas.pptx_importer import import_pptx


def _pptx_con_textos(*textos, size_pt=100):
    """Un A4 con un cuadro de texto por cada string recibido."""
    prs = Presentation()
    prs.slide_width = Cm(21.0)
    prs.slide_height = Cm(29.7)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for i, texto in enumerate(textos):
        box = slide.shapes.add_textbox(Cm(2), Cm(3 + i * 5), Cm(17), Cm(4))
        run = box.text_frame.paragraphs[0].add_run()
        run.text = texto
        run.font.size = Pt(size_pt)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _pptx_con_cajas(*cajas, size_pt=100):
    """Un A4 con los cuadros EN LAS POSICIONES que se le pasan.

    `_pptx_con_textos` apila los cuadros uno debajo del otro, que alcanza para
    la mayoria de los tests pero no para los que dependen de que un cuadro
    TAPE a otro: en las plantillas reales de Redexpres el cuadro de
    <<promoOferta>> se dibuja encima del del precio (66% a 100% de solape
    medido en produccion), y esa superposicion es justamente la señal que usa
    el render para saber cual de los dos manda.
    """
    prs = Presentation()
    prs.slide_width = Cm(21.0)
    prs.slide_height = Cm(29.7)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for texto, x, y, w, h in cajas:
        box = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
        run = box.text_frame.paragraphs[0].add_run()
        run.text = texto
        run.font.size = Pt(size_pt)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _componente(defin, contiene):
    return next(c for c in defin["components"] if contiene in str(c))


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------

def test_texto_fijo_junto_al_placeholder_no_se_pierde():
    # Bug real (28/08): "$<<precioOferta>>" en UN solo run descartaba el "$"
    # en silencio — la A4 REDEX re-subida con el símbolo salía igual que antes.
    d = import_pptx(_pptx_con_textos("$<<precioOferta>>"))
    comp = _componente(d, "precioOferta")
    segs = comp.get("segments") or []
    assert any(s["type"] == "static" and "$" in s["value"] for s in segs)
    assert any(s["type"] == "variable" and s["value"] == "precioOferta" for s in segs)


def test_placeholder_canonico_directo():
    d = import_pptx(_pptx_con_textos("<<precioOferta>>"))
    comp = _componente(d, "precioOferta")
    assert comp.get("variable") == "precioOferta"
    assert not comp.get("segments")


def test_moneda_legacy_resuelve_unidad_moneda():
    # Desde el 29/08 el símbolo es variable de nuevo: un <<Moneda>> viejo
    # apunta a unidadMoneda en vez de importarse como cuadro vacío.
    d = import_pptx(_pptx_con_textos("<<Moneda>>"))
    assert any(c.get("variable") == "unidadMoneda" for c in d["components"])


def test_placeholder_dado_de_baja_queda_vacio():
    d = import_pptx(_pptx_con_textos("<<UnidadMedida1>>"))
    comp = d["components"][0]
    assert comp.get("variable") is None
    assert comp.get("static_value") == ""


def test_dos_placeholders_en_un_cuadro():
    d = import_pptx(_pptx_con_textos("<<unidadMoneda>><<precioOferta>>"))
    comp = _componente(d, "precioOferta")
    vars_ = [s["value"] for s in comp["segments"] if s["type"] == "variable"]
    assert vars_ == ["unidadMoneda", "precioOferta"]


# ---------------------------------------------------------------------------
# Render de punta a punta (sin base, sin red)
# ---------------------------------------------------------------------------

def _runs_del_pptx(pptx_bytes):
    with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as z:
        xml = "".join(
            z.read(n).decode("utf-8", "ignore")
            for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n))
    return "".join(re.findall(r"<a:t>([^<]*)</a:t>", xml))


def test_render_imprime_simbolo_y_precio():
    src = _pptx_con_textos("$<<precioOferta>>", "<<descripcion>>")
    d = import_pptx(src)
    pptx, missing = render_template_to_pptx(
        d, [{"precioOferta": "1.290", "descripcion": "Aspiradora MASTER-X"}],
        "a4", None, src)
    runs = _runs_del_pptx(pptx)
    assert "$" in runs and "1.290" in runs and "MASTER-X" in runs


def test_render_dolares():
    src = _pptx_con_textos("<<unidadMoneda>><<precioOferta>>")
    d = import_pptx(src)
    pptx, _ = render_template_to_pptx(
        d, [{"unidadMoneda": "U$S", "precioOferta": "60"}], "a4", None, src)
    assert "U$S" in _runs_del_pptx(pptx)


def test_variable_ausente_en_el_excel_se_reporta():
    # El cuadro tiene texto fijo ("$") ademas de la variable: se dibuja igual
    # y la columna ausente se reporta. (Un cuadro SOLO de variables vacias se
    # saca entero del slide antes de llegar a reportar nada -- es la regla
    # que evita imprimir la cocarda de color sin contenido.)
    src = _pptx_con_textos("$<<precioOferta>>")
    d = import_pptx(src)
    _, missing = render_template_to_pptx(d, [{"descripcion": "X"}], "a4", None, src)
    assert "precioOferta" in missing


# ---------------------------------------------------------------------------
# El achique por vecinos — el solapamiento del 3xA4 (29/08)
# ---------------------------------------------------------------------------

def _caja(x, y, w, h, variable, texto=""):
    return {
        "id": variable, "type": "text", "variable": variable,
        "style": {"font_size": 97.0},
        "base_bounds": {"x": x, "y": y, "width": w, "height": h},
        "computed_bounds": {"x": x, "y": y, "width": w, "height": h},
    }


def _pptx_con_grupo(texto_hijo, *, grupo, hijo):
    """Un A4 con UN grupo que contiene un cuadro de texto.

    `grupo` es (x, y, w, h) en cm sobre la hoja; `hijo` es (x, y, w, h) en el
    sistema INTERNO del grupo. Se arma el XML a mano porque python-pptx no
    sabe crear grupos con chOff/chExt propios, que es justo lo que hace falta
    para reproducir el caso: un grupo cuyo sistema interno NO coincide con el
    de la hoja.
    """
    from pptx.oxml.ns import qn, nsmap
    from lxml import etree
    prs = Presentation()
    prs.slide_width, prs.slide_height = Cm(21.0), Cm(29.7)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    caja = slide.shapes.add_textbox(Cm(hijo[0]), Cm(hijo[1]), Cm(hijo[2]), Cm(hijo[3]))
    caja.text_frame.paragraphs[0].add_run().text = texto_hijo
    sp = caja._element
    spTree = sp.getparent()
    spTree.remove(sp)

    grp = etree.SubElement(spTree, qn("p:grpSp"))
    nv = etree.SubElement(grp, qn("p:nvGrpSpPr"))
    cnv = etree.SubElement(nv, qn("p:cNvPr")); cnv.set("id", "900"); cnv.set("name", "cocarda")
    etree.SubElement(nv, qn("p:cNvGrpSpPr")); etree.SubElement(nv, qn("p:nvPr"))
    pr = etree.SubElement(grp, qn("p:grpSpPr"))
    xfrm = etree.SubElement(pr, qn("a:xfrm"))
    for tag, a, b, va, vb in (
        ("a:off", "x", "y", grupo[0], grupo[1]), ("a:ext", "cx", "cy", grupo[2], grupo[3]),
        ("a:chOff", "x", "y", hijo[0], hijo[1]), ("a:chExt", "cx", "cy", hijo[2], hijo[3]),
    ):
        e = etree.SubElement(xfrm, qn(tag)); e.set(a, str(int(Cm(va)))); e.set(b, str(int(Cm(vb))))
    grp.append(sp)

    buf = io.BytesIO(); prs.save(buf)
    return buf.getvalue()


def _pos_en_hoja(prs, texto):
    """Dónde queda un shape EN LA HOJA, resolviendo la transformación de los
    grupos que lo contienen -- que es lo que hace PowerPoint al dibujar."""
    from pptx.oxml.ns import qn
    CM = 360000.0
    encontrado = []

    def rec(shapes, tf):
        for sh in shapes:
            if sh.shape_type == 6:
                x = sh._element.find(qn("p:grpSpPr") + "/" + qn("a:xfrm"))
                o, e = x.find(qn("a:off")), x.find(qn("a:ext"))
                co, ce = x.find(qn("a:chOff")), x.find(qn("a:chExt"))
                rec(sh.shapes, tf + [(
                    int(o.get("x")) / CM, int(o.get("y")) / CM,
                    int(co.get("x")) / CM, int(co.get("y")) / CM,
                    int(e.get("cx")) / int(ce.get("cx")), int(e.get("cy")) / int(ce.get("cy")),
                )])
                continue
            if not sh.has_text_frame or texto not in sh.text_frame.text:
                continue
            hx, hy = sh.left / CM, sh.top / CM
            for ox, oy, cx, cy, sx, sy in reversed(tf):
                hx, hy = ox + (hx - cx) * sx, oy + (hy - cy) * sy
            encontrado.append((hx, hy))

    rec(prs.slides[0].shapes, [])
    assert len(encontrado) == 1, f"se esperaba un shape con {texto!r}, hay {len(encontrado)}"
    return encontrado[0]


def test_shape_dentro_de_un_grupo_se_exporta_donde_lo_muestra_el_editor():
    # Bug real (Fiesta de Gran Bretaña A4, 07/09/2026): la cocarda del
    # "XX% OFF" es un GRUPO, y un shape adentro de un grupo guarda su posición
    # en el sistema interno del grupo (chOff/chExt), no en el de la hoja.
    #
    # El importer ya convertía interno -> hoja al leer, así que la cocarda se
    # veía bien en el editor. Pero al exportar el motor escribía la coordenada
    # de HOJA tal cual adentro del grupo y PowerPoint la volvía a transformar:
    # guardada en (14,83 , 18,54), terminaba dibujada en (25,65 , 40,56) sobre
    # una hoja de 21 x 29,7 -- fuera de la página, abajo y a la derecha.
    #
    # El grupo de acá tiene la misma forma que el real: ocupa el doble de lo
    # que mide su sistema interno, así que cualquier coordenada escrita sin
    # invertir la transformación se va al doble de distancia.
    src = _pptx_con_grupo("<<precioOferta>>", grupo=(10.0, 12.0, 8.0, 4.0), hijo=(3.0, 2.0, 4.0, 2.0))
    d = import_pptx(src)

    comp = _componente(d, "precioOferta")
    # Lo que ve el editor: coordenadas de HOJA, no las internas (3,0 , 2,0).
    assert abs(comp["base_bounds"]["x"] - 10.0) < 0.02
    assert abs(comp["base_bounds"]["y"] - 12.0) < 0.02

    pptx, _ = render_template_to_pptx(d, [{"precioOferta": "239"}], "a4", None, src)
    x, y = _pos_en_hoja(Presentation(io.BytesIO(pptx)), "239")
    assert abs(x - 10.0) < 0.05, f"la cocarda salio en x={x:.2f}, el editor la muestra en 10,00"
    assert abs(y - 12.0) < 0.05, f"la cocarda salio en y={y:.2f}, el editor la muestra en 12,00"


def test_shape_dentro_de_un_grupo_respeta_que_lo_muevan():
    # El caso que lo destapó: la cocarda salía mal del importador viejo, Ivan
    # la acomodó a mano en el editor y guardó la plantilla. Ahí el movimiento
    # a mano y la transformación del grupo se sumaron y la mandaron al fondo.
    src = _pptx_con_grupo("<<precioOferta>>", grupo=(10.0, 12.0, 8.0, 4.0), hijo=(3.0, 2.0, 4.0, 2.0))
    d = import_pptx(src)
    comp = _componente(d, "precioOferta")
    comp["base_bounds"]["x"] = 4.5     # arrastrado a mano en el editor
    comp["base_bounds"]["y"] = 6.25

    pptx, _ = render_template_to_pptx(d, [{"precioOferta": "239"}], "a4", None, src)
    x, y = _pos_en_hoja(Presentation(io.BytesIO(pptx)), "239")
    assert abs(x - 4.5) < 0.05, f"salio en x={x:.2f} en vez de 4,50"
    assert abs(y - 6.25) < 0.05, f"salio en y={y:.2f} en vez de 6,25"


def test_mxn_imprime_el_literal_una_sola_vez():
    # Bug real (pag. 54 de mundo hogar): la A4 REDEX tiene cocarda
    # (tipoOferta) Y cuadro que tapa al precio (promoOferta) -- en un M x N
    # los dos llevan el mismo literal y "2X1" salia impreso dos veces. La
    # regla de excluyentes esconde la cocarda cuando promoOferta tapa.
    # El cuadro de promoOferta va ENCIMA del precio, como en las plantillas
    # reales -- es la superposicion la que dice cual de los dos manda.
    src = _pptx_con_cajas(
        ("<<tipoOferta>>",                    2.0,  2.0, 6.0, 3.0),   # cocarda, aparte
        ("<<unidadMoneda>><<precioOferta>>",  2.0, 10.0, 17.0, 6.0),  # el precio
        ("<<promoOferta>>",                   2.0, 10.0, 17.0, 6.0),  # lo tapa entero
    )
    d = import_pptx(src)
    pptx, _ = render_template_to_pptx(
        d, [{"tipoOferta": "2x1", "promoOferta": "2x1",
             "unidadMoneda": "$", "precioOferta": "49,50"}],
        "a4", None, src)
    runs = _runs_del_pptx(pptx)
    assert runs.count("2x1") == 1, f"el literal salio {runs.count('2x1')} veces: {runs!r}"
    # y el precio quedo tapado: no se imprime
    assert "49,50" not in runs


def test_combo_con_total_en_promo_no_tapa_el_precio_unitario():
    # Regresion de Preciazos (09/2026): en un combo la cocarda lleva "2x" y
    # promoOferta lleva el TOTAL ("129"), y el diseno muestra las dos cosas a
    # la vez -- arriba "2x $129", abajo el unitario. Una regla que escondiera
    # el precio cada vez que promoOferta trae valor borraba el unitario de
    # todos los carteles de combo.
    #
    # Lo que distingue este caso del M x N de Redexpres (donde promoOferta SI
    # va en lugar del precio) es el CONTENIDO: en un M x N promoOferta trae el
    # mismo literal que la cocarda ("2x1" y "2x1"); en un combo trae un numero
    # distinto. Es la misma senal que evita el literal duplicado.
    src = _pptx_con_textos("<<tipoOferta>>", "<<unidadMoneda>><<precioOferta>>", "<<promoOferta>>")
    d = import_pptx(src)
    pptx, _ = render_template_to_pptx(
        d, [{"tipoOferta": "2x", "promoOferta": "129",
             "unidadMoneda": "$", "precioOferta": "64,50"}],
        "a4", None, src)
    runs = _runs_del_pptx(pptx)
    assert "64,50" in runs, f"se perdio el precio unitario del combo: {runs!r}"
    assert "129" in runs, f"se perdio el total del combo: {runs!r}"


def test_combo_imprime_la_cocarda_aunque_el_diseno_la_encime_al_precio():
    # Bug real (Ivan, 17/09/2026): "Empanadas horneadas congeladas" salia sin
    # el "3x" arriba del precio en la 3xA4 de Redexpres -- la MISMA fila salia
    # bien en la A4. El dato estaba perfecto (tipoOferta="3x",
    # promoOferta="160"): lo borraba la regla de excluyentes, que escondia la
    # cocarda cuando promoOferta la pisaba mas del 50%. La 3xA4 encima las dos
    # cajas 60-70% y la A4 solo 43%, asi que la misma oferta se perdia en una
    # y salia en la otra.
    #
    # Las medidas de abajo son las reales de la plantilla (cocarda 8,48x2,13cm
    # en 1,68/3,58; el cuadro del precio 19,83x4,40 en 1,41/4,29): 67% de
    # solape, justo por encima del viejo umbral.
    src = _pptx_con_cajas(
        ("<<tipoOferta>>",                    1.682, 3.583,  8.478, 2.133),
        ("<<unidadMoneda>><<precioOferta>>",  1.410, 4.290, 19.827, 4.403),
        ("<<promoOferta>>",                   1.410, 4.290, 19.827, 4.403),
    )
    d = import_pptx(src)
    pptx, _ = render_template_to_pptx(
        d, [{"tipoOferta": "3x", "promoOferta": "160",
             "unidadMoneda": "$", "precioOferta": "53"}],
        "a4", None, src)
    runs = _runs_del_pptx(pptx)
    assert "3x" in runs, f"se perdio la cocarda del combo: {runs!r}"
    assert "160" in runs, f"se perdio el total del combo: {runs!r}"


def test_mxn_encimado_sigue_sin_repetir_el_literal():
    # La contracara del test de arriba, con la MISMA geometria: si el literal
    # es el mismo en las dos variables (M x N viejo, antes de que el
    # Convertidor dejara tipoOferta vacia), sigue saliendo una sola vez. Eso
    # ya no lo decide la geometria sino el contenido, y tiene que aguantar sin
    # la entrada de tipoOferta en _EXCLUYENTES.
    src = _pptx_con_cajas(
        ("<<tipoOferta>>",                    1.682, 3.583,  8.478, 2.133),
        ("<<unidadMoneda>><<precioOferta>>",  1.410, 4.290, 19.827, 4.403),
        ("<<promoOferta>>",                   1.410, 4.290, 19.827, 4.403),
    )
    d = import_pptx(src)
    pptx, _ = render_template_to_pptx(
        d, [{"tipoOferta": "2x1", "promoOferta": "2x1",
             "unidadMoneda": "$", "precioOferta": "49,50"}],
        "a4", None, src)
    runs = _runs_del_pptx(pptx)
    assert runs.count("2x1") == 1, f"el literal salio {runs.count('2x1')} veces: {runs!r}"


def test_combo_muestra_el_precio_con_cocarda():
    # En un combo promoOferta viene vacia -> el precio unitario se ve, con la
    # cocarda arriba, aunque el diseno tenga el cuadro de promoOferta.
    src = _pptx_con_textos("<<tipoOferta>>", "<<unidadMoneda>><<precioOferta>>", "<<promoOferta>>")
    d = import_pptx(src)
    pptx, _ = render_template_to_pptx(
        d, [{"tipoOferta": "2x$299", "promoOferta": "",
             "unidadMoneda": "$", "precioOferta": "149,50"}],
        "a4", None, src)
    runs = _runs_del_pptx(pptx)
    assert "2x$299" in runs and "149,50" in runs and "$" in runs


def test_regla_de_segmento_oculta_solo_esa_palabra_del_renglon():
    # Caso de Ivan (08/09/2026): la palabra "unidad" al lado del precio solo
    # corresponde cuando la cenefa es de una categoria unificada (varios SKU
    # en una fila, que quedan con el codigo combinado "A - B"). En un cuadro
    # aparte quedaba desalineada del precio; con una regla sobre el CUADRO,
    # ocultarla se llevaba puesto tambien al precio.
    #
    # El campo se escribe "CODIGO" a proposito: el formulario de reglas pasa a
    # mayusculas lo que se tipea en "Columna del Excel", y tiene que resolver
    # igual contra la clave canonica `codigo` de la fila.
    src = _pptx_con_textos("$<<precioOferta>> unidad", "<<descripcion>>")
    d = import_pptx(src)
    precio = next(c for c in d["components"]
                  if any(s.get("value") == "precioOferta" for s in (c.get("segments") or [])))
    idx = next(i for i, s in enumerate(precio["segments"])
               if s["type"] == "static" and "unidad" in str(s["value"]))
    d["rules"] = [{
        "id": "r1", "name": "unidad solo si es grupo unificado",
        "target_component_id": precio["id"],
        "target_segment_index": idx,
        "condition": {"field": "CODIGO", "operator": "contains", "value": " - "},
        "action": {"type": "show"},
    }]

    un_sku = {"codigo": "580735", "precioOferta": "321,75", "descripcion": "ALMENDRAS"}
    pptx, _ = render_template_to_pptx(d, [un_sku], "a4", None, src)
    runs = _runs_del_pptx(pptx)
    assert "321,75" in runs, f"se perdio el precio: {runs!r}"
    assert "unidad" not in runs, f"'unidad' no debia imprimirse con un solo SKU: {runs!r}"

    unificada = {"codigo": "580735 - 590183", "precioOferta": "321,75", "descripcion": "ALMENDRAS"}
    pptx, _ = render_template_to_pptx(d, [unificada], "a4", None, src)
    runs = _runs_del_pptx(pptx)
    assert "321,75" in runs and "unidad" in runs, f"falto el precio o la palabra: {runs!r}"


def test_lo_que_se_prepara_para_un_producto_no_se_le_pega_al_siguiente():
    # Bug real que encontró Ivan (Gran Bretaña A4, 07/09/2026): "cuando las
    # cifras de precioOferta pasan a ser 4 reducís el tamaño, pero cuando
    # vuelven a 3 no volvés al original". Y no solo no volvía: seguía bajando
    # hoja tras hoja. Con 140 pt de diseño, seis hojas seguidas salieron
    # 120 / 88,3 / 88,3 / 88,3 / 83,9 / 83,9 -- cada producto arrancaba del
    # tamaño que le dejó el anterior.
    #
    # La causa era estructural y sigue estándolo: el layout se arma UNA vez y
    # se reusa para TODOS los productos de la corrida. Cualquier cosa que
    # escriba el cuerpo de un cuadro tiene que escribirla sobre material
    # propio. El achique automático que lo provocaba ya no existe (14/09/2026),
    # pero preparar_componentes sigue escribiendo font_size --ahora porque lo
    # dice una regla-- así que la invariante hay que seguir fijándola.
    #
    # Se prueba la invariante y no un tamaño puntual: lo que sale depende de la
    # geometría de cada plantilla, pero que el resultado sea SIEMPRE material
    # propio no depende de nada.
    caja = _caja(1.0, 10.0, 12.0, 3.0, "precioOferta")
    caja["style"] = {"font_size": 20.0}
    reglas = [{
        "id": "r1", "target_component_id": caja["id"],
        "condition": {"field": "precioOferta", "operator": "length_greater_than", "value": 2},
        "action": {"type": "set_font_size", "value": 12},
    }]
    resultado = preparar_componentes([caja], reglas, {"precioOferta": "396"})

    assert resultado[0] is not caja, "devolvio el MISMO componente del layout compartido"
    assert resultado[0]["style"] is not caja["style"], "devolvio el MISMO style"
    assert resultado[0]["style"]["font_size"] == 12, "no aplico la regla de tamaño"
    assert caja["style"]["font_size"] == 20.0, (
        f"la regla dejo el layout compartido en {caja['style']['font_size']} "
        f"en vez de 20: el proximo producto arranca de ahi")

    # Y el producto siguiente, que NO matchea la regla, vuelve al cuerpo del
    # diseño. Esa es literalmente la mitad del bug que reportó Ivan: "cuando
    # vuelven a 3 no volvés al original".
    otro = preparar_componentes([caja], reglas, {"precioOferta": "39"})
    assert otro[0]["style"]["font_size"] == 20.0


# ---------------------------------------------------------------------------
# El fondo heredado: master Y layout (02/10/2026)
# ---------------------------------------------------------------------------
#
# Cenefas_A5_FIESTA DE ALEMANIA_Frescos tenía el arte entero en el slide
# layout y nada en el master. El importer miraba solo el master, así que la
# plantilla quedaba sin fondo en el preview mientras el export, que preserva
# el archivo, lo imprimía bien. Estos tests fijan que el fondo se importa
# venga de donde venga, y que una imagen del slide sigue siendo una imagen
# común (editable, con su shape real), no un fondo.

def _png_de_prueba():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _pptx_con_imagen_en(donde):
    """Un A4 con un cuadro <<descripcion>> y una imagen a toda hoja que vive
    en el `slide`, en el `layout` o en el `master`. python-pptx solo sabe
    agregar imágenes a un slide, así que para las otras dos se agrega ahí y
    se muda el <p:pic> con su relación, que es exactamente lo que deja
    PowerPoint cuando alguien pega el arte en la vista de patrón."""
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT

    prs = Presentation()
    prs.slide_width = Cm(21.0)
    prs.slide_height = Cm(29.7)
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    box = slide.shapes.add_textbox(Cm(2), Cm(3), Cm(17), Cm(4))
    box.text_frame.paragraphs[0].add_run().text = "<<descripcion>>"
    pic = slide.shapes.add_picture(io.BytesIO(_png_de_prueba()), Cm(0), Cm(0), Cm(21.0), Cm(29.7))
    if donde != "slide":
        destino = layout if donde == "layout" else layout.slide_master
        imagen = slide.part.related_part(pic._element.blip_rId)
        rid = destino.part.relate_to(imagen, RT.IMAGE)
        el = pic._element
        el.getparent().remove(el)
        destino.shapes._spTree.append(el)
        el.blipFill.blip.rEmbed = rid
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _fondos(defin):
    return [c for c in defin["components"] if c["type"] == "image" and c.get("name") == "fondo"]


def test_el_fondo_del_layout_se_importa_como_fondo():
    d = import_pptx(_pptx_con_imagen_en("layout"))
    fondos = _fondos(d)
    assert len(fondos) == 1, "la imagen del layout no llegó al preview"
    fondo = fondos[0]
    assert fondo["locked"] is True
    assert fondo["_source_shape_id"] is None
    assert fondo["image_data"] and fondo["image_ext"] == "png"
    assert abs(fondo["base_bounds"]["width"] - 21.0) < 0.05
    assert fondo["z_index"] == 0, "el fondo va debajo de todo"
    assert _componente(d, "descripcion") is not None


def test_el_fondo_del_master_se_sigue_importando():
    d = import_pptx(_pptx_con_imagen_en("master"))
    assert len(_fondos(d)) == 1
    assert _fondos(d)[0]["_source_shape_id"] is None


def test_una_imagen_del_slide_no_es_fondo():
    d = import_pptx(_pptx_con_imagen_en("slide"))
    assert _fondos(d) == []
    imagenes = [c for c in d["components"] if c["type"] == "image"]
    assert len(imagenes) == 1
    assert imagenes[0]["locked"] is False
    assert imagenes[0]["_source_shape_id"] is not None, "una imagen del slide se muta en su lugar al exportar"


def test_el_export_conserva_el_fondo_del_layout_sin_duplicarlo():
    src = _pptx_con_imagen_en("layout")
    d = import_pptx(src)
    pptx, _ = render_template_to_pptx(
        d, [{"descripcion": "Queso brie"}, {"descripcion": "Salchichas"}], "a4", None, src)
    z = zipfile.ZipFile(io.BytesIO(pptx))
    layouts_con_pic = [n for n in z.namelist()
                       if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", n) and b"<p:pic>" in z.read(n)]
    assert layouts_con_pic, "el layout del export perdió el fondo"
    # Las hojas no dibujan el fondo de nuevo: lo heredan del layout.
    for n in z.namelist():
        if re.match(r"ppt/slides/slide\d+\.xml$", n):
            assert b"<p:pic>" not in z.read(n), f"{n} trae el fondo duplicado encima del heredado"


# ---------------------------------------------------------------------------
# La línea del tachado (Exclusivos TI, 06/10/2026)
# ---------------------------------------------------------------------------

def _pptx_con_linea(*, caja, linea, flip_v=True, ancho_pt=3.0):
    """Un A4 con el cuadro del precio regular y, encima, una línea suelta como
    el "Conector recto" con el que el diseño de Exclusivos TI tacha el precio.
    `linea` es la CAJA de la línea (x, y, w, h); con flip_v va de
    abajo-izquierda a arriba-derecha, que es como la dibuja el diseño."""
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR

    prs = Presentation()
    prs.slide_width = Cm(21.0)
    prs.slide_height = Cm(29.7)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    x, y, w, h = caja
    box = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "<<unidadMoneda>><<precioRegular>> unidad"
    run.font.size = Pt(28)
    lx, ly, lw, lh = linea
    if flip_v:
        conector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Cm(lx), Cm(ly + lh), Cm(lx + lw), Cm(ly))
    else:
        conector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Cm(lx), Cm(ly), Cm(lx + lw), Cm(ly + lh))
    conector.line.width = Pt(ancho_pt)
    conector.line.color.rgb = RGBColor(0, 0, 0)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _lineas(defin):
    return [c for c in defin["components"]
            if c.get("type") == "shape" and (c.get("style") or {}).get("geometry") == "line"]


def _conectores_del_pptx(pptx_bytes):
    """(x, y, w, h) en cm, flipV y grosor en pt de cada conector del slide."""
    from lxml import etree
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
          "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as z:
        root = etree.fromstring(z.read("ppt/slides/slide1.xml"))
    out = []
    for cxn in root.iter("{%s}cxnSp" % ns["p"]):
        xfrm = cxn.find("p:spPr/a:xfrm", ns)
        off, ext = xfrm.find("a:off", ns), xfrm.find("a:ext", ns)
        ln = cxn.find("p:spPr/a:ln", ns)
        out.append((
            int(off.get("x")) / 360000, int(off.get("y")) / 360000,
            int(ext.get("cx")) / 360000, int(ext.get("cy")) / 360000,
            xfrm.get("flipV") in ("1", "true"),
            (int(ln.get("w")) / 12700) if ln is not None and ln.get("w") else None,
        ))
    return out


_CAJA_PRECIO   = (6.21, 17.90, 9.51, 3.51)   # CuadroTexto 9 de la A4 de Exclusivos TI
_LINEA_TACHADO = (9.27, 18.19, 2.46, 1.13)   # Conector recto 5, tal cual viene
_PRODUCTO      = {"unidadMoneda": "$", "precioRegular": "160"}


def test_la_linea_del_tachado_se_importa_como_componente():
    # Caso real (A4 Exclusivos TI, 06/10/2026): el tachado del precio regular
    # es un "Conector recto" suelto. El importer lo descartaba --sin texto ni
    # relleno-- y el editor no lo mostraba, así que no había forma de moverlo
    # cuando el precio salía más corto que el de muestra.
    d = import_pptx(_pptx_con_linea(caja=_CAJA_PRECIO, linea=_LINEA_TACHADO))
    lineas = _lineas(d)
    assert len(lineas) == 1, "la línea del tachado tiene que ser un componente"
    linea = lineas[0]
    b = linea["base_bounds"]
    assert abs(b["x"] - 9.27) < 0.02 and abs(b["y"] - 18.19) < 0.02
    assert abs(b["width"] - 2.46) < 0.02 and abs(b["height"] - 1.13) < 0.02
    assert linea["style"]["flip_v"] is True, "va de abajo-izquierda a arriba-derecha"
    assert linea["style"].get("flip_h") is not True
    assert linea["style"]["line_width_pt"] == 3.0
    assert linea["style"]["line_color"] == "#000000"
    assert linea.get("_source_shape_id") is not None, (
        "sin el id del shape fuente no hay forma de mover el conector al exportar")
    # El cuadro del precio se sigue importando como siempre.
    assert _componente(d, "precioRegular")["type"] == "text"


def test_una_linea_horizontal_tambien_se_importa():
    # Un tachado horizontal mide 0 cm de alto, y el filtro de "forma demasiado
    # chica" de _make_common la tiraba junto con las formas finas.
    d = import_pptx(_pptx_con_linea(caja=_CAJA_PRECIO, linea=(9.27, 18.8, 2.46, 0.0), flip_v=False))
    lineas = _lineas(d)
    assert len(lineas) == 1
    assert abs(lineas[0]["base_bounds"]["width"] - 2.46) < 0.02
    assert lineas[0]["base_bounds"]["height"] < 0.01


def test_la_linea_sin_tocar_sale_donde_estaba():
    src = _pptx_con_linea(caja=_CAJA_PRECIO, linea=_LINEA_TACHADO)
    d = import_pptx(src)
    pptx, _ = render_template_to_pptx(d, [_PRODUCTO], "a4", None, src)
    conectores = _conectores_del_pptx(pptx)
    assert len(conectores) == 1, "tiene que salir UNA línea, ni duplicada ni borrada"
    x, y, w, h, flip_v, grosor = conectores[0]
    assert abs(x - 9.27) < 0.02 and abs(y - 18.19) < 0.02
    assert abs(w - 2.46) < 0.02 and abs(h - 1.13) < 0.02
    assert flip_v and grosor == 3.0


def test_la_linea_movida_en_el_editor_se_exporta_movida():
    # Lo que pidió Ivan: ver la línea para correrla él. Corrida y estirada en
    # el editor, el papel la tiene que traer ahí, con el mismo sentido y grosor.
    src = _pptx_con_linea(caja=_CAJA_PRECIO, linea=_LINEA_TACHADO)
    d = import_pptx(src)
    linea = _lineas(d)[0]
    linea["base_bounds"]["x"] = 7.0
    linea["base_bounds"]["width"] = 3.2
    pptx, _ = render_template_to_pptx(d, [_PRODUCTO], "a4", None, src)
    conectores = _conectores_del_pptx(pptx)
    assert len(conectores) == 1
    x, y, w, h, flip_v, grosor = conectores[0]
    assert abs(x - 7.0) < 0.05, f"salió en x={x:.2f} en vez de 7,00"
    assert abs(w - 3.2) < 0.05, f"salió con ancho {w:.2f} en vez de 3,20"
    assert abs(y - 18.19) < 0.05 and abs(h - 1.13) < 0.05
    assert flip_v and grosor == 3.0, "mover la línea no le cambia el sentido ni el grosor"


def test_una_linea_horizontal_movida_sigue_horizontal():
    # _place_component forzaba 0,1 cm de alto mínimo a todo lo que mutaba: a
    # una línea horizontal eso la inclina.
    src = _pptx_con_linea(caja=_CAJA_PRECIO, linea=(9.27, 18.8, 2.46, 0.0), flip_v=False)
    d = import_pptx(src)
    _lineas(d)[0]["base_bounds"]["x"] = 8.0
    pptx, _ = render_template_to_pptx(d, [_PRODUCTO], "a4", None, src)
    x, y, w, h, _, _ = _conectores_del_pptx(pptx)[0]
    assert abs(x - 8.0) < 0.05
    assert h < 0.01, f"la línea horizontal salió con {h:.3f} cm de alto: inclinada"


def test_la_linea_eliminada_no_sale_en_el_papel():
    src = _pptx_con_linea(caja=_CAJA_PRECIO, linea=_LINEA_TACHADO)
    d = import_pptx(src)
    linea = _lineas(d)[0]
    d["formas_eliminadas"] = [linea["_source_shape_id"]]
    d["components"] = [c for c in d["components"] if c["id"] != linea["id"]]
    pptx, _ = render_template_to_pptx(d, [_PRODUCTO], "a4", None, src)
    assert _conectores_del_pptx(pptx) == []
