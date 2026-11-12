"""Los mundos (la plataforma entera, separada por negocio) y las tareas
asignadas de una acción.

Pedido de Ivan (12/11/2026): "Los mundos tienen que ser de toda la plataforma.
La persona que entra a ese mundo va a ver todo hecho para ese mundo... una
persona que tenga acceso a un solo mundo va directamente al único que tiene",
y que quien lidera pueda crear tareas y subtareas en cada acción y
asignárselas a cada persona.

Lo que se fija acá es lo que no depende de la base: quién abre qué mundo, a
qué profundidad puede colgar una tarea y qué dice el aviso.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes.calendario import (
    _NIVELES_DE_TAREA, BarraNueva, TareaCambios, TareaNueva,
    mensaje_de_asignacion, mensaje_de_tarea_hecha, nivel_de, referencia_de_tarea,
)
from app.core.mundos import (
    MUNDO_POR_DEFECTO, MUNDOS, exigir_mundo, mundos_de, mundos_iniciales, puede_abrir,
)
from app.models.role import ALL_PERMISSIONS, DEFAULT_ROLES


def _persona(mundos=None, superuser=False):
    return SimpleNamespace(mundos=mundos, is_superuser=superuser)


# --- Mundos ----------------------------------------------------------------

def test_los_cinco_mundos_y_el_de_siempre():
    assert list(MUNDOS) == ["tienda_inglesa", "tienda_express", "redexpres", "tienda_viajes", "tienda_farma"]
    assert MUNDO_POR_DEFECTO == "tienda_inglesa"


def test_cada_uno_abre_solo_los_suyos():
    assert mundos_de(_persona(["redexpres"])) == ["redexpres"]
    assert not puede_abrir(_persona(["redexpres"]), "tienda_inglesa")


def test_nadie_queda_sin_mundo():
    """Sin mundo no se puede entrar a la plataforma: a quien todavía no se le
    asignó ninguno le toca Tienda Inglesa, que es donde estaba todo."""
    assert mundos_de(_persona(None)) == ["tienda_inglesa"]
    assert mundos_de(_persona([])) == ["tienda_inglesa"]
    assert mundos_de(_persona(["mundo_viejo"])) == ["tienda_inglesa"]


def test_un_superadmin_abre_todos():
    assert mundos_de(_persona([], superuser=True)) == list(MUNDOS)


def test_los_mundos_salen_en_el_orden_del_selector():
    assert mundos_de(_persona(["redexpres", "tienda_inglesa"])) == ["tienda_inglesa", "redexpres"]


def test_un_mundo_que_ya_no_existe_se_ignora():
    assert mundos_de(_persona(["tienda_inglesa", "mundo_viejo"])) == ["tienda_inglesa"]


def test_pedir_un_mundo_ajeno_es_403_y_uno_inventado_422():
    with pytest.raises(HTTPException) as ajeno:
        exigir_mundo(_persona(["redexpres"]), "tienda_inglesa")
    assert ajeno.value.status_code == 403
    with pytest.raises(HTTPException) as inventado:
        exigir_mundo(_persona(superuser=True), "no_existe")
    assert inventado.value.status_code == 422


# --- Con qué mundos arranca cada uno (la regla de la migración 0060) --------

def test_quien_usaba_la_plataforma_queda_en_tienda_inglesa():
    assert mundos_iniciales(["calendario.view", "cenefas.view"]) == ["tienda_inglesa"]


def test_quien_no_tiene_ningun_permiso_tambien():
    """Entra a algo (Don Tino, la ayuda, su perfil): necesita un mundo."""
    assert mundos_iniciales([]) == ["tienda_inglesa"]
    assert mundos_iniciales(None) == ["tienda_inglesa"]


@pytest.mark.parametrize("permiso", ["redexpres.view", "redexpres.manage"])
def test_quien_tiene_algo_de_redexpres_no_pierde_la_planilla(permiso):
    """La planilla de pedidos pasa a verse solo dentro de Redexpres: quien la
    usaba tiene que quedar adentro."""
    assert mundos_iniciales(["calendario.view", permiso]) == ["tienda_inglesa", "redexpres"]


def test_quien_solo_es_de_redexpres_queda_solo_en_redexpres():
    assert mundos_iniciales(["redexpres.view"]) == ["redexpres"]


def test_un_login_de_sucursal_entra_solo_a_redexpres():
    assert mundos_iniciales([], es_sucursal_de_redexpres=True) == ["redexpres"]


def test_los_otros_mundos_no_se_le_dan_a_nadie_solos():
    todos = list(ALL_PERMISSIONS)
    assert mundos_iniciales(todos) == ["tienda_inglesa", "redexpres"]


def test_la_migracion_reparte_con_la_misma_regla():
    """La 0060 lleva su propia copia de la regla (una migración no puede
    cambiar si mañana cambia el código): hoy tienen que decir lo mismo."""
    import importlib.util
    import pathlib

    ruta = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0060_mundos_y_tareas.py"
    spec = importlib.util.spec_from_file_location("m0060", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    for permisos in ([], ["calendario.view"], ["redexpres.view"], ["cenefas.view", "redexpres.manage"], list(ALL_PERMISSIONS)):
        for sucursal in (False, True):
            assert modulo._mundos_iniciales(permisos, sucursal) == mundos_iniciales(permisos, sucursal)


def test_una_barra_sin_mundo_es_de_tienda_inglesa():
    """El front de antes de los mundos no lo manda: lo suyo sigue cayendo en
    el único calendario que había."""
    b = BarraNueva(id="br-1", seccion="comercial", banda="MEGA EVENTO", nombre="Ciberlunes",
                   desde=date(2026, 11, 2), hasta=date(2026, 11, 4))
    assert b.mundo == "tienda_inglesa"


# --- Tareas ----------------------------------------------------------------

def test_tarea_subtarea_y_subsubtarea_y_no_mas():
    padres = {"t1": None, "t2": "t1", "t3": "t2"}
    assert nivel_de(None, padres) == 1
    assert nivel_de("t1", padres) == 2
    assert nivel_de("t2", padres) == 3
    assert nivel_de("t3", padres) > _NIVELES_DE_TAREA


def test_un_ciclo_no_cuelga_el_servidor():
    assert nivel_de("a", {"a": "b", "b": "a"}) > _NIVELES_DE_TAREA


def test_una_tarea_sin_titulo_no_se_guarda():
    with pytest.raises(ValidationError):
        TareaNueva(id="ta-1", titulo="   ")


def test_solo_viaja_lo_que_cambio():
    assert TareaCambios(estado="hecha").model_fields_set == {"estado"}
    # Sacarle la persona es mandarla en null: tiene que distinguirse de no mandarla.
    assert TareaCambios(asignadoA=None).model_fields_set == {"asignadoA"}


def test_un_estado_que_no_existe_no_se_guarda():
    with pytest.raises(ValidationError):
        TareaCambios(estado="publicado")


def test_el_aviso_de_asignacion_dice_quien_que_y_donde():
    texto = mensaje_de_asignacion("Ana", "Arte mobile", "Ciberlunes", date(2026, 11, 20))
    assert texto == "Ana te asignó una tarea en Ciberlunes: Arte mobile. Vence el 20/11."
    assert "Vence" not in mensaje_de_asignacion("Ana", "Arte mobile", "Ciberlunes", None)


def test_el_aviso_de_tarea_terminada():
    assert mensaje_de_tarea_hecha("Ivan", "Arte mobile", "Ciberlunes") == \
        "Ivan terminó la tarea «Arte mobile» de Ciberlunes."


def test_la_referencia_empieza_por_la_accion():
    """La campanita abre la ficha con lo que hay antes del primer ':'."""
    assert referencia_de_tarea("br-9", "ta-3").split(":")[0] == "br-9"


def test_el_permiso_de_tareas_existe_y_no_lo_trae_el_rol_usuario():
    assert "calendario.tareas" in ALL_PERMISSIONS
    usuario = next(r for r in DEFAULT_ROLES if r["name"] == "Usuario")
    assert "calendario.tareas" not in usuario["permissions"]
