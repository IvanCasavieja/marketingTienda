# -*- coding: utf-8 -*-
"""Relleno de capacidad POR SEGMENTO.

Bug real (18/09/2026, reportado por Ivan): en la plantilla nueva de Alemania
("Fiesta Alemania-202608-A4") el bloque del precio es UN cuadro de tres
segmentos --unidadMoneda 60 pt, precioOferta 140 pt, decimalPrecioOferta
36 pt-- y el relleno de capacidad devolvia un solo string por cuadro, medido
con el cuerpo maximo de los segmentos (140). El decimal nunca se dibujaba con
su cuerpo:

    "estoy poniendo para rellenar con x en la plataforma ya que el primer
     precio que tengo de oferta no tiene decimal, y no tengo como verlo ni
     como ordenarlo porque el relleno de x no funciona en esa variable"

El caso de Alemania es el fixture de todos estos tests: la caja mide 13,209 cm
de ancho, que es la medida de la plantilla que esta en produccion.
"""
from app.services.cenefas.capacidad import (
    capacidad_por_componente,
    capacidad_por_segmento,
    segmentos_por_componente,
)


def _cuadro_alemania() -> dict:
    """El bloque del precio de Alemania: moneda + precio + decimal en una caja."""
    return {
        "id": "precio-alemania",
        "type": "text",
        "base_bounds": {"width": 13.209, "height": 5.5},
        "style": {"font_family": "Impact", "font_size": 140},
        "segments": [
            {"type": "variable", "value": "unidadMoneda",        "style": {"font_size": 60}},
            {"type": "variable", "value": "precioOferta",        "style": {"font_size": 140}},
            {"type": "variable", "value": "decimalPrecioOferta", "style": {"font_size": 36}},
        ],
    }


def test_el_decimal_recibe_coma_y_dos_cifras():
    """Lo que Ivan no podia ver: el decimal ahora tiene su propio relleno.

    Son siempre 3 caracteres --la coma y dos cifras-- porque ese es el peor
    caso REAL de un decimal, no "los que entren en la caja".
    """
    rellenos = capacidad_por_segmento(_cuadro_alemania())
    decimal = rellenos[2]
    assert decimal != ""
    assert len(decimal) == 3
    assert decimal.startswith(",")
    assert decimal[1:].isdigit()


def test_la_moneda_se_rellena_con_su_peor_caso_y_no_con_digitos():
    """unidadMoneda solo puede valer "$" o "U$S": el peor caso es "U$S"."""
    rellenos = capacidad_por_segmento(_cuadro_alemania())
    assert rellenos[0] == "U$S"


def test_el_precio_recibe_menos_digitos_por_compartir_la_caja():
    """La cuenta que importa: cuantos digitos entran AL LADO del simbolo y del
    decimal, no cuantos entrarian si el precio tuviera la caja para el solo."""
    comp = _cuadro_alemania()
    solo = capacidad_por_componente({"components": [comp]})[comp["id"]]
    compartido = capacidad_por_segmento(comp)[1]

    assert compartido.isdigit()
    assert len(compartido) >= 1
    assert len(compartido) < len(solo)


def test_cada_segmento_se_mide_con_su_propio_cuerpo():
    """Con el cuerpo maximo (140) el decimal no entraria ni una vez; con el
    suyo (36) entra comodo. Es exactamente el bloque que se reemplazo."""
    comp = _cuadro_alemania()
    chico = capacidad_por_segmento(comp)

    # Mismo cuadro pero con el decimal declarado a 140: al ocupar mucho mas,
    # al precio le tiene que quedar menos lugar.
    comp_grande = _cuadro_alemania()
    comp_grande["segments"][2]["style"]["font_size"] = 140
    grande = capacidad_por_segmento(comp_grande)

    assert len(grande[1]) < len(chico[1])


def test_un_cuadro_de_una_sola_variable_no_devuelve_segmentos():
    """Los cuadros de siempre no cambian: el front los sigue leyendo de
    `capacidad` y `segmentos` ni los menciona."""
    suelto = {
        "id": "precio-suelto",
        "type": "text",
        "variable": "precioOferta",
        "base_bounds": {"width": 10.0, "height": 5.0},
        "style": {"font_family": "Impact", "font_size": 140},
    }
    assert capacidad_por_segmento(suelto) is None

    salida = segmentos_por_componente({"components": [suelto, _cuadro_alemania()]})
    assert "precio-suelto" not in salida
    assert "precio-alemania" in salida


def test_capacidad_por_componente_sigue_devolviendo_lo_de_siempre():
    """El contrato viejo no se toca: `capacidad` sigue siendo un string por
    cuadro, para todos los cuadros rellenables."""
    comp = _cuadro_alemania()
    vieja = capacidad_por_componente({"components": [comp]})
    assert isinstance(vieja[comp["id"]], str)
    assert vieja[comp["id"]].isdigit()


def test_los_segmentos_van_en_el_orden_del_cuadro():
    comp = _cuadro_alemania()
    rellenos = segmentos_por_componente({"components": [comp]})[comp["id"]]
    assert len(rellenos) == len(comp["segments"])
    assert rellenos[0] == "U$S"
    assert rellenos[1].isdigit()
    assert rellenos[2].startswith(",")


def test_los_pedazos_estaticos_se_miden_tal_cual():
    """Un texto fijo del diseno ("Comprando 2 ") ya es su propio peor caso, y
    ademas le come ancho al precio."""
    comp = {
        "id": "comprando",
        "type": "text",
        "base_bounds": {"width": 13.209, "height": 5.0},
        "style": {"font_family": "Impact", "font_size": 90},
        "segments": [
            {"type": "static",   "value": "Comprando 2 "},
            {"type": "variable", "value": "precioOferta", "style": {"font_size": 90}},
        ],
    }
    rellenos = capacidad_por_segmento(comp)
    assert rellenos[0] == "Comprando 2 "
    assert rellenos[1].isdigit()

    sin_estatico = capacidad_por_componente({"components": [comp]})[comp["id"]]
    assert len(rellenos[1]) < len(sin_estatico)


def test_dos_segmentos_variables_reparten_parejo():
    """Decision documentada: si hay mas de un segmento de largo libre, el
    sobrante se parte en partes iguales."""
    comp = {
        "id": "dos-precios",
        "type": "text",
        "base_bounds": {"width": 13.209, "height": 5.0},
        "style": {"font_family": "Impact", "font_size": 100},
        "segments": [
            {"type": "variable", "value": "precioOferta",  "style": {"font_size": 100}},
            {"type": "static",   "value": " / "},
            {"type": "variable", "value": "precioRegular", "style": {"font_size": 100}},
        ],
    }
    rellenos = capacidad_por_segmento(comp)
    assert rellenos[0].isdigit()
    assert rellenos[2].isdigit()
    assert len(rellenos[0]) == len(rellenos[2])


def test_un_segmento_nunca_queda_vacio_aunque_no_entre_nada():
    """Un segmento vacio en el preview se lee como "esta variable no existe",
    que es justo la confusion que el relleno viene a sacar."""
    comp = _cuadro_alemania()
    comp["base_bounds"]["width"] = 2.0
    rellenos = capacidad_por_segmento(comp)
    assert all(r for r in rellenos)
    assert rellenos[2].startswith(",")
