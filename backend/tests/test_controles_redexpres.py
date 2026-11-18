"""Lanzar y Cierre de Redexpres (app/services/controles_redexpres.py): puras.

Lo que pasa con la base (crear la acción, a quién le llega cada aviso) está
en test_tablero_agencia_api.py.
"""
from datetime import date
from types import SimpleNamespace

from app.services import controles_redexpres as cr
from app.services import tipos_de_tarea
from app.services.calendario_avisos import mensaje_de_control

HOY = date(2026, 11, 18)


def barra(**kw):
    base = {"id": "br-1", "mundo": "redexpres", "seccion": "comercial", "banda": "ESPECIAL - CM", "desde": date(2027, 3, 1)}
    base.update(kw)
    return SimpleNamespace(**base)


def test_solo_las_acciones_de_redexpres_y_no_las_semanales():
    assert cr.aplica(barra())
    assert not cr.aplica(barra(mundo="tienda_inglesa"))
    assert not cr.aplica(barra(seccion="envio"))
    assert not cr.aplica(barra(banda="BOMBAS"))
    assert not cr.aplica(barra(banda="  super   FDS "))


def test_cargada_con_tiempo_las_tareas_van_ancladas_a_la_accion():
    lanzar, cierre = cr.tareas_nuevas(barra(), set(), 7, HOY)
    assert (lanzar["titulo"], lanzar["vence"], lanzar["ancla"], lanzar["ancla_dias"]) == ("Lanzar", date(2026, 12, 31), "inicio", -60)
    assert (cierre["titulo"], cierre["vence"], cierre["ancla"], cierre["ancla_dias"]) == ("Cierre", date(2027, 2, 1), "inicio", -28)
    assert lanzar["creado_por_id"] == 7 and lanzar["estado"] == "pendiente" and lanzar["orden"] < cierre["orden"]


def test_cargada_tarde_vencen_hoy_y_no_nacen_vencidas():
    lanzar, cierre = cr.tareas_nuevas(barra(desde=date(2026, 12, 8)), set(), None, HOY)
    assert lanzar["vence"] == HOY and lanzar["ancla"] is None
    assert cierre["vence"] == HOY and cierre["ancla"] is None
    # Con 40 días: Lanzar ya pasó, Cierre todavía no.
    lanzar, cierre = cr.tareas_nuevas(barra(desde=date(2026, 12, 28)), set(), None, HOY)
    assert lanzar["vence"] == HOY and cierre["vence"] == date(2026, 11, 30) and cierre["ancla"] == "inicio"


def test_una_tarea_que_ya_se_llama_asi_no_se_repite():
    assert [t["titulo"] for t in cr.tareas_nuevas(barra(), {"lanzar"}, None, HOY)] == ["Cierre"]
    assert cr.tareas_nuevas(barra(), {"lanzar", "cierre"}, None, HOY) == []


def test_los_tres_avisos_y_sin_repetir():
    avisos = cr.avisos_nuevos(barra(), set(), 7)
    assert [(a["control"], a["dias_antes"]) for a in avisos] == [("lanzar", 60), ("lanzar", 30), ("cierre", 28)]
    assert all(a["destinatarios"] == [] for a in avisos)
    assert [a["dias_antes"] for a in cr.avisos_nuevos(barra(), {("lanzar", 60)}, 7)] == [30, 28]


def test_los_ids_son_siempre_los_mismos():
    assert cr.id_de_tarea("br-1", "lanzar") == cr.id_de_tarea("br-1", "lanzar") != cr.id_de_tarea("br-2", "lanzar")
    assert cr.id_de_aviso("br-1", "lanzar", 60) != cr.id_de_aviso("br-1", "lanzar", 30)
    assert len(cr.id_de_tarea("x" * 64, "cierre")) <= 64


def test_el_mensaje_dice_que_control_es():
    texto = mensaje_de_control("lanzar", "Mailing marzo", "MAILING - 16 PAG EL PAIS", date(2027, 3, 1), date(2026, 12, 31))
    assert texto == "Lanzar: Mailing marzo (MAILING - 16 PAG EL PAIS) arranca en 60 días, el 01/03."
    assert mensaje_de_control("cierre", "X", "ESPECIAL - CM", date(2027, 3, 1), date(2027, 3, 1)).startswith("Cierre: X")


def test_las_piezas_de_valentina_solo_en_redexpres():
    for clave in ("imprenta", "video_monitores", "bases_escribana", "afiche_bombas"):
        assert tipos_de_tarea.vale_en(clave, "redexpres")
        assert not tipos_de_tarea.vale_en(clave, "tienda_inglesa")
    assert tipos_de_tarea.vale_en("banners", "redexpres") and tipos_de_tarea.vale_en("banners", "tienda_inglesa")
    assert not tipos_de_tarea.vale_en("no-existe", "redexpres")
    por_clave = {t["clave"]: t for t in tipos_de_tarea.para_la_pantalla()}
    assert por_clave["imprenta"]["mundos"] == ["redexpres"] and por_clave["banners"]["mundos"] is None
