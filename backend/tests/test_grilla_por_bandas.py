"""Que un cuadro corrido dos centésimas de milímetro no cambie de cenefa en silencio.

Bug real (Ivan, 16/09/2026). Ivan editó la plantilla "Cenefas 3xa4-202609-3xA4"
y el <<promoOferta>> de la tercera cenefa quedó en y=22,88 cm. El motor repartía
los cuadros en bandas por PASO FIJO --una división entera-- y el corte entre la
banda 2 y la banda 3 caía en y=22,882. Por 0,002 cm ese cuadro se fue a la banda
del medio: la banda 2 terminó con DOS <<promoOferta>> y la banda 3 sin ninguno.

Lo que se imprimió, en 36 de 440 cenefas de un mailing real:
  - el <<promoOferta>> de más se llenó con el producto del MEDIO y se dibujó
    encima del precio del TERCERO: dos números de productos distintos pisándose;
  - la tercera cenefa, si le tocaba un Combo, sacó el precio UNITARIO en vez del
    total. Un precio FALSO en góndola.

Nada de esto tiró un error. Estos tests están para que no pueda volver a pasar
callado.
"""
import pytest

from app.services.cenefas.component_renderer import _asignar_grilla, _detect_slot_bands

# Coordenadas REALES de la plantilla, tal cual las dejó el editor (cm).
# El diseño son tres cenefas apiladas en una A4; el paso entre bandas es 9,747.
Y_PROMO_ROTO = 22.88    # lo que quedó guardado el 16/09 y rompió el mailing
Y_PROMO_SANO = 23.72    # superpuesto con su <<precioOferta>>, como en el PPTX

_FILAS_3XA4 = [
    ("tipoOferta",     1.682,  [3.583, 13.330, 23.078]),
    ("vigencia",       9.501,  [3.815, 13.562, 23.310]),
    ("mecanica",       9.424,  [4.354, 14.022, 23.809]),
    ("descripcion",    9.384,  [4.862, 14.609, 24.356]),
    ("aclaracionUno", 12.485,  [8.184, 17.931, 27.679]),
    ("legales",       12.485,  [8.615, 18.363, 28.110]),
    ("precioOferta",   1.410,  [4.290, 14.190, 23.720]),
]


def _caja(var, x, y, alto=1.2):
    return {
        "id": f"{var}-{y}", "type": "text", "variable": var,
        "base_bounds": {"x": x, "y": y, "width": 6.0, "height": alto},
    }


def _hoja_3xa4(y_promo_tercero):
    """La plantilla 3xA4 de redexpres, con el <<promoOferta>> de la 3ra cenefa
    donde se lo pida el test."""
    comps = []
    for var, x, ys in _FILAS_3XA4:
        for y in ys:
            # Los cuadros de precio son cajas altas de verdad (4,4 cm para una
            # línea): es parte del caso, no un detalle.
            comps.append(_caja(var, x, y, alto=4.403 if var == "precioOferta" else 1.2))
    for y in (6.28, 16.15, y_promo_tercero):
        comps.append(_caja("promoOferta", 1.6, y, alto=4.403))
    return comps


def _promos_por_banda(bandas):
    return [sum(1 for c in b if c["variable"] == "promoOferta") for b in bandas]


def test_por_002_cm_el_promo_de_la_tercera_cenefa_imprimia_el_precio_de_otro_producto():
    # LA REGRESIÓN. Con y=22,88 el reparto por paso daba int(1,9998) = 1 y este
    # cuadro se iba a la banda del medio: la 2 con dos promos, la 3 con ninguna.
    bandas = _detect_slot_bands(_hoja_3xa4(Y_PROMO_ROTO))
    assert bandas is not None and len(bandas) == 3
    assert _promos_por_banda(bandas) == [1, 1, 1], (
        "el <<promoOferta>> de la tercera cenefa (y=22,88) cambió de banda por "
        "2 centésimas de milímetro: una cenefa imprime el precio de otro "
        f"producto. Promos por banda: {_promos_por_banda(bandas)}")
    # Y que sea EL suyo, no el del medio.
    ys_tercera = sorted(c["base_bounds"]["y"] for c in bandas[2]
                        if c["variable"] == "promoOferta")
    assert ys_tercera == [Y_PROMO_ROTO]


def test_con_el_promo_en_su_lugar_las_tres_bandas_siguen_con_uno_cada_una():
    # Control: el valor correcto (superpuesto con su precioOferta) también anda.
    bandas = _detect_slot_bands(_hoja_3xa4(Y_PROMO_SANO))
    assert bandas is not None and len(bandas) == 3
    assert _promos_por_banda(bandas) == [1, 1, 1]


@pytest.mark.parametrize("y_promo", [Y_PROMO_ROTO, Y_PROMO_SANO])
def test_cada_banda_se_queda_con_una_sola_cenefa(y_promo):
    # Lo que de verdad importa: que ninguna banda mezcle cuadros de dos cenefas.
    # Los cortes reales de la 3xA4 caen en ~13,2 y ~22,9 cm.
    bandas = _detect_slot_bands(_hoja_3xa4(y_promo))
    esperado = [{v for v, _, _ in _FILAS_3XA4} | {"promoOferta"}] * 3
    assert [{c["variable"] for c in b} for b in bandas] == esperado,         "alguna banda quedó sin una variable o con una repetida"
    for i, banda in enumerate(bandas):
        assert len(banda) == 8, f"la banda {i} se llevó cuadros de otra cenefa"


def test_una_variable_que_cae_dos_veces_en_la_misma_cenefa_no_arma_grilla():
    # La red de seguridad, para lo que el reparto por orden no puede resolver.
    # Acá <<promoOferta>> aparece 3 veces --una por cenefa, dice la plantilla--
    # pero dos están pegadas en la primera banda y ninguna en la segunda. El
    # orden no sirve (las apariciones no están separadas) y el reparto por paso
    # las dejaba juntas y seguía de largo: la banda 1 con dos promos y la 2 sin
    # ninguna, impreso y sin aviso. Ahora la grilla se rechaza.
    comps = []
    for var, x, ys in _FILAS_3XA4:
        for y in ys:
            comps.append(_caja(var, x, y))
    for y in (6.28, 7.50, 25.00):
        comps.append(_caja("promoOferta", 1.6, y))

    anclas = [c for c in comps if c["variable"] == "descripcion"]
    assert _asignar_grilla(comps, anclas, 3, 1) is None, (
        "la grilla dejó dos <<promoOferta>> en la misma cenefa y no lo rechazó")


def test_una_hoja_3xa4_sana_se_reparte_igual_que_siempre():
    # Fijar el comportamiento de referencia: tres bandas, cada cuadro en la
    # cenefa que le toca por su Y.
    bandas = _detect_slot_bands(_hoja_3xa4(Y_PROMO_SANO))
    limites = [(0.0, 13.2), (13.2, 22.9), (22.9, 29.7)]
    for i, banda in enumerate(bandas):
        desde, hasta = limites[i]
        ys = sorted(c["base_bounds"]["y"] for c in banda)
        assert all(desde <= y < hasta for y in ys),             f"la banda {i} se llevó cuadros de otra cenefa: {ys}"


def test_la_grilla_de_dos_columnas_sigue_funcionando():
    # La 6xA4 son 3 filas x 2 columnas, y la columna derecha arranca 2 mm más
    # abajo. Si el arreglo de las bandas rompiera esto, sería peor que el bug.
    comps = []
    for col, x0, corrimiento in ((0, 0.0, 0.0), (1, 10.5, 0.2)):
        for fila in range(3):
            y = fila * 9.9 + corrimiento
            comps.append(_caja("descripcion",  x0 + 0.5, y + 1.0))
            comps.append(_caja("precioOferta", x0 + 0.5, y + 3.0, alto=8.0))
            comps.append(_caja("legales",      x0 + 0.5, y + 5.0))
    bandas = _detect_slot_bands(comps)
    assert bandas is not None and len(bandas) == 6
    assert all(len(b) == 3 for b in bandas), [len(b) for b in bandas]
    # Orden de lectura: izquierda a derecha y después hacia abajo.
    xs = [min(c["base_bounds"]["x"] for c in b) for b in bandas]
    assert xs == [0.5, 11.0, 0.5, 11.0, 0.5, 11.0]
