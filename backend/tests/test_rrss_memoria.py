"""Las carillas del mailing viven en JPEG, no crudas.

El 23/09/2026 Render mató el servicio por memoria: "exceeded its memory limit".
Medido sobre el mailing del 24 al 27 (un PDF de 22 MB, 2 hojas, 4 carillas),
prepararlo subía 276 MB con picos de 418, y el servicio tiene 512. Una carilla
de 1600 px son 11 MB en crudo y unos 600 KB en JPEG.

Lo que fija este archivo: que las carillas se guarden comprimidas, que abrirlas
tenga un tope --así el pico no crece con el tamaño del mailing-- y que se
puedan soltar cuando ya no hacen falta.
"""
import pytest
from PIL import Image

from app.services.rrss.imagenes import Carillas


def _paginas(cuantas: int, ancho: int = 400, alto: int = 300) -> list[Image.Image]:
    return [Image.new("RGB", (ancho, alto), (i * 20 % 256, 100, 200)) for i in range(cuantas)]


# ---------------------------------------------------------------------------
# Se comporta como la lista que reemplaza
# ---------------------------------------------------------------------------

def test_tiene_tantas_carillas_como_paginas():
    assert len(Carillas(_paginas(5))) == 5


def test_se_pide_por_indice_y_devuelve_la_imagen():
    c = Carillas(_paginas(3))
    assert c[1].size == (400, 300)


def test_un_indice_negativo_cuenta_desde_el_final():
    c = Carillas(_paginas(3))
    assert c[-1].getpixel((0, 0)) == c[2].getpixel((0, 0))


def test_se_puede_recorrer():
    assert [im.size for im in Carillas(_paginas(3))] == [(400, 300)] * 3


def test_cada_carilla_conserva_lo_suyo():
    c = Carillas(_paginas(3))
    # El JPEG no es exacto, pero el canal verde (100) y el azul (200) se mantienen.
    for i in range(3):
        r, g, b = c[i].getpixel((10, 10))
        assert abs(g - 100) < 12 and abs(b - 200) < 12


# ---------------------------------------------------------------------------
# Lo que ahorra
# ---------------------------------------------------------------------------

def test_guarda_los_jpeg_y_no_las_imagenes_crudas():
    paginas = _paginas(4, 1600, 2300)
    crudo = sum(p.width * p.height * 3 for p in paginas)
    c = Carillas(paginas)
    comprimido = sum(len(j) for j in c.jpegs)
    assert comprimido < crudo / 10, f"{comprimido} vs {crudo}"


def test_los_tamanos_quedan_a_mano_sin_abrir_nada():
    c = Carillas(_paginas(3, 800, 600))
    assert c.tamanos == [(800, 600)] * 3
    assert c._cajon == {}     # preguntarle el tamaño no abrió ninguna


def test_no_hay_mas_carillas_abiertas_que_el_tope():
    c = Carillas(_paginas(10), abiertas=3)
    for i in range(10):
        _ = c[i]
    assert len(c._cajon) == 3


def test_el_tope_nunca_es_cero():
    c = Carillas(_paginas(2), abiertas=0)
    _ = c[0]
    assert len(c._cajon) == 1


def test_pedir_dos_veces_la_misma_no_la_abre_dos_veces():
    c = Carillas(_paginas(3), abiertas=2)
    primera = c[0]
    assert c[0] is primera


def test_la_mas_vieja_es_la_que_sale_del_cajon():
    c = Carillas(_paginas(3), abiertas=2)
    _ = c[0]
    _ = c[1]
    _ = c[0]      # la 0 vuelve a ser la más reciente
    _ = c[2]      # entra la 2: tiene que salir la 1
    assert set(c._cajon) == {0, 2}


def test_liberar_deja_los_jpeg_y_cierra_lo_abierto():
    c = Carillas(_paginas(4))
    _ = c[0]
    _ = c[1]
    assert c._cajon
    c.liberar()
    assert c._cajon == {}
    assert len(c.jpegs) == 4


def test_despues_de_liberar_se_puede_volver_a_pedir():
    c = Carillas(_paginas(2))
    _ = c[0]
    c.liberar()
    assert c[0].size == (400, 300)


@pytest.mark.parametrize("cuantas", [1, 2, 12])
def test_el_tope_de_abiertas_no_depende_del_tamano_del_mailing(cuantas):
    """Es el punto de todo esto: un mailing de 12 carillas no puede costar seis
    veces más memoria que uno de 2."""
    c = Carillas(_paginas(cuantas), abiertas=4)
    for i in range(cuantas):
        _ = c[i]
    assert len(c._cajon) <= 4
