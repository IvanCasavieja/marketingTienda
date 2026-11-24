"""Las plantillas de tareas y las tareas que se mueven con su acción (0065).

Cada tipo de acción lleva casi siempre las mismas tareas: el brief a la
agencia, las entregas, la aprobación, las cenefas a los locales, la foto de
colocación y el retiro. Una plantilla las guarda con su vencimiento relativo
(N días antes o después del inicio o del fin) y, al aplicarla, se crean con la
fecha calculada. Si la acción se mueve, las que no están hechas se mueven con
ella; si alguien cambia a mano una fecha, esa queda donde la puso.

Lo que se fija acá es la lógica pura, sin base: las cuentas de fechas, qué se
mueve y qué no, qué plantilla se puede guardar y qué dice el aviso.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.routes.calendario import (
    PlantillaAplicada, PlantillaCambio, PlantillaDatos, TareaDePlantilla, _tarea_json,
    categoria_de_plantilla, mensaje_de_asignacion, mensaje_de_asignaciones, poner_vence_a_mano,
    tareas_de_plantilla, vence_al_reabrir, vence_anclado, vencimientos_al_mover,
)
from app.models.calendario import CalendarioTarea

# Una acción del 10 al 20 de diciembre.
DESDE, HASTA = date(2026, 12, 10), date(2026, 12, 20)


def _tarea(id_, ancla="inicio", dias=0, estado="pendiente", vence=None):
    return SimpleNamespace(id=id_, ancla=ancla, ancla_dias=dias if ancla else None, estado=estado, vence=vence)


# --- La cuenta -----------------------------------------------------------------

@pytest.mark.parametrize("ancla,dias,esperado", [
    ("inicio", -30, date(2026, 11, 10)),   # brief a la agencia
    ("inicio", -3, date(2026, 12, 7)),     # cenefas a los locales
    ("inicio", 0, date(2026, 12, 10)),     # el día que arranca
    ("inicio", 1, date(2026, 12, 11)),     # foto de colocación
    ("fin", 0, date(2026, 12, 20)),        # el día que termina
    ("fin", 1, date(2026, 12, 21)),        # retiro
])
def test_el_vencimiento_se_cuenta_desde_el_inicio_o_el_fin(ancla, dias, esperado):
    assert vence_anclado(ancla, dias, DESDE, HASTA) == esperado


def test_la_cuenta_cruza_de_mes_y_de_anio():
    assert vence_anclado("fin", 15, DESDE, HASTA) == date(2027, 1, 4)


# --- Si la acción se mueve -------------------------------------------------------

def test_al_mover_la_accion_se_mueven_las_ancladas():
    tareas = [_tarea("brief", "inicio", -30, vence=date(2026, 11, 10)),
              _tarea("retiro", "fin", 1, vence=date(2026, 12, 21))]
    # Se corre una semana entera.
    nuevas = vencimientos_al_mover(tareas, date(2026, 12, 17), date(2026, 12, 27))
    assert nuevas == {"brief": date(2026, 11, 17), "retiro": date(2026, 12, 28)}


def test_las_hechas_no_se_mueven():
    """Lo hecho, hecho está: su fecha queda como registro."""
    tareas = [_tarea("brief", "inicio", -30, estado="hecha", vence=date(2026, 11, 10))]
    assert vencimientos_al_mover(tareas, date(2026, 12, 17), date(2026, 12, 27)) == {}


def test_las_que_no_vinieron_de_plantilla_no_se_mueven():
    tareas = [_tarea("a-mano", ancla=None, vence=date(2026, 12, 1))]
    assert vencimientos_al_mover(tareas, date(2026, 12, 17), date(2026, 12, 27)) == {}


def test_si_solo_cambia_el_fin_solo_se_mueven_las_del_fin():
    tareas = [_tarea("brief", "inicio", -30, vence=date(2026, 11, 10)),
              _tarea("retiro", "fin", 1, vence=date(2026, 12, 21))]
    assert vencimientos_al_mover(tareas, DESDE, date(2026, 12, 24)) == {"retiro": date(2026, 12, 25)}


def test_solo_vuelve_lo_que_cambia():
    tareas = [_tarea("brief", "inicio", -30, vence=date(2026, 11, 10))]
    assert vencimientos_al_mover(tareas, DESDE, HASTA) == {}


# --- Lo manual se respeta ----------------------------------------------------------

def test_cambiar_a_mano_el_vencimiento_le_saca_el_ancla():
    t = _tarea("brief", "inicio", -30, vence=date(2026, 11, 10))
    poner_vence_a_mano(t, date(2026, 11, 12))
    assert (t.vence, t.ancla, t.ancla_dias) == (date(2026, 11, 12), None, None)
    # Y desde ahí, mover la acción ya no la toca.
    assert vencimientos_al_mover([t], date(2026, 12, 17), date(2026, 12, 27)) == {}


def test_sacarle_la_fecha_a_mano_tambien():
    t = _tarea("brief", "inicio", -30, vence=date(2026, 11, 10))
    poner_vence_a_mano(t, None)
    assert (t.vence, t.ancla) == (None, None)


def test_mandar_la_misma_fecha_no_es_cambiarla():
    """El campo de fecha puede volver a mandar lo que ya tenía: eso no es una
    decisión de la persona, y la tarea sigue moviéndose con la acción."""
    t = _tarea("brief", "inicio", -30, vence=date(2026, 11, 10))
    poner_vence_a_mano(t, date(2026, 11, 10))
    assert (t.ancla, t.ancla_dias) == ("inicio", -30)


def test_al_reabrir_una_hecha_vuelve_a_su_fecha_con_la_accion_de_hoy():
    # Se hizo cuando la acción arrancaba el 10; después la acción pasó al 17.
    t = _tarea("brief", "inicio", -30, estado="hecha", vence=date(2026, 11, 10))
    assert vence_al_reabrir(t, date(2026, 12, 17), date(2026, 12, 27)) == date(2026, 11, 17)


def test_al_reabrir_una_sin_ancla_queda_como_estaba():
    t = _tarea("a-mano", ancla=None, estado="hecha", vence=date(2026, 12, 1))
    assert vence_al_reabrir(t, date(2026, 12, 17), date(2026, 12, 27)) == date(2026, 12, 1)


# --- Qué plantilla se puede guardar ------------------------------------------------

def _plantilla(tareas, **extra):
    return PlantillaDatos(**{"nombre": "Mega evento", "categoria": "MEGA EVENTO", "tareas": tareas, **extra})


EJEMPLO = [
    {"id": "t1", "titulo": "Brief a la agencia", "ancla": "inicio", "dias": -30},
    {"id": "t2", "titulo": "Primera entrega de la agencia", "ancla": "inicio", "dias": -21},
    {"id": "t3", "titulo": "Aprobación final", "ancla": "inicio", "dias": -10},
    {"id": "t4", "titulo": "Cenefas a los locales", "ancla": "inicio", "dias": -3},
    {"id": "t5", "titulo": "Foto de colocación", "ancla": "inicio", "dias": 1},
    {"id": "t6", "titulo": "Retirar cenefas y carteles de la promo", "ancla": "fin", "dias": 1},
]


def test_el_ejemplo_se_puede_guardar():
    p = _plantilla(EJEMPLO)
    assert [t.dias for t in p.tareas] == [-30, -21, -10, -3, 1, 1]
    assert p.mundo == "tienda_inglesa"


def test_una_plantilla_sin_tareas_o_sin_nombre_no_se_guarda():
    with pytest.raises(ValidationError):
        _plantilla([])
    with pytest.raises(ValidationError):
        _plantilla(EJEMPLO, nombre="   ")


def test_una_tarea_sin_titulo_no_se_guarda():
    with pytest.raises(ValidationError):
        _plantilla([{"id": "t1", "titulo": "  "}])


def test_ya_no_hay_subtareas_en_una_plantilla():
    # 0090: una tarea = un pedido, también en las plantillas.
    _plantilla([{"id": "t1", "titulo": "Piezas"}, {"id": "t2", "titulo": "Header"}])
    for anidada in (
        [{"id": "t1", "titulo": "Piezas"}, {"id": "t2", "titulo": "Header", "parentId": "t1"}],
        [{"id": "t2", "titulo": "Header", "parentId": "otra"}],
        [{"id": "t1", "titulo": "Ella misma", "parentId": "t1"}],
    ):
        with pytest.raises(ValidationError, match="primer nivel"):
            _plantilla(anidada)


def test_el_responsable_de_tienda_va_solo_en_lo_que_hace_una_agencia():
    assert TareaDePlantilla(id="t1", titulo="x", para="agencia", agencia="Publicis", responsable=5).responsable == 5
    assert TareaDePlantilla(id="t1", titulo="x", responsable=5).responsable is None


def test_dos_tareas_con_el_mismo_id_no():
    with pytest.raises(ValidationError):
        _plantilla([{"id": "t1", "titulo": "A"}, {"id": "t1", "titulo": "B"}])


def test_los_dias_tienen_tope_y_el_ancla_es_inicio_o_fin():
    with pytest.raises(ValidationError):
        TareaDePlantilla(id="t1", titulo="x", dias=400)
    with pytest.raises(ValidationError):
        TareaDePlantilla(id="t1", titulo="x", ancla="mitad")


def test_sin_ancla_no_hay_dias():
    assert TareaDePlantilla(id="t1", titulo="x", ancla=None, dias=5).dias == 0


@pytest.mark.parametrize("escrita,guardada", [
    (None, None), ("", None), ("   ", None), ("Sin categoría", None), ("sin CATEGORÍA", None),
    ("  MEGA EVENTO ", "MEGA EVENTO"),
])
def test_sin_categoria_es_de_cualquier_categoria(escrita, guardada):
    assert categoria_de_plantilla(escrita) == guardada


# --- Aplicarla ---------------------------------------------------------------------

def test_aplicar_calcula_cada_fecha_y_la_deja_anclada():
    ids = {f"t{i}": f"ta-{i}" for i in range(1, 7)}
    plan = tareas_de_plantilla(EJEMPLO, ids, DESDE, HASTA)
    assert [t["vence"] for t in plan] == [
        date(2026, 11, 10), date(2026, 11, 19), date(2026, 11, 30),
        date(2026, 12, 7), date(2026, 12, 11), date(2026, 12, 21),
    ]
    assert plan[-1]["ancla"] == "fin" and plan[-1]["ancla_dias"] == 1
    assert [t["id"] for t in plan] == list(ids.values())


def test_aplicada_va_toda_en_el_primer_nivel_en_su_orden():
    # Si una guardada trajera `parentId` (la 0090 las aplanó), no se usa.
    tareas = [
        {"id": "s1", "titulo": "Header", "parentId": "p1", "ancla": "inicio", "dias": -5},
        {"id": "p1", "titulo": "Piezas", "ancla": "inicio", "dias": -7},
        {"id": "p2", "titulo": "Banners", "ancla": "fin", "dias": 1, "para": "agencia", "agencia": "Publicis",
         "tipo": "banners", "responsable": 5},
    ]
    plan = tareas_de_plantilla(tareas, {"s1": "n1", "p1": "n2", "p2": "n3"}, DESDE, HASTA, "Ciberlunes")
    assert [t["id"] for t in plan] == ["n1", "n2", "n3"]
    assert all(t["parent_id"] is None for t in plan)
    assert [t["responsable_id"] for t in plan] == [None, None, 5]


def test_una_tarea_sin_ancla_se_crea_sin_fecha():
    plan = tareas_de_plantilla([{"id": "t1", "titulo": "Pedir cotización", "ancla": None, "dias": 0}],
                               {"t1": "n1"}, DESDE, HASTA)
    assert (plan[0]["vence"], plan[0]["ancla"], plan[0]["ancla_dias"]) == (None, None, None)


def test_si_la_plantilla_cambio_mientras_tanto_no_se_aplica_a_medias():
    with pytest.raises(PlantillaCambio):
        tareas_de_plantilla(EJEMPLO, {"t1": "n1"}, DESDE, HASTA)
    with pytest.raises(PlantillaCambio):
        tareas_de_plantilla(EJEMPLO[:1], {"t1": "n1", "t9": "n9"}, DESDE, HASTA)


def test_dos_tareas_nuevas_con_el_mismo_id_no():
    with pytest.raises(ValidationError):
        PlantillaAplicada(plantillaId="pl-1", ids={"t1": "n1", "t2": "n1"})
    with pytest.raises(ValidationError):
        PlantillaAplicada(plantillaId="pl-1", ids={"t1": "con espacios"})


def test_el_recorrido_entero():
    """Se aplica, se tilda una, se cambia a mano otra y se mueve la acción:
    se mueven las demás, y esas dos quedan donde estaban."""
    ids = {f"t{i}": f"ta-{i}" for i in range(1, 7)}
    tareas = [
        SimpleNamespace(id=t["id"], estado="pendiente", vence=t["vence"], ancla=t["ancla"], ancla_dias=t["ancla_dias"])
        for t in tareas_de_plantilla(EJEMPLO, ids, DESDE, HASTA)
    ]
    hecha, a_mano = tareas[0], tareas[3]
    hecha.estado = "hecha"
    poner_vence_a_mano(a_mano, date(2026, 12, 5))

    nuevas = vencimientos_al_mover(tareas, date(2026, 12, 13), date(2026, 12, 23))
    assert set(nuevas) == {"ta-2", "ta-3", "ta-5", "ta-6"}
    assert nuevas["ta-6"] == date(2026, 12, 24)


# --- El aviso -----------------------------------------------------------------------

def test_con_una_sola_tarea_el_aviso_es_el_de_siempre():
    assert mensaje_de_asignaciones("Ana", [("Brief", date(2026, 11, 10))], "Ciberlunes") == \
        mensaje_de_asignacion("Ana", "Brief", "Ciberlunes", date(2026, 11, 10))


def test_con_varias_es_un_solo_aviso_con_la_primera_que_vence():
    texto = mensaje_de_asignaciones("Ana", [
        ("Aprobación final", date(2026, 11, 30)), ("Brief", date(2026, 11, 10)), ("Retiro", None),
    ], "Ciberlunes")
    assert texto == ("Ana te asignó 3 tareas en Ciberlunes: Aprobación final, Brief y Retiro. "
                     "La primera vence el 10/11.")


def test_con_muchas_nombra_tres_y_cuenta_el_resto():
    texto = mensaje_de_asignaciones("Ana", [(f"Tarea {i}", None) for i in range(1, 7)], "Ciberlunes")
    assert texto == "Ana te asignó 6 tareas en Ciberlunes: Tarea 1, Tarea 2, Tarea 3 y 3 más."


# --- Lo que viaja ---------------------------------------------------------------------

def test_el_ancla_viaja_solo_en_las_tareas_que_la_tienen():
    comun = CalendarioTarea(id="ta-1", barra_id="br-1", titulo="A mano", estado="pendiente")
    assert "ancla" not in _tarea_json(comun) and "plantillaId" not in _tarea_json(comun)
    anclada = CalendarioTarea(id="ta-2", barra_id="br-1", titulo="Retiro", estado="pendiente",
                              vence=date(2026, 12, 21), ancla="fin", ancla_dias=1, plantilla_id="pl-1")
    j = _tarea_json(anclada)
    assert (j["ancla"], j["anclaDias"], j["plantillaId"], j["vence"]) == ("fin", 1, "pl-1", "2026-12-21")
