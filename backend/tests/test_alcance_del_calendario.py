"""Hasta dónde ve el calendario cada persona (0070, app/core/alcance.py).

Pedido de Ivan (16/11/2026): el calendario lo ve mucha gente y lo quiere
empezar a cerrar. Cada usuario tiene un alcance: No lo ve / 1 mes / 2 meses /
12 meses / Todo. N meses = el mes actual y los N−1 siguientes, más los
últimos 7 días del mes anterior, en hora de Uruguay. La agencia arranca en
"No lo ve"; el equipo, en "Todo".

Sin base: lo que pasa con la API de punta a punta está en
test_tablero_agencia_api.py.
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import alcance


def _u(alc=None, externo=False):
    return SimpleNamespace(id=1, es_externo=externo, calendario_alcance=alc)


# ---------------------------------------------------------------------------
# Por defecto
# ---------------------------------------------------------------------------

def test_por_defecto_la_agencia_no_lo_ve_y_el_equipo_lo_ve_todo():
    assert alcance.por_defecto(True) == "nada"
    assert alcance.por_defecto(False) == "todo"
    # Sin valor guardado (o uno que no existe): el de su tipo de cuenta.
    assert alcance.alcance_de(_u(None, externo=True)) == "nada"
    assert alcance.alcance_de(_u(None, externo=False)) == "todo"
    assert alcance.alcance_de(_u("cualquiera", externo=True)) == "nada"
    assert alcance.alcance_de(_u("2m", externo=True)) == "2m"


def test_no_lo_ve_se_frena_con_403():
    with pytest.raises(HTTPException) as e:
        alcance.exigir_calendario(_u("nada"))
    assert e.value.status_code == 403
    alcance.exigir_calendario(_u("1m"))
    alcance.exigir_calendario(_u("todo"))
    assert not alcance.ve_el_calendario(_u("nada"))
    assert alcance.es_limitado(_u("12m")) and not alcance.es_limitado(_u("todo"))


# ---------------------------------------------------------------------------
# La ventana
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hoy,alc,esperado", [
    # 1 mes: el mes actual, más los últimos 7 días del anterior.
    (date(2026, 11, 16), "1m", (date(2026, 10, 25), date(2026, 11, 30))),
    (date(2026, 11, 1), "1m", (date(2026, 10, 25), date(2026, 11, 30))),
    (date(2026, 11, 30), "1m", (date(2026, 10, 25), date(2026, 11, 30))),
    # 2 meses: el actual y el que viene.
    (date(2026, 11, 16), "2m", (date(2026, 10, 25), date(2026, 12, 31))),
    # Cambio de año: diciembre con 2 meses termina en enero del siguiente.
    (date(2026, 12, 10), "2m", (date(2026, 11, 24), date(2027, 1, 31))),
    # Enero arranca en diciembre del año anterior.
    (date(2027, 1, 5), "1m", (date(2026, 12, 25), date(2027, 1, 31))),
    # Marzo: los 7 últimos días de febrero (bisiesto y no).
    (date(2028, 3, 3), "1m", (date(2028, 2, 23), date(2028, 3, 31))),
    (date(2027, 3, 3), "1m", (date(2027, 2, 22), date(2027, 3, 31))),
    # 2 meses desde enero: febrero entero, bisiesto.
    (date(2028, 1, 20), "2m", (date(2027, 12, 25), date(2028, 2, 29))),
    # 12 meses: el actual y los 11 que siguen.
    (date(2026, 11, 16), "12m", (date(2026, 10, 25), date(2027, 10, 31))),
    (date(2026, 1, 1), "12m", (date(2025, 12, 25), date(2026, 12, 31))),
])
def test_la_ventana_de_cada_alcance(hoy, alc, esperado):
    assert alcance.ventana_de_alcance(hoy, alc) == esperado


def test_todo_es_sin_limite_y_nada_es_vacia():
    assert alcance.ventana_de_alcance(date(2026, 11, 16), "todo") is None
    v = alcance.ventana_de_alcance(date(2026, 11, 16), "nada")
    assert v == alcance.VACIA
    # Con "Todo" toca cualquier fecha (2025, 2027, 2099...).
    for desde in (date(2025, 1, 1), date(2027, 6, 1), date(2099, 12, 1)):
        assert alcance.toca(desde, desde, None)
    # Con "No lo ve", ninguna.
    assert not alcance.toca(date(2026, 11, 16), date(2026, 11, 16), v)
    assert alcance.meses_de(None) is None
    assert alcance.meses_de(v) == []


def test_hoy_es_el_de_montevideo_y_no_el_de_greenwich():
    # 30/11 a las 22:30 en Montevideo = 1/12 01:30 en UTC: sigue siendo noviembre.
    ahora_utc = datetime(2026, 12, 1, 1, 30, tzinfo=timezone.utc)
    assert alcance.hoy_en_uruguay(ahora_utc) == date(2026, 11, 30)
    assert alcance.ventana_de(_u("1m"), ahora_utc) == (date(2026, 10, 25), date(2026, 11, 30))
    # A las 3:30 UTC ya es 1/12 también en Montevideo.
    assert alcance.ventana_de(_u("1m"), datetime(2026, 12, 1, 3, 30, tzinfo=timezone.utc)) == (
        date(2026, 11, 24), date(2026, 12, 31))


V = (date(2026, 10, 25), date(2026, 12, 31))  # 2 meses desde noviembre


@pytest.mark.parametrize("desde,hasta,esperado", [
    (date(2026, 11, 15), date(2026, 11, 20), True),     # este mes
    (date(2026, 12, 31), date(2027, 1, 5), True),       # arranca el último día
    (date(2026, 10, 1), date(2026, 10, 25), True),      # termina justo el primero
    (date(2026, 9, 1), date(2027, 3, 1), True),         # la cruza entera
    (date(2027, 1, 1), date(2027, 1, 10), False),       # el mes que sigue al alcance
    (date(2026, 10, 1), date(2026, 10, 24), False),     # antes de los 7 días
    (date(2026, 11, 20), date(2026, 11, 10), True),     # fechas al revés: un día, adentro
])
def test_que_acciones_tocan_la_ventana(desde, hasta, esperado):
    assert alcance.toca(desde, hasta, V) is esperado


def test_los_meses_de_la_ventana_para_retail_media():
    assert alcance.meses_de(V) == ["2026-10", "2026-11", "2026-12"]
    assert alcance.meses_de((date(2026, 12, 25), date(2027, 1, 31))) == ["2026-12", "2027-01"]
