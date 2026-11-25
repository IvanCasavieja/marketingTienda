"""Don Tino consulta con los permisos de quien le pregunta.

El 28/09/2026 se encontró que le buscaba precios a cualquiera con ai.don_tino,
tuviera o no el permiso del buscador (precios.search). Lo que se fija acá: cada
herramienta exige el permiso de su módulo, tanto al ofrecérsela al modelo como
al ejecutarla, y el superadmin las tiene todas.
"""
import asyncio
import json
from types import SimpleNamespace

from app.api.routes.chat import _ejecutar_tool, _puede_usar_tool, _tools_para


def _usuario(*permisos, super_=False, mundos=()):
    return SimpleNamespace(is_superuser=super_, permissions=list(permisos), mundos=list(mundos))


def test_sin_el_buscador_no_se_le_ofrece_buscar_precio():
    tools = _tools_para(_usuario("ai.don_tino", "calendario.view"))
    assert "buscar_precio" not in [t["name"] for t in tools]


def test_con_el_buscador_si():
    tools = _tools_para(_usuario("ai.don_tino", "precios.search"))
    assert "buscar_precio" in [t["name"] for t in tools]


def test_cada_herramienta_pide_el_permiso_de_su_modulo():
    assert _puede_usar_tool(_usuario("cenefas.view"), "consultar_estado_cenefa")
    assert not _puede_usar_tool(_usuario("precios.search"), "consultar_estado_cenefa")
    assert _puede_usar_tool(_usuario("ai.triada"), "resumen_ultimo_debate")
    assert not _puede_usar_tool(_usuario("ai.don_tino"), "resumen_ultimo_debate")


def test_el_superadmin_las_tiene_todas():
    assert [t["name"] for t in _tools_para(_usuario(super_=True))] == [
        "buscar_precio", "consultar_estado_cenefa", "resumen_ultimo_debate",
        "calendario_acciones", "calendario_accion", "calendario_piezas",
        "calendario_tareas", "calendario_carga", "calendario_avisos",
        "tablero_tarjetas", "redexpres_pedidos",
    ]


def test_las_del_calendario_piden_calendario_view():
    nombres = [t["name"] for t in _tools_para(_usuario("ai.don_tino", "calendario.view"))]
    assert nombres == [
        "calendario_acciones", "calendario_accion", "calendario_piezas",
        "calendario_tareas", "calendario_carga", "calendario_avisos",
        # El tablero (25/11/2026), con lo mismo que la pantalla.
        "tablero_tarjetas",
    ]
    assert not any(n.startswith("calendario_") for n in [t["name"] for t in _tools_para(_usuario("ai.don_tino"))])


def test_sin_ningun_permiso_no_hay_herramientas():
    assert _tools_para(_usuario("ai.don_tino")) == []


def test_ejecutar_sin_permiso_no_busca_y_lo_dice():
    # db=None a propósito: la denegación tiene que cortar ANTES de tocar nada.
    salida = asyncio.run(_ejecutar_tool("buscar_precio", {"termino": "cafe"}, _usuario("ai.don_tino"), None))
    datos = json.loads(salida)
    assert "error" in datos and "precios.search" in datos["error"]


def test_una_herramienta_desconocida_tampoco_pasa():
    salida = asyncio.run(_ejecutar_tool("otra_cosa", {}, _usuario(super_=True), None))
    assert "error" in json.loads(salida)


def test_los_pedidos_de_redexpres_los_tiene_quien_tiene_la_planilla_o_un_local():
    # 25/11/2026: el local ve el suyo (lo cuida la herramienta); el equipo de otro mundo, nada.
    assert _puede_usar_tool(_usuario("redexpres.view"), "redexpres_pedidos")
    assert _puede_usar_tool(_usuario("ai.don_tino", mundos=("redexpres",)), "redexpres_pedidos")
    assert not _puede_usar_tool(_usuario("ai.don_tino", "calendario.view", mundos=("tienda_inglesa",)),
                                "redexpres_pedidos")

