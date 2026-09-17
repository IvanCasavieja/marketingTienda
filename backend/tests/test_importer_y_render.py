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
