"""Cuándo la pantalla de mapeo avisa que la columna OFERTA trae precios.

El aviso existe para el Excel editado a mano (27/08/2026): OFERTADET dice
"Combo" y en OFERTA alguien escribió el precio en vez de "2x$299". NO tiene que
saltar con el export normal de gestión, donde OFERTA repite el precio en las
filas "Precio fijo" y trae el porcentaje en las de "% Descuento". Saltó con la
hoja "Otros productos" del mailing 13318 (Ivan, 08/10/2026), se aceptó, y la
colita de cuadril salió a "$20" (su 20% de descuento) en vez de $639.
"""
from app.services.cenefas.convertidor import oferta_trae_precios


def test_excel_editado_a_mano_sigue_avisando():
    # OFERTADET dice Combo y en OFERTA hay precios pelados distintos de PRECIO.
    assert oferta_trae_precios(
        ["299", "199", "1.100", "89"],
        ["Combo", "Combo", "Combo", "Combo"],
        ["149", "99", "550", "45"],
    )


def test_sin_columna_ofertadet_vale_lo_de_siempre():
    assert oferta_trae_precios(["299", "199", "1.100"])
    assert not oferta_trae_precios(["2x$299", "6x4", "2da unidad al 50%"])
    assert not oferta_trae_precios(["299", "199"])  # con dos no hay patrón


def test_el_export_normal_de_gestion_no_avisa():
    # La hoja "Otros productos" en chico: Precio fijo repite PRECIO, % Descuento
    # trae el porcentaje, los combos traen el literal.
    oferta = ["199", "349", "20", "20", "13", "2x199", "8x6", "299", "169"]
    det    = ["Precio fijo", "Precio Fijo", "% Descuento", "% Descuento", "% Descuento", "Combo", "MxN", "Precio fijo", "Precio fijo"]
    precio = ["199", "349", "639", "1039", "890", "99.5", "74.25", "299", "169"]
    assert not oferta_trae_precios(oferta, det, precio)


def test_oferta_que_repite_precio_no_cuenta():
    # Aunque OFERTADET no diga nada, un número igual a PRECIO no delata nada:
    # leerlo como precio no cambiaría el resultado.
    assert not oferta_trae_precios(["199", "349", "299", "169"], ["", "", "", ""], ["199", "349.0", "299", "169"])


def test_porcentajes_con_ofertadet_corrido_no_alcanzan_solos():
    # Caso real: en las filas de "% Descuento" el export viene corrido una
    # celda y OFERTADET trae un número ("0", "0.59"). Esas filas cuentan como
    # candidatas (no se sabe qué son), pero con los combos y lo que repite
    # PRECIO en la misma muestra no llegan al 80%.
    oferta = ["199", "349", "20", "20", "2x199", "8x6", "299", "169", "13", "3X2"]
    det    = ["Precio fijo", "Precio fijo", "0", "0", "Combo", "MxN", "Precio fijo", "Precio fijo", "0.59", "MxN"]
    precio = ["199", "349", "639", "1039", "99.5", "74.25", "299", "169", "890", "169"]
    assert not oferta_trae_precios(oferta, det, precio)


def test_la_columna_precio_puede_faltar_en_una_fila():
    # None en la lista = el archivo no trae esa columna; "" = la celda vacía.
    assert oferta_trae_precios(["299", "199", "1.100"], ["Combo", "Combo", "Combo"], [None, None, None])
    assert oferta_trae_precios(["299", "199", "1.100"], ["Combo", "Combo", "Combo"], ["", "", ""])


def test_un_porcentaje_junto_al_precio_no_es_un_precio():
    # Las 12 primeras filas reales de "Otros productos": fiambres con OFERTA
    # 10..24 (su % de descuento) y OFERTADET corrido ("0.11", "0.59"), más
    # "Precio fijo" que repite PRECIO. Antes del 08/10 esto avisaba.
    oferta = ["199", "19", "24", "199", "11", "12", "13", "10", "199", "349", "20", "20"]
    det    = ["Precio fijo", "0.11", "0.3", "Precio fijo", "0.59", "0.2", "0.59", "0.61", "Precio fijo", "Precio Fijo", "0", "0"]
    precio = ["199", "880", "640", "199", "890", "710", "890", "590", "199", "349", "639", "1039"]
    assert not oferta_trae_precios(oferta, det, precio)
    # Y el mismo número SIN la columna PRECIO al lado sigue contando como precio.
    assert oferta_trae_precios(["19", "24", "11", "12"], ["0.11", "0.3", "0.59", "0.2"], [None] * 4)
