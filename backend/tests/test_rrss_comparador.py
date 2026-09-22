"""Comparación de placas de redes sociales contra el mailing (rrss/comparador.py).

La regla es ESTRICTA: lo que dice la placa tiene que ser exactamente lo que
dice el mailing. Estos tests fijan qué cuenta como diferencia -- incluidas las
que Ivan encontró en la campaña real del 17 al 20 de setiembre de 2026 (el
"unidad" que en las placas está en la Stella y en el mailing está en el vino).
"""
from app.services.rrss import comparador as c
from app.services.rrss import imagenes


def prod(**kw) -> dict:
    base = dict(
        descripcion="Bola de lomo. Kg", precio_anterior="$499", precio_anterior_tachado=True,
        mecanica="", oferta_encabezado="Oferta", oferta_precio="$399", oferta_pie="",
        es_alcohol=False, cajas={},
    )
    base.update(kw)
    return base


def placa(producto=None, **kw) -> dict:
    base = dict(
        producto=producto or prod(), fecha="DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE",
        logo_campana_presente=True, isotipo_presente=True,
        legal_bases="Bases y condiciones en tiendainglesa.com.uy", legal_alcohol="", cta="",
        otros_textos=[], cajas={},
        imagen_producto=dict(presente=True, que_se_ve="carne", coincide_con_descripcion=True, motivo=""),
    )
    base.update(kw)
    return base


MAILING = {
    "fecha": "DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE",
    "legal_alcohol": "Beber con moderación. Prohibida la venta a menores de 18 años.",
    "productos": [
        prod(),
        prod(descripcion="Cerveza STELLA ARTOIS. Lata 710 ml", precio_anterior="$171", oferta_precio="$125", es_alcohol=True),
        prod(descripcion="Vino BRISAS DEL ESTE Tinto Tannat, Cabernet Sauvignon, Rosé Blend o Blanco Sauvignon Blanc. 750 ml",
             precio_anterior="$340 unidad", oferta_precio="$199", oferta_pie="unidad", es_alcohol=True),
        prod(descripcion="Arvejas TIENDA INGLESA. 300 g", precio_anterior="$48 unidad", precio_anterior_tachado=False,
             mecanica="2x$75", oferta_encabezado="Comprando 2", oferta_precio="$37,50", oferta_pie="unidad"),
    ],
}
CONFIG = {"legal_bases": "Bases y condiciones en tiendainglesa.com.uy", "legal_alcohol": ""}


def filas_por_campo(filas):
    return {f["campo"]: f for f in filas}


def errores(filas):
    return {f["campo"] for f in filas if f["severidad"] == "error"}


# ---------------------------------------------------------------- estricto

def test_los_adornos_no_son_texto():
    """Los puntos rojos de la fecha de la campaña (•) salían como una diferencia
    de fecha en casi todas las placas."""
    from app.services.rrss.catti import limpiar_texto
    assert limpiar_texto("DEL JUEVES 17 AL DOMINGO 20 • DE SETIEMBRE •") == "DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE"
    assert limpiar_texto("DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE") == "DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE"


def test_placa_identica_no_tiene_diferencias():
    idx, _, filas = c.comparar_placa(placa(), MAILING, CONFIG)
    assert idx == 0
    assert errores(filas) == set()
    assert c.estado_de_la_placa(filas, idx) == "ok"


def test_una_mayuscula_es_una_diferencia():
    p = placa(prod(descripcion="Bola de lomo. kg"))
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert errores(filas) == {"descripcion"}
    fila = filas_por_campo(filas)["descripcion"]
    assert fila["estado"] == "diferente"
    assert (fila["placa"], fila["mailing"]) == ("Bola de lomo. kg", "Bola de lomo. Kg")


def test_un_espacio_es_una_diferencia():
    # el "100g" de la placa contra el "100 g" del mailing
    mailing = {**MAILING, "productos": [prod(descripcion="Queso Colonia IL CAPITANO. 100 g")]}
    p = placa(prod(descripcion="Queso Colonia IL CAPITANO. 100g"))
    _, _, filas = c.comparar_placa(p, mailing, CONFIG)
    assert errores(filas) == {"descripcion"}


def test_un_punto_de_mas_es_una_diferencia():
    p = placa(prod(descripcion="Bola de lomo. Kg."))
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert errores(filas) == {"descripcion"}


def test_el_precio_tiene_que_ser_exacto():
    p = placa(prod(oferta_precio="$389"))
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert errores(filas) == {"oferta_precio"}


def test_los_saltos_de_renglon_no_cuentan():
    # catti.limpiar_texto junta los renglones con un espacio: acá ya llega así
    from app.services.rrss.catti import limpiar_texto
    assert limpiar_texto("Bola\nde lomo.\n  Kg") == "Bola de lomo. Kg"


def test_el_unidad_cambiado_entre_stella_y_vino():
    """El error real de la campaña: en el mailing 'unidad' va en el vino y en
    la placa va en la Stella."""
    stella = placa(prod(
        descripcion="Cerveza STELLA ARTOIS. Lata 710 ml.", precio_anterior="$171 unidad",
        oferta_precio="$125", oferta_pie="unidad", es_alcohol=True,
    ), legal_alcohol=MAILING["legal_alcohol"])
    vino = placa(prod(
        descripcion="Vino BRISAS DEL ESTE. Tinto Tannat, Cabernet Sauvignon, Rosé Blend o Blanco Sauvignon Blanc 750 ml",
        precio_anterior="$340", oferta_precio="$199", oferta_pie="", es_alcohol=True,
    ), legal_alcohol=MAILING["legal_alcohol"])

    idx_s, _, filas_s = c.comparar_placa(stella, MAILING, CONFIG)
    idx_v, _, filas_v = c.comparar_placa(vino, MAILING, CONFIG)
    assert (idx_s, idx_v) == (1, 2)
    # Stella: de más el "unidad" (y el punto de "ml.")
    assert {"descripcion", "precio_anterior", "oferta_pie"} <= errores(filas_s)
    assert filas_por_campo(filas_s)["oferta_pie"]["estado"] == "sobra_en_placa"
    # Vino: falta el "unidad" en el precio y en el pie
    assert {"precio_anterior", "oferta_pie", "descripcion"} <= errores(filas_v)
    assert filas_por_campo(filas_v)["oferta_pie"]["estado"] == "falta_en_placa"


def test_tachado_solo_se_compara_si_hay_precio_en_los_dos():
    p = placa(prod(precio_anterior_tachado=False))
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert errores(filas) == {"precio_anterior_tachado"}
    # sin precio anterior en ninguno, no hay fila de tachado
    mailing = {**MAILING, "productos": [prod(precio_anterior="", precio_anterior_tachado=False)]}
    p2 = placa(prod(precio_anterior="", precio_anterior_tachado=False))
    _, _, filas2 = c.comparar_placa(p2, mailing, CONFIG)
    assert "precio_anterior_tachado" not in filas_por_campo(filas2)


def test_mecanica_que_falta():
    p = placa(prod(
        descripcion="Arvejas TIENDA INGLESA. 300 g", precio_anterior="$48 unidad", precio_anterior_tachado=False,
        mecanica="", oferta_encabezado="Comprando 2", oferta_precio="$37,50", oferta_pie="unidad",
    ))
    idx, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert idx == 3
    assert errores(filas) == {"mecanica"}
    assert filas_por_campo(filas)["mecanica"]["estado"] == "falta_en_placa"


# ---------------------------------------------------------------- elementos

def test_fecha_distinta():
    p = placa(fecha="DEL JUEVES 17 AL DOMINGO 20 DE SEPTIEMBRE")
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert errores(filas) == {"fecha"}


def test_faltan_los_legales_de_bases():
    p = placa(legal_bases="")
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert errores(filas) == {"legal_bases"}


def test_alcohol_exige_su_leyenda():
    sin = placa(prod(descripcion="Cerveza STELLA ARTOIS. Lata 710 ml", precio_anterior="$171", oferta_precio="$125", es_alcohol=True))
    _, _, filas = c.comparar_placa(sin, MAILING, CONFIG)
    assert "legal_alcohol" in errores(filas)
    assert filas_por_campo(filas)["legal_alcohol"]["estado"] == "falta_en_placa"

    con = placa(sin["producto"], legal_alcohol=MAILING["legal_alcohol"])
    _, _, filas = c.comparar_placa(con, MAILING, CONFIG)
    assert "legal_alcohol" not in errores(filas)


def test_la_leyenda_de_alcohol_tambien_es_estricta():
    p = placa(
        prod(descripcion="Cerveza STELLA ARTOIS. Lata 710 ml", precio_anterior="$171", oferta_precio="$125", es_alcohol=True),
        legal_alcohol="Beber con moderacion. Prohibida la venta a menores de 18 años.",
    )
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert "legal_alcohol" in errores(filas)


def test_leyenda_de_alcohol_en_un_producto_que_no_lo_es_es_aviso():
    p = placa(legal_alcohol=MAILING["legal_alcohol"])
    idx, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    fila = filas_por_campo(filas)["legal_alcohol"]
    assert fila["severidad"] == "aviso"
    assert c.estado_de_la_placa(filas, idx) == "avisos"


def test_falta_el_logo_y_la_foto():
    p = placa(logo_campana_presente=False,
              imagen_producto=dict(presente=False, que_se_ve="", coincide_con_descripcion=True, motivo=""))
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert errores(filas) == {"logo_campana", "imagen_producto"}


def test_foto_que_no_parece_del_producto_es_un_aviso():
    p = placa(imagen_producto=dict(presente=True, que_se_ve="una lata de cerveza",
                                   coincide_con_descripcion=False, motivo="la descripción dice carne"))
    idx, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert errores(filas) == set()
    assert c.estado_de_la_placa(filas, idx) == "avisos"


# ---------------------------------------------------------------- emparejar

def test_emparejar_tolera_una_descripcion_mal_escrita():
    idx, _ = c.emparejar(prod(descripcion="Bola de lomo Kilo"), MAILING["productos"])
    assert idx == 0


def test_placa_de_un_producto_que_no_esta_en_el_mailing():
    p = placa(prod(descripcion="Aceite de girasol COCINERO. 900 ml", precio_anterior="$99", oferta_precio="$79"))
    idx, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    assert idx is None
    assert c.estado_de_la_placa(filas, idx) == "sin_match"
    # sin producto con qué compararla, igual se validan sus elementos fijos
    assert "logo_campana" in filas_por_campo(filas)


def test_no_adivina_entre_dos_productos_casi_iguales():
    mailing = {"productos": [prod(descripcion="Cerveza IMPERIAL. Lata 710 ml", oferta_precio="$129"),
                             prod(descripcion="Cerveza IMPERIAL. Lata 710 ml", oferta_precio="$129")]}
    idx, _ = c.emparejar(prod(descripcion="Cerveza IMPERIAL. Lata 710 ml", oferta_precio="$129"), mailing["productos"])
    assert idx is None


# ---------------------------------------------------------------- segunda lectura

def test_un_error_que_la_segunda_lectura_no_repite_baja_a_aviso():
    p = placa(prod(descripcion="Bola de lomo. kg"))
    idx, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    segunda = c.campos_leidos(placa(prod(descripcion="Bola de lomo. Kg")))  # la 2ª lectura lee "Kg"
    filas = c.confirmar_con_segunda_lectura(filas, segunda)
    assert errores(filas) == set()
    assert filas_por_campo(filas)["descripcion"]["estado"] == "revisar"
    assert c.estado_de_la_placa(filas, idx) == "avisos"


def test_un_error_que_la_segunda_lectura_confirma_se_mantiene():
    p = placa(prod(descripcion="Bola de lomo. kg"))
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    filas = c.confirmar_con_segunda_lectura(filas, c.campos_leidos(p))
    assert errores(filas) == {"descripcion"}


def test_faltante_que_la_segunda_lectura_si_encuentra_baja_a_aviso():
    p = placa(legal_bases="")
    _, _, filas = c.comparar_placa(p, MAILING, CONFIG)
    filas = c.confirmar_con_segunda_lectura(filas, c.campos_leidos(placa()))  # la 2ª lo encontró
    assert errores(filas) == set()


# ---------------------------------------------------------------- el lote

def img(id_, formato, match, lectura=None, nombre=None):
    return {"id": id_, "nombre_archivo": nombre or f"{id_}.jpg", "formato": formato,
            "match_indice": match, "lectura": lectura or placa()}


def test_adaptaciones_completas_y_una_que_falta():
    imgs = [
        img(1, "1:1", 0), img(2, "4:5", 0), img(3, "9:16", 0),
        img(4, "1:1", 1), img(5, "4:5", 1),  # a la Stella le falta la 9:16
    ]
    r = c.chequeos_del_lote(imgs, MAILING["productos"])
    assert r["formatos_esperados"] == ["1:1", "4:5", "9:16"]
    por_match = {g["match_indice"]: g for g in r["grupos"]}
    assert por_match[0]["avisos"] == []
    faltas = [a for a in por_match[1]["avisos"] if a["tipo"] == "falta_formato"]
    assert [a["formato"] for a in faltas] == ["9:16"]
    assert r["productos_con_placa"] == 2 and r["productos_mailing"] == 4


def test_un_solo_producto_no_marca_formatos_faltantes():
    r = c.chequeos_del_lote([img(1, "1:1", 0)], MAILING["productos"])
    assert r["grupos"][0]["avisos"] == []


def test_placa_repetida_en_el_mismo_formato():
    r = c.chequeos_del_lote([img(1, "1:1", 0), img(2, "1:1", 0)], MAILING["productos"])
    assert [a["tipo"] for a in r["grupos"][0]["avisos"]] == ["repetida"]


def test_adaptaciones_sin_mailing_se_juntan_y_se_comparan_entre_si():
    a = placa(prod(descripcion="Aceite COCINERO. 900 ml", oferta_precio="$79"))
    b = placa(prod(descripcion="Aceite COCINERO. 900 ml", oferta_precio="$97"))  # otro precio en la 4:5
    r = c.chequeos_del_lote([img(1, "1:1", None, a), img(2, "4:5", None, b)], MAILING["productos"])
    assert len(r["grupos"]) == 1
    incons = r["grupos"][0]["inconsistencias"]
    assert [i["campo"] for i in incons] == ["oferta_precio"]


def test_cta_mezclado():
    con_comprar = placa(cta="Comprar")
    con_ver = placa(cta="Ver más")
    r = c.chequeos_del_lote(
        [img(1, "1:1", 0, con_comprar), img(2, "4:5", 0, con_comprar), img(3, "9:16", 0, con_ver), img(4, "1:1", 1, placa())],
        MAILING["productos"],
    )
    assert r["cta"]["hay_mezcla"] is True
    variantes = {v["cta"]: v["cantidad"] for v in r["cta"]["variantes"]}
    assert variantes == {"Comprar": 2, "Ver más": 1, None: 1}


def test_cta_uniforme_o_ausente_no_es_mezcla():
    assert c.chequeos_del_lote([img(1, "1:1", 0), img(2, "4:5", 0)], MAILING["productos"])["cta"]["hay_mezcla"] is False
    todas = placa(cta="Comprar")
    assert c.chequeos_del_lote([img(1, "1:1", 0, todas), img(2, "4:5", 0, todas)], MAILING["productos"])["cta"]["hay_mezcla"] is False


# ---------------------------------------------------------------- imagenes

def test_clasificar_formato():
    assert imagenes.clasificar_formato(2250, 2250) == "1:1"
    assert imagenes.clasificar_formato(2250, 2813) == "4:5"
    assert imagenes.clasificar_formato(2250, 4000) == "9:16"
    assert imagenes.clasificar_formato(1200, 628) == "1200x628"


def test_caja_valida_descarta_lo_que_no_sirve():
    assert imagenes.caja_valida([0.1, 0.2, 0.5, 0.6]) == [0.1, 0.2, 0.5, 0.6]
    assert imagenes.caja_valida([100, 200, 500, 600]) is None       # vino en pixeles
    assert imagenes.caja_valida([0.5, 0.5, 0.4, 0.4]) is None       # invertida
    assert imagenes.caja_valida([0.1, 0.1, 0.1, 0.1]) is None       # area cero
    assert imagenes.caja_valida(None) is None
    assert imagenes.caja_valida("hola") is None


def test_recortar_y_grilla():
    from PIL import Image
    im = Image.new("RGB", (800, 1200), (255, 255, 255))
    r = imagenes.recortar(im, [0.25, 0.25, 0.75, 0.5], ancho_max=300)
    assert r is not None and r.width <= 300
    assert imagenes.recortar(im, [9, 9, 9, 9]) is None
    g = imagenes.con_grilla(im)
    assert g.size == im.size and g.getpixel((80, 100)) != (255, 255, 255)  # líneas dibujadas


def test_paginas_del_mailing_desde_un_pdf():
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=300, height=400)
    doc.new_page(width=300, height=400)
    paginas = imagenes.paginas_del_mailing(doc.tobytes(), "application/pdf", "m.pdf")
    assert len(paginas) == 2 and paginas[0].width == 1600


# ---------------------------------------------------------------- (22/09) la relectura del mailing y la cola del precio

def test_cola_del_precio():
    assert c.cola_del_precio("$340 unidad") == "unidad"
    assert c.cola_del_precio("$171") == ""
    assert c.cola_del_precio("U$S149 c/u") == "c/u"
    assert c.cola_del_precio("") == "" and c.cola_del_precio("Oferta") == ""


def _error_de_precio():
    return [c._fila("precio_anterior", "Precio anterior", "producto", "$1090", "$1.090", "diferente", "error"),
            c._fila("descripcion", "Descripción", "producto", "Jarra", "Jarra", "ok", None)]


def test_la_relectura_del_mailing_que_coincide_con_la_placa_levanta_el_error():
    """Placa leída dos veces igual + recorte ampliado del mailing igual a la
    placa = tres lecturas contra una: la fila queda en ok y explica por qué."""
    filas = c.confirmar_con_relectura_de_la_fuente(_error_de_precio(), {"precio_anterior": "$1090"})
    fila = filas_por_campo(filas)["precio_anterior"]
    assert fila["estado"] == "ok" and fila["severidad"] is None and fila["mailing"] == "$1090"
    assert "'$1.090'" in fila["nota"] and "recorte ampliado" in fila["nota"]
    assert c.estado_de_la_placa(filas, 0) == "ok"


def test_la_relectura_que_repite_la_primera_sostiene_el_error():
    filas = c.confirmar_con_relectura_de_la_fuente(_error_de_precio(), {"precio_anterior": "$1.090"})
    assert filas_por_campo(filas)["precio_anterior"]["severidad"] == "error"


def test_la_relectura_que_dice_otra_cosa_baja_a_aviso():
    filas = c.confirmar_con_relectura_de_la_fuente(_error_de_precio(), {"precio_anterior": "$1O90"})
    fila = filas_por_campo(filas)["precio_anterior"]
    assert fila["severidad"] == "aviso" and fila["estado"] == "revisar"
    assert "dos lecturas" in fila["nota"] and "'$1O90'" in fila["nota"]


def test_la_relectura_no_toca_lo_que_no_es_texto_ni_lo_que_no_releyo():
    filas = [c._fila("precio_anterior_tachado", "Tachado", "producto", "sin tachar", "tachado", "diferente", "error"),
             c._fila("oferta_precio", "Precio de oferta", "producto", "$799", "$7799", "diferente", "error")]
    filas = c.confirmar_con_relectura_de_la_fuente(filas, {"precio_anterior": "$1090"})
    assert all(f["severidad"] == "error" for f in filas)


def test_el_tachado_tambien_se_confirma_con_la_segunda_lectura():
    """Era el único error que se acusaba con UNA lectura: en la corrida real del
    22/09 una placa 9:16 salió acusada de "sin tachar" por una línea de un píxel
    que la lectura no vio. Ahora entra en la segunda lectura como los textos."""
    assert "precio_anterior_tachado" in c.CAMPOS_CONFIRMABLES
    fila = c._fila("precio_anterior_tachado", "Tachado", "producto", "sin tachar", "tachado", "diferente", "error")
    segunda = c.campos_leidos(placa(prod(precio_anterior_tachado=True)))
    assert segunda["precio_anterior_tachado"] == "tachado"
    filas = c.confirmar_con_segunda_lectura([fila], segunda)
    assert filas[0]["severidad"] == "aviso" and "dos lecturas" in filas[0]["nota"]
    # y si la segunda lectura repite "sin tachar", el error se sostiene
    fila = c._fila("precio_anterior_tachado", "Tachado", "producto", "sin tachar", "tachado", "diferente", "error")
    filas = c.confirmar_con_segunda_lectura([fila], c.campos_leidos(placa(prod(precio_anterior_tachado=False))))
    assert filas[0]["severidad"] == "error"
    # del lado del mailing, el producto releído se aplana igual
    assert c.campos_del_producto(prod(precio_anterior_tachado=False))["precio_anterior_tachado"] == "sin tachar"
