"""Un mailing que viene en pliego: dos carillas A4 impresas lado a lado.

El caso real (23/09/2026): el mailing del 24 al 27 de setiembre vino como un
PDF de 2 hojas de 44 x 32 cm, y cada hoja eran DOS carillas juntas — a la
izquierda "Rompe Precios" del 23 al 30, a la derecha "Los Rompe del Finde" del
24 al 27. Leída como una sola página, con una sola fecha, CatTi se quedaba con
una campaña y descartaba la otra: ninguna placa del finde encontraba su fila y
todas salían con "no encontré esta placa en el mailing".

Lo que fija este archivo:
  - se mide cuántas carillas verticales entran a lo ancho (1, 2, 3 o 4) y la
    hoja se parte en esas, sin solape -- así sirve para un díptico, un
    tríptico o una carilla suelta, no solo para este mailing;
  - una carilla vertical no se parte;
  - el ancho se aplica POR CARILLA, así un pliego no queda a la mitad de
    resolución que un mailing normal;
  - la vigencia que se le exige a una placa es la de SU carilla.
"""
import io

import pymupdf
import pytest
from PIL import Image

from app.services.rrss import imagenes
from app.services.rrss.comparador import comparar_elementos


# ---------------------------------------------------------------------------
# Reconocer un pliego
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ancho, alto, cuantas", [
    (595, 842, 1),     # A4 vertical: una carilla, no se toca
    (420, 595, 1),     # A5 vertical
    (908, 908, 1),     # cuadrada
    (800, 4000, 1),    # altísima
    (1257, 908, 2),    # el mailing real: dos A4 verticales al lado
    (842, 595, 2),     # A4 apaisado
    (1191, 842, 2),    # A3 apaisado = dos A4
    (1785, 842, 3),    # tríptico
    (2382, 842, 4),    # cuatro carillas
    (9999, 842, 4),    # más que eso no se parte: no es un pliego
])
def test_cuantas_carillas_entran_en_la_hoja(ancho, alto, cuantas):
    assert imagenes.carillas_en(ancho, alto) == cuantas


def test_una_hoja_sin_medidas_no_rompe():
    assert imagenes.carillas_en(0, 0) == 1


# ---------------------------------------------------------------------------
# Partirlo
# ---------------------------------------------------------------------------

def test_las_dos_carillas_parten_la_hoja_al_medio():
    hoja = Image.new("RGB", (1600, 1100), "white")
    izq, der = imagenes.carillas_de(hoja, 2)
    assert izq.size == (800, 1100)
    assert der.size == (800, 1100)


def test_un_triptico_sale_en_tres_y_no_pierde_una_columna():
    hoja = Image.new("RGB", (900, 400), "white")
    partes = imagenes.carillas_de(hoja, 3)
    assert [p.width for p in partes] == [300, 300, 300]
    assert sum(p.width for p in partes) == hoja.width


def test_un_ancho_impar_no_deja_una_franja_afuera():
    hoja = Image.new("RGB", (1001, 400), "white")
    partes = imagenes.carillas_de(hoja, 3)
    assert sum(p.width for p in partes) == hoja.width


def test_una_sola_carilla_devuelve_la_hoja_entera():
    hoja = Image.new("RGB", (600, 900), "white")
    assert imagenes.carillas_de(hoja, 1) == [hoja]


def test_las_carillas_no_se_solapan():
    """Con solape se duplicarían productos: cada carilla se lee por separado y
    sus productos se suman, nadie los deduplica."""
    hoja = Image.new("RGB", (1000, 500), "white")
    izq, der = imagenes.carillas_de(hoja, 2)
    assert izq.width + der.width == hoja.width


def test_cada_carilla_se_queda_con_su_contenido():
    hoja = Image.new("RGB", (400, 100), "white")
    for x in range(200):
        for y in range(100):
            hoja.putpixel((x, y), (255, 0, 0))     # izquierda roja
    for x in range(200, 400):
        for y in range(100):
            hoja.putpixel((x, y), (0, 0, 255))     # derecha azul
    izq, der = imagenes.carillas_de(hoja, 2)
    assert izq.getpixel((100, 50)) == (255, 0, 0)
    assert der.getpixel((100, 50)) == (0, 0, 255)


# ---------------------------------------------------------------------------
# El render, de punta a punta
# ---------------------------------------------------------------------------

def _pdf_de_una_hoja(ancho_pt: float, alto_pt: float) -> bytes:
    doc = pymupdf.open()
    doc.new_page(width=ancho_pt, height=alto_pt)
    datos = doc.tobytes()
    doc.close()
    return datos


def test_un_pliego_rinde_dos_carillas_con_la_resolucion_de_una():
    # 1257 x 908 pt es la hoja del mailing real.
    paginas = imagenes.paginas_del_mailing(
        _pdf_de_una_hoja(1257, 908), "application/pdf", "mailing.pdf")
    assert len(paginas) == 2
    # Cada carilla sale al ancho de página completo, no a la mitad: sin esto
    # la letra chica quedaba a ~90 DPI y el modelo no la leía.
    for carilla in paginas:
        assert carilla.width == pytest.approx(imagenes._ANCHO_PAGINA_PX, abs=2)


def test_una_carilla_vertical_sigue_siendo_una_sola_pagina():
    paginas = imagenes.paginas_del_mailing(
        _pdf_de_una_hoja(595, 842), "application/pdf", "mailing.pdf")
    assert len(paginas) == 1
    assert paginas[0].width == pytest.approx(imagenes._ANCHO_PAGINA_PX, abs=2)


def test_el_limite_de_paginas_cuenta_carillas_y_no_hojas():
    doc = pymupdf.open()
    for _ in range(imagenes.MAX_PAGINAS_MAILING // 2 + 1):
        doc.new_page(width=1257, height=908)
    datos = doc.tobytes()
    doc.close()
    with pytest.raises(imagenes.ArchivoInvalido) as err:
        imagenes.paginas_del_mailing(datos, "application/pdf", "mailing.pdf")
    assert str(imagenes.MAX_PAGINAS_MAILING) in str(err.value)


# ---------------------------------------------------------------------------
# La vigencia sale de la carilla del producto
# ---------------------------------------------------------------------------

def _placa(fecha: str) -> dict:
    """Lo mínimo que mira comparar_elementos. Lo único que varía es la fecha."""
    from app.services.rrss import reglas
    return {
        "fecha": fecha,
        "legal_bases": reglas.LEGAL_BASES,
        "legal_alcohol": "",
        "logo_campana_presente": True,
        "isotipo_presente": True,
        "imagen_producto": {
            "presente": True, "coincide_con_descripcion": True,
            "que_se_ve": "", "motivo": "",
        },
        "producto": {"descripcion": "Suprema de pollo AVESUR. Kg"},
        "cta": "", "otros_textos": [],
    }


_MAILING = {
    "fecha": "Del 23 al 30 de setiembre",
    "fechas_por_pagina": {0: "Del 23 al 30 de setiembre",
                          1: "Del jueves 24 al domingo 27 de setiembre"},
    "productos": [],
}


def _hay_error_de_fecha(filas) -> bool:
    return any(f["campo"] == "fecha" and f["estado"] != "ok" for f in filas)


def test_la_placa_del_finde_se_compara_contra_la_fecha_de_su_carilla():
    filas = comparar_elementos(
        _placa("Del jueves 24 al domingo 27 de setiembre"), _MAILING, {}, False, pagina=1)
    assert not _hay_error_de_fecha(filas)


def test_la_placa_del_finde_contra_la_carilla_equivocada_si_marca():
    filas = comparar_elementos(
        _placa("Del jueves 24 al domingo 27 de setiembre"), _MAILING, {}, False, pagina=0)
    assert _hay_error_de_fecha(filas)


def test_sin_carilla_conocida_cae_a_la_fecha_del_mailing():
    filas = comparar_elementos(_placa("Del 23 al 30 de setiembre"), _MAILING, {}, False)
    assert not _hay_error_de_fecha(filas)


def test_la_fecha_escrita_a_mano_le_gana_a_la_carilla():
    config = {"fecha": "Del jueves 24 al domingo 27 de setiembre"}
    filas = comparar_elementos(
        _placa("Del jueves 24 al domingo 27 de setiembre"), _MAILING, config, False, pagina=0)
    assert not _hay_error_de_fecha(filas)
