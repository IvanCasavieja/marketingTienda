"""La foto de la placa se compara con la del mismo producto en el mailing.

El caso real (23/09/2026): seis placas de Rompe del Finde tenían las fotos
cruzadas —"Freidora sin Aceite INHAUS $2.490" con la foto de una jarra
eléctrica, y "Jarra Eléctrica INAHUS $1.390" con la foto de la freidora—. La
lectura de la placa sola ("¿la foto parece del producto?") las marcó en una
corrida y las dejó pasar en la siguiente, y cuando las marcaba era un AVISO.
Una foto de otro producto es un error de la placa, y tiene que salir siempre.

Lo que fija este archivo: qué hace `con_comparacion_de_fotos` con el resultado
de comparar las dos fotos, y cómo cambia el estado de la placa.
"""
from app.services.rrss.comparador import con_comparacion_de_fotos, estado_de_la_placa, _fila


def _aviso_de_la_lectura_sola():
    return _fila("imagen_coincide", "La foto es del producto", "placa",
                 "hervidor", "Freidora sin Aceite INHAUS", "revisar", "aviso", "CatTi duda")


def _otra_fila_ok():
    return _fila("descripcion", "Descripción", "producto", "x", "x", "ok", None)


def test_fotos_distintas_es_un_error_no_un_aviso():
    filas = con_comparacion_de_fotos([_otra_fila_ok()], {
        "mismo_producto": False,
        "que_hay_en_la_placa": "una jarra eléctrica de acero",
        "que_hay_en_el_mailing": "una freidora de aire negra",
        "motivo": "Son electrodomésticos distintos.",
    })
    foto = next(f for f in filas if f["campo"] == "imagen_coincide")
    assert foto["severidad"] == "error"
    assert foto["estado"] == "distinto"
    assert estado_de_la_placa(filas, idx=0) == "diferencias"


def test_la_nota_dice_que_hay_en_cada_lado():
    filas = con_comparacion_de_fotos([], {
        "mismo_producto": False,
        "que_hay_en_la_placa": "una jarra eléctrica",
        "que_hay_en_el_mailing": "una freidora de aire",
        "motivo": "",
    })
    nota = filas[0]["nota"]
    assert "jarra" in nota and "freidora" in nota


def test_los_lados_de_la_fila_son_lo_que_se_ve_no_los_textos():
    filas = con_comparacion_de_fotos([], {
        "mismo_producto": False, "que_hay_en_la_placa": "jarra", "que_hay_en_el_mailing": "freidora", "motivo": "",
    })
    assert filas[0]["placa"] == "jarra"
    assert filas[0]["mailing"] == "freidora"


def test_mismo_producto_retira_el_aviso_de_la_lectura_sola():
    """La comparación directa es la prueba más fuerte: si dice que es el mismo
    producto, la duda de la lectura sola no se sostiene."""
    filas = con_comparacion_de_fotos([_aviso_de_la_lectura_sola(), _otra_fila_ok()], {
        "mismo_producto": True, "que_hay_en_la_placa": "freidora", "que_hay_en_el_mailing": "freidora", "motivo": "",
    })
    assert not any(f["campo"] == "imagen_coincide" for f in filas)
    assert estado_de_la_placa(filas, idx=0) == "ok"


def test_fotos_distintas_reemplaza_el_aviso_por_el_error_sin_duplicar():
    filas = con_comparacion_de_fotos([_aviso_de_la_lectura_sola()], {
        "mismo_producto": False, "que_hay_en_la_placa": "jarra", "que_hay_en_el_mailing": "freidora", "motivo": "",
    })
    fotos = [f for f in filas if f["campo"] == "imagen_coincide"]
    assert len(fotos) == 1
    assert fotos[0]["severidad"] == "error"


def test_sin_dato_de_mismo_producto_se_asume_que_si():
    # Un resultado incompleto no acusa: acusar sin ver es peor que no ver.
    filas = con_comparacion_de_fotos([_aviso_de_la_lectura_sola()], {})
    assert not any(f["campo"] == "imagen_coincide" for f in filas)


def test_las_otras_filas_no_se_tocan():
    otra = _otra_fila_ok()
    filas = con_comparacion_de_fotos([otra], {"mismo_producto": False, "que_hay_en_la_placa": "a",
                                              "que_hay_en_el_mailing": "b", "motivo": ""})
    assert otra in filas
