"""calendario.pedidos: pedir piezas y materiales es un permiso aparte (0071).

Pedido de Ivan (17/11/2026): la acción la arma quien lidera, y "debería de
ser un permiso específico el poder hacer peticiones de materiales". Antes pedir
una pieza venía con calendario.edit.
"""
import importlib.util
import pathlib
from types import SimpleNamespace

from app.api.routes.calendario import PERMISO_PEDIDOS, puede_crear_tarea, puede_pedir_piezas
from app.models.role import ALL_PERMISSIONS, DEFAULT_ROLES, is_view_permission


def _persona(*permisos, externo=False, superusuario=False):
    return SimpleNamespace(id=1, es_externo=externo, is_superuser=superusuario, permissions=list(permisos))


def _migracion():
    ruta = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0071_permiso_pedir_piezas.py"
    spec = importlib.util.spec_from_file_location("m0071", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_permiso_existe_y_no_es_de_solo_lectura():
    assert PERMISO_PEDIDOS == "calendario.pedidos"
    assert PERMISO_PEDIDOS in ALL_PERMISSIONS
    assert not is_view_permission(PERMISO_PEDIDOS)


def test_el_rol_usuario_lo_trae_como_traia_editar():
    usuario = next(r for r in DEFAULT_ROLES if r["name"] == "Usuario")
    assert "calendario.edit" in usuario["permissions"] and PERMISO_PEDIDOS in usuario["permissions"]
    viewer = next(r for r in DEFAULT_ROLES if r["name"] == "Viewer")
    assert PERMISO_PEDIDOS not in viewer["permissions"]


def test_pedir_piezas_ya_no_viene_con_editar():
    solo_edita = _persona("calendario.view", "calendario.edit")
    assert not puede_pedir_piezas(solo_edita)
    assert not puede_crear_tarea(solo_edita, pieza=True)


def test_quien_tiene_pedidos_crea_tareas_y_sus_materiales():
    # "El inicio debería ser crear tarea y punto... y debajo de eso poder
    # asignar los materiales de esa tarea creada" (17/11/2026).
    analista = _persona("calendario.view", PERMISO_PEDIDOS)
    assert puede_pedir_piezas(analista)
    assert puede_crear_tarea(analista, pieza=True)
    assert puede_crear_tarea(analista, pieza=False)


def test_quien_lidera_pide_piezas_sin_el_permiso_aparte():
    lider = _persona("calendario.view", "calendario.tareas")
    assert puede_pedir_piezas(lider)
    assert puede_crear_tarea(lider, pieza=True) and puede_crear_tarea(lider, pieza=False)
    assert puede_pedir_piezas(_persona(superusuario=True))


def test_una_cuenta_externa_nunca_pide_aunque_lo_tenga_anotado():
    agencia = _persona("calendario.view", PERMISO_PEDIDOS, externo=True)
    assert not puede_pedir_piezas(agencia)
    assert not puede_crear_tarea(agencia, pieza=True)


def test_la_migracion_lo_suma_al_lado_de_editar():
    m = _migracion()
    assert m.con_pedidos(["calendario.view", "calendario.edit", "ai.don_tino"]) == (
        ["calendario.view", "calendario.edit", "calendario.pedidos", "ai.don_tino"], True)


def test_la_migracion_no_toca_a_quien_no_editaba_ni_repite():
    m = _migracion()
    assert m.con_pedidos(["calendario.view"]) == (["calendario.view"], False)
    assert m.con_pedidos(None) == ([], False)
    ya = ["calendario.edit", "calendario.pedidos"]
    assert m.con_pedidos(ya) == (ya, False)


def test_la_migracion_sigue_a_la_0070():
    m = _migracion()
    assert m.revision == "0071" and m.down_revision == "0070"
