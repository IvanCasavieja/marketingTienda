"""Don Tino se amolda a cada usuario: lo propio se lo dice siempre.

Ivan (19/11/2026): "Don Tino debe amoldarse a cada usuario". A quien le
limitaron el calendario (1 mes, 2 meses, 12 meses o «No lo ve») y le
preguntaba «¿qué tengo pendiente?», Don Tino no le nombraba sus tareas de
las acciones que quedan fuera de lo que ve, aunque en «Mis tareas» sí las
veía. Lo que se fija acá:

- Sus tareas abiertas le llegan siempre, con la misma regla que Mis tareas
  (alcance.le_llega_siempre): las hechas, solo las de su alcance. De esa
  acción, el nombre y las fechas, sin link ni id: la ficha no le abriría.
- Lo de los demás y las acciones fuera de su alcance siguen cerrados.
- Quien no ve el calendario solo puede preguntar por lo suyo: de otra persona
  no se le dice nada, ni siquiera "no tiene tareas".
- El chat sabe hasta dónde ve cada uno.

Sin base y sin la API: la fuente es falsa y a propósito no filtra nada (como
una consulta con un bug). Lo de una agencia (sus tarjetas, siempre) está en
test_agencia_externa.py; con la base, en test_tablero_agencia_api.py.
"""
import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.core import alcance
from app.services import calendario_consultas as cc

HOY = date(2026, 11, 15)  # con «1 mes» ve del 25/10 al 30/11


def _persona(uid, nombre, alc):
    return SimpleNamespace(
        id=uid, full_name=nombre, email=f"p{uid}@x.uy", mundos=["tienda_inglesa"],
        permissions=["calendario.view", "ai.don_tino"], is_superuser=False, is_active=True,
        es_externo=False, empresa=None, calendario_alcance=alc,
    )


LIMITADA = _persona(3, "Lucía Limitada", "1m")
SIN_CAL = _persona(4, "Nadia Sin Calendario", "nada")
OTRO = _persona(5, "Otro del Equipo", "todo")


def _barra(id, nombre, desde, hasta):
    return SimpleNamespace(id=id, mundo="tienda_inglesa", nombre=nombre, banda="MEGA EVENTO", seccion="comercial",
                           desde=desde, hasta=hasta, formato=None, hora=None, estado=None)


AHORA = _barra("b-ahora", "Black Friday", date(2026, 11, 20), date(2026, 11, 29))
FEBRERO = _barra("b-feb", "Carnaval de FEBRERO", date(2027, 2, 10), date(2027, 2, 20))


def _tarea(id, barra, titulo, asignado, *, estado="pendiente", vence=None):
    return SimpleNamespace(id=id, barra_id=barra.id, parent_id=None, titulo=titulo, descripcion=None,
                           estado=estado, asignado_a_id=asignado, vence=vence)


TAREAS = [
    _tarea("t-ahora", AHORA, "Brief de Black Friday", 3, vence=date(2026, 11, 18)),
    _tarea("t-feb", FEBRERO, "Brief del carnaval", 3, vence=date(2027, 1, 20)),
    _tarea("t-feb-hecha", FEBRERO, "Ya HECHA del carnaval", 3, estado="hecha", vence=date(2027, 1, 10)),
    _tarea("t-feb-otro", FEBRERO, "La de OTRO en el carnaval", 5, vence=date(2027, 1, 25)),
    _tarea("t-feb-sin", FEBRERO, "SIN DUEÑO en el carnaval", None, vence=date(2027, 1, 26)),
    _tarea("t-ahora-otro", AHORA, "Afiche del compañero", 5, vence=date(2026, 11, 19)),
    _tarea("t-ahora-nadia", AHORA, "La de Nadia", 4, vence=date(2026, 11, 17)),
]
BARRAS = {b.id: b for b in (AHORA, FEBRERO)}


class FuenteSinFiltro:
    """Devuelve todo, sin mirar mundo, fechas ni personas: lo que no se ve lo
    tiene que recortar Don Tino."""

    async def barras(self, mundos, *, rango=None, secciones=None, ids=None):
        return [b for b in BARRAS.values() if ids is None or b.id in ids]

    async def piezas_de(self, ids):
        return []

    async def tareas_de(self, ids):
        return [t for t in TAREAS if t.barra_id in ids]

    async def avisos_de(self, ids):
        return []

    async def piezas_con_accion(self, mundos, desde, hasta):
        return []

    async def tareas_con_accion(self, mundos, **kw):
        return [(t, BARRAS[t.barra_id]) for t in TAREAS]

    async def titulos_de_tareas(self, ids):
        return {t.id: t.titulo for t in TAREAS if t.id in ids}

    async def tareas_con_tarjeta(self, ids):
        return set()

    async def avisos_con_accion(self, mundos, desde, hasta):
        return []

    async def personas_activas(self):
        return [LIMITADA, SIN_CAL, OTRO]


def _tino(nombre, usuario, args=None):
    salida = asyncio.run(cc.ejecutar(nombre, args or {}, usuario, None, hoy=HOY, fuente=FuenteSinFiltro()))
    return json.loads(salida), salida


# ---------------------------------------------------------------------------
# Con el calendario limitado
# ---------------------------------------------------------------------------

def test_con_un_mes_que_tengo_pendiente_trae_tambien_lo_suyo_de_febrero():
    datos, _ = _tino("calendario_tareas", LIMITADA, {"responsable": "yo"})
    assert [t["titulo"] for t in datos["tareas"]] == ["Brief de Black Friday", "Brief del carnaval"]
    ahora, febrero = (t["accion"] for t in datos["tareas"])
    # La de su mes, con su link de siempre.
    assert ahora["link"] == "/calendario?accion=b-ahora" and "fuera_de_lo_que_ve" not in ahora
    # La de febrero: el nombre y las fechas, sin link ni id (como en Mis tareas).
    assert febrero == {
        "nombre": "Carnaval de FEBRERO", "mundo": "Tienda Inglesa", "desde": "2027-02-10", "hasta": "2027-02-20",
        "fuera_de_lo_que_ve": True, "categoria": "MEGA EVENTO",
    }
    assert datos["tareas"][1]["responsable"] == "Lucía Limitada (vos)"


def test_las_hechas_fuera_de_su_alcance_no_como_en_mis_tareas():
    datos, texto = _tino("calendario_tareas", LIMITADA,
                         {"responsable": "yo", "estados": ["pendiente", "en-proceso", "hecha"]})
    assert "Brief del carnaval" in texto and "Ya HECHA" not in texto


def test_lo_de_los_demas_fuera_de_su_alcance_sigue_cerrado():
    datos, texto = _tino("calendario_tareas", LIMITADA, {"responsable": "todos"})
    # De su ventana, todo (es del equipo); de afuera, solo lo suyo.
    assert [t["titulo"] for t in datos["tareas"]] == [
        "Brief de Black Friday", "Brief del carnaval", "Afiche del compañero", "La de Nadia"]
    assert "OTRO" not in texto and "SIN DUEÑO" not in texto
    # La ficha de esa acción no se abre, ni aparece entre las acciones. Y "no
    # la encontré" dice que puede estar fuera de sus fechas: no que no existe.
    datos, _ = _tino("calendario_accion", LIMITADA, {"accion_id": "b-feb"})
    assert "fuera de las fechas que ve del calendario" in datos["error"]
    datos, _ = _tino("calendario_accion", LIMITADA, {"texto": "Carnaval"})
    assert "entre las fechas que esta persona ve del calendario" in datos["error"]
    _, texto = _tino("calendario_acciones", LIMITADA, {"desde": "2027-02-01", "hasta": "2027-02-28"})
    assert "FEBRERO" not in texto


def test_en_la_carga_lo_suyo_de_febrero_cuenta_sin_link():
    datos, texto = _tino("calendario_carga", LIMITADA, {"desde": "2027-01-01", "hasta": "2027-01-31"})
    suya = next(p for p in datos["personas"] if p["persona"] == "Lucía Limitada (vos)")
    assert suya["vencen_en_el_periodo"] == 1
    assert suya["del_periodo"] == [{"titulo": "Brief del carnaval", "vence": "2027-01-20",
                                    "accion": "Carnaval de FEBRERO", "fuera_de_lo_que_ve": True}]
    assert "OTRO" not in texto and "SIN DUEÑO" not in texto and "/calendario?accion=b-feb" not in texto


def test_es_la_misma_regla_que_mis_tareas():
    por_id = {t.id: t for t in TAREAS}
    assert alcance.le_llega_siempre(LIMITADA, por_id["t-feb"])
    assert not alcance.le_llega_siempre(LIMITADA, por_id["t-feb-hecha"])
    assert not alcance.le_llega_siempre(LIMITADA, por_id["t-feb-otro"])
    assert not alcance.le_llega_siempre(LIMITADA, por_id["t-feb-sin"])
    # A una agencia, no: lo suyo es el tablero (sus tarjetas, ver test_agencia_externa.py).
    agencia = SimpleNamespace(**{**vars(LIMITADA), "es_externo": True, "empresa": "Publicis"})
    assert not alcance.le_llega_siempre(agencia, por_id["t-feb"])


# ---------------------------------------------------------------------------
# Sin calendario («No lo ve»)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("responsable", ["yo", "todos", None])
def test_sin_calendario_igual_sabe_lo_suyo(responsable):
    args = {"responsable": responsable} if responsable else {}
    datos, texto = _tino("calendario_tareas", SIN_CAL, args)
    assert [t["titulo"] for t in datos["tareas"]] == ["La de Nadia"]
    assert datos["tareas"][0]["accion"]["fuera_de_lo_que_ve"] is True
    assert "link" not in datos["tareas"][0]["accion"]
    assert datos["solo_las_suyas"] == cc.SOLO_LAS_SUYAS
    assert "Lucía" not in texto and "compañero" not in texto


@pytest.mark.parametrize("responsable", ["Lucía", "Otro", "sin_asignar", "Pepe"])
def test_sin_calendario_de_otra_persona_no_se_le_dice_nada(responsable):
    """Ni que no tiene tareas (sería mentira) ni si existe alguien con ese nombre."""
    datos, texto = _tino("calendario_tareas", SIN_CAL, {"responsable": responsable})
    assert datos == {"error": cc.SOLO_LO_SUYO}
    assert "Black Friday" not in texto


@pytest.mark.parametrize("herramienta", ["calendario_acciones", "calendario_accion", "calendario_piezas",
                                         "calendario_carga", "calendario_avisos"])
def test_sin_calendario_lo_demas_sigue_cerrado(herramienta):
    datos, texto = _tino(herramienta, SIN_CAL, {"accion_id": "b-ahora", "texto": "Black"})
    assert datos == {"error": cc.NO_VE_EL_CALENDARIO}
    assert "sus propias tareas" in datos["error"]


def test_quien_ve_todo_sigue_igual():
    datos, texto = _tino("calendario_tareas", OTRO, {"responsable": "todos"})
    assert "fuera_de_lo_que_ve" not in texto and "solo_las_suyas" not in datos
    assert {t["titulo"] for t in datos["tareas"]} == {
        "Brief de Black Friday", "Brief del carnaval", "La de OTRO en el carnaval", "SIN DUEÑO en el carnaval",
        "Afiche del compañero", "La de Nadia"}


# ---------------------------------------------------------------------------
# El chat sabe hasta dónde ve cada uno
# ---------------------------------------------------------------------------

def test_el_chat_le_dice_al_modelo_hasta_donde_ve_cada_uno():
    from app.api.routes.chat import _contexto_del_dia

    limitada = _contexto_del_dia(LIMITADA, HOY)
    assert "del 25/10/2026 al 30/11/2026" in limitada and "sus propias tareas" in limitada
    assert "No ve el calendario" in _contexto_del_dia(SIN_CAL, HOY)
    todo = _contexto_del_dia(OTRO, HOY)
    assert "ve del" not in todo and "No ve el calendario" not in todo
    # Sin el permiso del calendario, ni se menciona.
    sin_permiso = SimpleNamespace(**{**vars(LIMITADA), "permissions": ["ai.don_tino"]})
    assert "calendario" not in _contexto_del_dia(sin_permiso, HOY)
