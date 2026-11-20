"""Lanzar, el control de Redexpres (app/services/controles_redexpres.py): puras.

Lo que pasa con la base (crear la acción, a quién le llega cada aviso) está
en test_tablero_agencia_api.py. Desde el 20/11/2026 el Cierre es manual y los
Super FDS no llevan nada.
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


def test_solo_lanzar_anclada_a_la_accion():
    (lanzar,) = cr.tareas_nuevas(barra(), set(), 7, HOY)
    assert (lanzar["titulo"], lanzar["vence"], lanzar["ancla"], lanzar["ancla_dias"]) == ("Lanzar", date(2026, 12, 31), "inicio", -60)
    assert lanzar["creado_por_id"] == 7 and lanzar["estado"] == "pendiente"


def test_el_cierre_ya_no_es_automatico():
    # Ivan (20/11/2026): "se creará manual y solo manual".
    assert [t["titulo"] for t in cr.tareas_nuevas(barra(), set(), None, HOY)] == ["Lanzar"]
    assert all(a["control"] == "lanzar" for a in cr.avisos_nuevos(barra(), set(), None))
    assert set(cr.NOMBRE_DEL_CONTROL) == {"lanzar"}


def test_cargada_tarde_vence_hoy_y_no_nace_vencida():
    (lanzar,) = cr.tareas_nuevas(barra(desde=date(2026, 12, 8)), set(), None, HOY)
    assert lanzar["vence"] == HOY and lanzar["ancla"] is None


def test_una_tarea_que_ya_se_llama_asi_no_se_repite():
    assert cr.tareas_nuevas(barra(), {"lanzar"}, None, HOY) == []


def test_los_dos_avisos_y_sin_repetir():
    avisos = cr.avisos_nuevos(barra(), set(), 7)
    assert [(a["control"], a["dias_antes"]) for a in avisos] == [("lanzar", 60), ("lanzar", 30)]
    assert all(a["destinatarios"] == [] for a in avisos)
    assert [a["dias_antes"] for a in cr.avisos_nuevos(barra(), {("lanzar", 60)}, 7)] == [30]


def test_los_ids_son_siempre_los_mismos():
    assert cr.id_de_tarea("br-1", "lanzar") == cr.id_de_tarea("br-1", "lanzar") != cr.id_de_tarea("br-2", "lanzar")
    assert cr.id_de_aviso("br-1", "lanzar", 60) != cr.id_de_aviso("br-1", "lanzar", 30)
    assert len(cr.id_de_tarea("x" * 64, "lanzar")) <= 64


def test_el_mensaje_dice_que_control_es():
    texto = mensaje_de_control("lanzar", "Mailing marzo", "MAILING - 16 PAG EL PAIS", date(2027, 3, 1), date(2026, 12, 31))
    assert texto == "Lanzar: Mailing marzo (MAILING - 16 PAG EL PAIS) arranca en 60 días, el 01/03."


def test_las_piezas_de_valentina_solo_en_redexpres():
    for clave in ("imprenta", "video_monitores", "bases_escribana", "afiche_bombas"):
        assert tipos_de_tarea.vale_en(clave, "redexpres")
        assert not tipos_de_tarea.vale_en(clave, "tienda_inglesa")
    assert tipos_de_tarea.vale_en("banners", "redexpres") and tipos_de_tarea.vale_en("banners", "tienda_inglesa")
    assert not tipos_de_tarea.vale_en("no-existe", "redexpres")
    por_clave = {t["clave"]: t for t in tipos_de_tarea.para_la_pantalla()}
    assert por_clave["imprenta"]["mundos"] == ["redexpres"] and por_clave["banners"]["mundos"] is None
