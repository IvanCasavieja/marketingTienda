"""Qué avisos muestra la campanita a cada persona.

Cada aviso se vuelve a filtrar por el permiso de su módulo al leerlo. El
28/09/2026 los recordatorios del calendario (origen "calendario_aviso") no
estaban en la lista y caían en la regla por defecto, que pide precios.search:
a quien tenía el calendario pero no el buscador de precios no le llegaban.
Lo que se fija acá es que cada tipo de aviso pida SU permiso.
"""
from types import SimpleNamespace

import pytest

from app.api.routes.watchlist import _notif_visible
from app.services.calendario_avisos import ORIGEN as ORIGEN_RECORDATORIO


def _usuario(*permisos, super_=False):
    return SimpleNamespace(is_superuser=super_, permissions=list(permisos))


def _aviso(origen):
    return SimpleNamespace(origen_tipo=origen)


def test_el_recordatorio_del_calendario_le_llega_a_quien_ve_el_calendario():
    assert _notif_visible(_usuario("calendario.view"), _aviso(ORIGEN_RECORDATORIO))


def test_no_hace_falta_el_buscador_de_precios_para_ver_un_recordatorio():
    assert _notif_visible(_usuario("calendario.view", "calendario.edit"), _aviso("calendario_aviso"))


def test_sin_el_calendario_no_se_ve_el_recordatorio():
    assert not _notif_visible(_usuario("precios.search"), _aviso("calendario_aviso"))


@pytest.mark.parametrize("origen", ["calendario_accion", "calendario_header", "calendario_aviso"])
def test_todo_lo_del_calendario_pide_el_calendario(origen):
    assert _notif_visible(_usuario("calendario.view"), _aviso(origen))
    assert not _notif_visible(_usuario("precios.search"), _aviso(origen))


def test_las_alertas_de_campanas_piden_medios():
    assert _notif_visible(_usuario("analytics.view"), _aviso("campaign_alert"))
    assert not _notif_visible(_usuario("calendario.view"), _aviso("campaign_alert"))


def test_los_cambios_de_precio_piden_el_buscador():
    assert _notif_visible(_usuario("precios.search"), _aviso(None))
    assert not _notif_visible(_usuario("calendario.view"), _aviso(None))


def test_el_superadmin_ve_todo():
    for origen in ("calendario_aviso", "campaign_alert", None):
        assert _notif_visible(_usuario(super_=True), _aviso(origen))
