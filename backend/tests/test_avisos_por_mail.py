"""Los avisos por mail (app/services/avisos_por_mail.py): puras.

El loop con la base (quién recibe, reintentos, avisos viejos) está en
test_tablero_agencia_api.py.
"""
from types import SimpleNamespace

from app.services import avisos_por_mail as apm


def aviso(**kw):
    base = {"origen_tipo": None, "origen_ref": None, "watchlist_item_id": None}
    base.update(kw)
    return SimpleNamespace(**base)


def test_el_boton_lleva_a_donde_lleva_la_campanita():
    assert apm.destino(aviso(origen_tipo="calendario_aviso", origen_ref="br-1:av-2")) == "/calendario?accion=br-1"
    assert apm.destino(aviso(origen_tipo="calendario_tarea", origen_ref="br-1:ta-9")) == "/calendario?accion=br-1"
    assert apm.destino(aviso(origen_tipo="calendario_accion", origen_ref="2026-09:br-7:t-10")) == "/calendario?accion=br-7"
    assert apm.destino(aviso(origen_tipo="calendario_entrega", origen_ref="br-1:ta-3:ve-4:hecha")) == "/entregas?tarea=ta-3"
    assert apm.destino(aviso(origen_tipo="colocacion_pedido", origen_ref="br-1:5")) == "/fotos"
    assert apm.destino(aviso(origen_tipo="colocacion_completa", origen_ref="br-1:5")) == "/calendario?accion=br-1&pestana=fotos"
    assert apm.destino(aviso(origen_tipo="campaign_alert")) == "/campaigns"
    assert apm.destino(aviso(watchlist_item_id=3)) == "/precios/listas"
    assert apm.destino(aviso(origen_tipo="algo_nuevo")) == "/home"


def test_el_asunto_es_el_aviso_cortado():
    assert apm.asunto("  Lanzar:   Mailing marzo  ") == "Lanzar: Mailing marzo"
    largo = apm.asunto("x" * 300)
    assert len(largo) == 90 and largo.endswith("…")
    assert apm.asunto("") == "Tenés un aviso nuevo en Core Tienda"


def test_el_mail_saluda_dice_el_aviso_y_lleva_el_boton():
    html, texto = apm.armar_mail("Lanzar: Mailing marzo arranca en 60 días.", "Valentina Pérez", "https://ct.test/calendario?accion=br-1&x=2")
    assert "Hola, Valentina" in html and "Lanzar: Mailing marzo arranca en 60 días." in html
    assert 'href="https://ct.test/calendario?accion=br-1&amp;x=2"' in html
    assert "/perfil" in html and "Apagalos" in html
    assert texto.startswith("Hola, Valentina:") and "https://ct.test/calendario?accion=br-1&x=2" in texto


def test_el_mail_no_deja_meter_html():
    html, _ = apm.armar_mail('<img src=x onerror="alert(1)">Comentó', "<b>Ana</b>", "https://ct.test/home")
    assert "<img" not in html and "&lt;img" in html
    assert "<b>Ana" not in html


def test_a_quien_le_sale():
    persona = dict(is_active=True, email="a@b.com", avisos_por_mail=True)
    assert apm.lo_quiere(SimpleNamespace(**persona))
    assert not apm.lo_quiere(SimpleNamespace(**{**persona, "avisos_por_mail": False}))
    assert not apm.lo_quiere(SimpleNamespace(**{**persona, "is_active": False}))
    assert not apm.lo_quiere(SimpleNamespace(**{**persona, "email": " "}))
    assert not apm.lo_quiere(None)


def test_lo_del_tablero_queda_solo_en_la_campanita():
    """Ivan, 19/11/2026: el tope es de 3.000 mails por mes y el tablero
    (entregas, rondas, aprobaciones, comentarios) se lo comería."""
    assert not apm.va_por_mail("calendario_entrega")
    for otro in ("calendario_tarea", "calendario_aviso", "calendario_accion", "colocacion_pedido", "campaign_alert", None):
        assert apm.va_por_mail(otro), otro
