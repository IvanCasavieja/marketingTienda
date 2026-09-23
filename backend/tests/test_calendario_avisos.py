"""El aviso de las acciones del calendario, 10 días antes de que arranquen.

Pedido de Ivan (23/09/2026): "10 días antes de cada acción del calendario
promocional nos llegue a nuestras notificaciones". Lo que se fija acá:

  - se lee SOLO el calendario comercial (retail y header no avisan: el header
    se deriva de los otros dos y avisaría tres veces de lo mismo);
  - la ventana es "faltan 10 días o menos y todavía no arrancó", no "faltan
    exactamente 10": si el servidor estuvo caído un par de días, el aviso sale
    igual en vez de perderse;
  - un día que no existe en el mes (un 31 en un mes de 30) no rompe nada.
"""
from datetime import date

from app.services.calendario_avisos import DIAS_DE_AVISO, _mensaje, acciones_del_mes


def _mes(*barras_comerciales, retail=(), header=()):
    """Un mes con la forma que guarda el front: bandas -> filas -> barras."""
    def banda(nombre, barras):
        return {"id": f"bn-{nombre}", "nombre": nombre, "filas": [list(barras)]}
    return {
        "comercial": [banda("Mailing GRAL", barras_comerciales)] if barras_comerciales else [],
        "retail": [banda("HOME SLIDER (Retail Media)", retail)] if retail else [],
        "header": [banda("Posicion 1", header)] if header else [],
    }


def _barra(id_, nombre, desde, hasta=None):
    return {"id": id_, "nombre": nombre, "desde": desde, "hasta": hasta or desde, "color": None}


# ---------------------------------------------------------------------------
# Qué se lee
# ---------------------------------------------------------------------------

def test_solo_lee_el_calendario_comercial():
    datos = _mes(
        _barra("br-1", "Aniversario", 12),
        retail=[_barra("br-rm", "Marca X", 3)],
        header=[_barra("br-hd", "Banner", 5)],
    )
    acciones = acciones_del_mes("2026-10", datos)
    assert [a["nombre"] for a in acciones] == ["Aniversario"]


def test_la_fecha_sale_del_mes_y_del_dia_de_la_barra():
    acciones = acciones_del_mes("2026-10", _mes(_barra("br-1", "Aniversario", 12, 20)))
    assert acciones[0]["inicio"] == date(2026, 10, 12)
    assert acciones[0]["fin"] == date(2026, 10, 20)


def test_un_dia_que_no_existe_en_ese_mes_se_acomoda_al_ultimo():
    # Un 31 en un mes de 30 puede quedar de un import; antes reventaba.
    acciones = acciones_del_mes("2026-11", _mes(_barra("br-1", "Cierre", 31)))
    assert acciones[0]["inicio"] == date(2026, 11, 30)


def test_una_barra_sin_id_no_se_avisa():
    # Sin id no hay forma de deduplicar: avisaría todos los días.
    datos = _mes()
    datos["comercial"] = [{"id": "bn", "nombre": "X", "filas": [[{"nombre": "Sin id", "desde": 3}]]}]
    assert acciones_del_mes("2026-10", datos) == []


def test_una_accion_sin_nombre_igual_avisa():
    acciones = acciones_del_mes("2026-10", _mes(_barra("br-1", "   ", 4)))
    assert acciones[0]["nombre"] == "Sin nombre"


def test_un_mes_vacio_no_devuelve_nada():
    assert acciones_del_mes("2026-10", {}) == []


# ---------------------------------------------------------------------------
# La ventana de aviso
# ---------------------------------------------------------------------------

def _entra(inicio: date, hoy: date) -> bool:
    """La misma condición que usa revisar_avisos."""
    from datetime import timedelta
    return hoy <= inicio <= hoy + timedelta(days=DIAS_DE_AVISO)


def test_avisa_faltando_exactamente_diez_dias():
    assert _entra(date(2026, 10, 12), hoy=date(2026, 10, 2))


def test_avisa_tambien_si_el_servidor_estuvo_caido_y_faltan_menos():
    assert _entra(date(2026, 10, 12), hoy=date(2026, 10, 9))


def test_no_avisa_todavia_si_faltan_once():
    assert not _entra(date(2026, 10, 12), hoy=date(2026, 10, 1))


def test_no_avisa_una_accion_que_ya_arranco():
    assert not _entra(date(2026, 10, 12), hoy=date(2026, 10, 13))


def test_el_dia_que_arranca_todavia_entra():
    assert _entra(date(2026, 10, 12), hoy=date(2026, 10, 12))


# ---------------------------------------------------------------------------
# El texto
# ---------------------------------------------------------------------------

def test_el_mensaje_dice_cuanto_falta_y_la_fecha():
    accion = {"nombre": "Aniversario", "banda": "Mailing GRAL", "inicio": date(2026, 10, 12)}
    texto = _mensaje(accion, faltan=10)
    assert "Aniversario" in texto
    assert "Mailing GRAL" in texto
    assert "en 10 días" in texto
    assert "12/10" in texto


def test_el_mensaje_no_dice_en_1_dias():
    accion = {"nombre": "Aniversario", "banda": "", "inicio": date(2026, 10, 12)}
    assert "arranca mañana" in _mensaje(accion, faltan=1)
    assert "arranca hoy" in _mensaje(accion, faltan=0)
