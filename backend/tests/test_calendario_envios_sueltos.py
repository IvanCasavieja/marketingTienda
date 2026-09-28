"""Los envíos sueltos: un mailing, un WhatsApp o una push sin una acción detrás.

Pedido de Ivan (28/09/2026): "de repente no hay una promoción y tenemos que
salir con un email marketing, con una push, con un WhatsApp, y no podemos
hacerlo". Son barras de la sección 'envio'. Lo que se fija acá es lo que el
servidor exige para guardarlos, sin base: que el canal sea uno de los tres,
que salgan un solo día, y que formato, hora y estado sean solo de ellos.
"""
from datetime import date

import pytest
from pydantic import ValidationError

from app.api.routes.calendario import _CON_AVISOS, BarraCambios, BarraNueva, cambios_de_barra
from app.services.calendario_avisos import mensaje


def _envio(**extra):
    base = {
        "id": "br-envio-1", "seccion": "envio", "banda": "email", "nombre": "Mailing Día de la Madre",
        "desde": date(2026, 10, 12), "hasta": date(2026, 10, 12), "formato": "Mailing digital", "hora": "10:30",
    }
    return BarraNueva(**{**base, **extra})


def test_un_envio_suelto_valido():
    e = _envio()
    assert (e.banda, e.formato, e.hora) == ("email", "Mailing digital", "10:30")


def test_arranca_pendiente():
    assert _envio().estado == "pendiente"


@pytest.mark.parametrize("canal", ["email", "whatsapp", "push"])
def test_los_tres_canales(canal):
    assert _envio(banda=canal).banda == canal


def test_un_canal_que_no_existe_no_se_guarda():
    with pytest.raises(ValidationError):
        _envio(banda="fax")


def test_un_envio_sale_un_solo_dia():
    with pytest.raises(ValidationError):
        _envio(hasta=date(2026, 10, 13))


def test_una_hora_mal_escrita_no_se_guarda():
    with pytest.raises(ValidationError):
        _envio(hora="25:00")


def test_en_una_accion_el_formato_la_hora_y_el_estado_no_se_guardan():
    # En una acción esas cosas las lleva cada pieza, no la barra.
    accion = BarraNueva(
        id="br-1", seccion="comercial", banda="MEGA EVENTO", nombre="Fiesta",
        desde=date(2026, 10, 1), hasta=date(2026, 10, 9),
        formato="Mailing digital", hora="10:00", estado="aprobado",
    )
    assert (accion.formato, accion.hora, accion.estado) == (None, None, None)


# ---------------------------------------------------------------------------
# Editar (PATCH): qué se escribe
# ---------------------------------------------------------------------------

_DIA = date(2026, 10, 12)


def _cambios(seccion, **campos):
    return cambios_de_barra(seccion, BarraCambios(**campos), _DIA, _DIA)


def test_a_un_envio_se_le_puede_sacar_la_hora():
    assert _cambios("envio", hora=None) == {"hora": None}


def test_y_el_formato():
    assert _cambios("envio", formato=None) == {"formato": None}


def test_cambiar_de_canal_sin_decir_el_formato_lo_vacia():
    # "Mailing digital" no es una push: se muestra el primero del canal nuevo.
    assert _cambios("envio", banda="push") == {"banda": "push", "formato": None}


def test_cambiar_de_canal_con_formato_lo_respeta():
    assert _cambios("envio", banda="push", formato="Push app") == {"banda": "push", "formato": "Push app"}


def test_un_canal_que_no_existe_no_se_edita():
    with pytest.raises(ValueError):
        _cambios("envio", banda="fax")


def test_mover_solo_el_inicio_de_un_envio_no_se_permite():
    with pytest.raises(ValueError):
        _cambios("envio", desde=date(2026, 10, 14))


def test_moverlo_entero_de_dia_si():
    nuevo = date(2026, 10, 14)
    assert _cambios("envio", desde=nuevo, hasta=nuevo) == {"desde": nuevo, "hasta": nuevo}


def test_el_estado_no_se_vacia():
    assert _cambios("envio", estado=None) == {}


def test_en_una_accion_formato_hora_y_estado_no_se_escriben():
    assert _cambios("comercial", formato="Mailing digital", hora="10:00", estado="aprobado", nombre="Fiesta") == {"nombre": "Fiesta"}


def test_una_accion_puede_cruzar_de_mes():
    fin = date(2026, 11, 5)
    assert _cambios("comercial", hasta=fin) == {"hasta": fin}


def test_el_nombre_no_se_puede_vaciar():
    with pytest.raises(ValueError):
        _cambios("comercial", nombre=None)


def test_los_envios_aceptan_avisos():
    assert "envio" in _CON_AVISOS and "comercial" in _CON_AVISOS


def test_el_aviso_de_un_envio_dice_sale_y_el_canal():
    texto = mensaje("Mailing Día de la Madre", "email", date(2026, 10, 12), date(2026, 10, 2), "Ivan", es_envio=True)
    assert "sale en 10 días" in texto
    assert "(Email)" in texto
    assert "arranca" not in texto


def test_el_aviso_de_una_accion_sigue_diciendo_arranca():
    assert "arranca en 10 días" in mensaje("Fiesta", "MEGA EVENTO", date(2026, 10, 12), date(2026, 10, 2), None)
