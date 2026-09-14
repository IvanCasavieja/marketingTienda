"""Fija que un cuadro suelto no tumbe la detección de bandas de una hoja multi-cenefa.

Bug real (Ivan, 14/09/2026), Rompe Precios Congelados 3xA4: las tres cenefas de la
hoja salían con el MISMO producto, y encima no funcionaba el "muevo uno, muevo
todos" (los hermanos entre bandas se calculan a partir de las bandas).

Una sola causa para los dos síntomas. `_detect_slot_bands` sacaba la cantidad de
slots del GCD de cuántas veces aparece cada variable. En esa plantilla seis
variables aparecían 3 veces y `decimalPrecioBanco` UNA sola --el diseño tiene ese
cuadro en la primera cenefa y no en las otras dos--, así que
GCD(3,3,3,3,3,3,1) = 1 y la hoja entera se trataba como un producto.

Medido sobre las 22 plantillas de producción: el cambio mueve SOLO a ésta
(None -> 3) y deja a las otras 21 exactamente igual.
"""
from app.services.cenefas.component_renderer import _detect_slot_bands

ALTO_BANDA = 9.9   # 3xA4: tres franjas de 9,9 cm en una A4


def _caja(var, x, y):
    return {
        "id": f"{var}-{x}-{y}", "type": "text", "variable": var,
        "base_bounds": {"x": x, "y": y, "width": 6.0, "height": 1.2},
    }


def _hoja_3xa4(con_huerfano: bool):
    """Tres cenefas apiladas. El huérfano existe solo en la primera."""
    comps = []
    for banda in range(3):
        y = banda * ALTO_BANDA
        comps.append(_caja("descripcion",         1.0, y + 1.0))
        comps.append(_caja("codigo",              1.0, y + 2.5))
        comps.append(_caja("precioOferta",        1.0, y + 4.0))
        comps.append(_caja("precioRegular",       1.0, y + 5.5))
        comps.append(_caja("precioBanco",        13.0, y + 4.0))
        comps.append(_caja("decimalPrecioOferta", 8.0, y + 4.0))
    if con_huerfano:
        comps.append(_caja("decimalPrecioBanco", 18.63, 5.68))   # solo en la banda 0
    return comps


def test_sin_huerfano_detecta_las_tres_bandas():
    # Control: si esto falla, el test de abajo no prueba lo que dice probar.
    bandas = _detect_slot_bands(_hoja_3xa4(con_huerfano=False))
    assert bandas is not None and len(bandas) == 3


def test_un_cuadro_suelto_no_tumba_la_deteccion():
    # La regresión: antes esto devolvía None y las tres cenefas salían con el
    # mismo producto.
    bandas = _detect_slot_bands(_hoja_3xa4(con_huerfano=True))
    assert bandas is not None, (
        "un solo cuadro que aparece en una sola cenefa dejó la hoja sin bandas: "
        "las tres van a imprimir el mismo producto")
    assert len(bandas) == 3


def test_el_cuadro_suelto_cae_en_la_banda_que_le_toca_por_posicion():
    bandas = _detect_slot_bands(_hoja_3xa4(con_huerfano=True))
    dueña = [i for i, b in enumerate(bandas)
             if any(c.get("variable") == "decimalPrecioBanco" for c in b)]
    assert dueña == [0], f"el huérfano (y=5,68) tiene que quedar en la primera banda, quedó en {dueña}"


def test_cada_banda_se_queda_con_su_producto():
    # Lo que de verdad importa: que no se mezclen datos de cenefas distintas.
    bandas = _detect_slot_bands(_hoja_3xa4(con_huerfano=True))
    for i, banda in enumerate(bandas):
        ys = [c["base_bounds"]["y"] for c in banda]
        assert all(i * ALTO_BANDA <= y < (i + 1) * ALTO_BANDA for y in ys), \
            f"la banda {i} se llevó cuadros de otra cenefa: {sorted(ys)}"


def test_una_hoja_de_un_solo_producto_sigue_sin_bandas():
    # Un A4 normal no tiene que inventarse bandas.
    comps = [_caja("descripcion", 1.0, 1.0), _caja("precioOferta", 1.0, 4.0),
             _caja("codigo", 1.0, 2.5)]
    assert _detect_slot_bands(comps) is None


def test_un_precio_partido_en_dos_no_duplica_las_cenefas():
    # precioOferta dos veces por cenefa (entero + decimal apuntando a la misma
    # variable) son 6 apariciones en 3 cenefas: siguen siendo 3, no 6.
    comps = _hoja_3xa4(con_huerfano=False)
    for banda in range(3):
        comps.append(_caja("precioOferta", 9.0, banda * ALTO_BANDA + 4.0))
    bandas = _detect_slot_bands(comps)
    assert bandas is not None and len(bandas) == 3
