"""Una tarea = un pedido, todas en un solo nivel (0090, 24/11/2026).

Ivan: "las tareas y el pedido de piezas deberían ser uno, entendés? sería
simplemente tarea nueva pum poner los banners y descripción o lo que sea que
estemos pidiendo, pero tener así dividido en tarea, pedido de piezas y luego
subtareas me parece al pedo y confuso".

- Lo puro de la migración (aplanar lo que ya existe y las plantillas), sin base.
- El responsable de Tienda de lo que hace una agencia, con la API y una base
  de verdad (TEST_DATABASE_URL; sin ella se saltea).
"""
import importlib.util
import os
import pathlib
import uuid

import pytest

_RUTA = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0090_una_tarea_un_pedido.py"
_spec = importlib.util.spec_from_file_location("migracion_0090", _RUTA)
m0090 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m0090)

URL = os.environ.get("TEST_DATABASE_URL")


def _t(id, parent=None, *, barra="br-1", orden=0, descripcion=None, asignado=None, para="tienda",
       tipo=None, responsable=None):
    return {"id": id, "barra_id": barra, "parent_id": parent, "descripcion": descripcion,
            "asignado_a_id": asignado, "responsable_id": responsable, "para": para, "tipo": tipo, "orden": orden}


# --- La migración: lo que ya existe ------------------------------------------------

def test_la_pieza_de_hoy_sale_de_su_tarea_de_afuera_con_lo_que_tenia_afuera():
    # Lo de la captura de Ivan: "Digital" (con el detalle, los Excel y él de
    # responsable) y adentro "TiendaChecks Emisión - Banners" para Publicis.
    tareas = [
        _t("antes", orden=0),
        _t("digital", orden=1, descripcion="Search con ver más y sin CTA", asignado=7),
        _t("banners", "digital", orden=2, para="agencia", tipo="banners"),
        _t("despues", orden=3),
    ]
    plan = m0090.aplanar(tareas, con_tarjeta={"banners"}, externos=set())
    assert plan["borrar"] == ["digital"]
    assert plan["cambios"]["banners"] == {
        "parent_id": None, "descripcion": "Search con ver más y sin CTA", "responsable_id": 7, "orden": 1,
    }
    assert plan["archivos"] == {"digital": ["banners"]}
    # Queda donde estaba su tarea de afuera; las demás se corren lo justo.
    assert plan["cambios"]["despues"] == {"orden": 2}
    assert "antes" not in plan["cambios"]


def test_con_dos_piezas_cada_una_se_queda_con_su_copia_de_los_archivos():
    tareas = [
        _t("mailing", orden=0, descripcion="El de diciembre"),
        _t("p1", "mailing", orden=1, para="agencia", tipo="mailing", descripcion="Lo suyo"),
        _t("p2", "mailing", orden=2, para="fuera", tipo="banners", asignado=9),
    ]
    plan = m0090.aplanar(tareas, con_tarjeta=set(), externos=set())
    assert plan["borrar"] == ["mailing"]
    assert plan["archivos"] == {"mailing": ["p1", "p2"]}
    # La que tenía su propio detalle lo conserva.
    assert "descripcion" not in plan["cambios"]["p1"]
    assert plan["cambios"]["p2"]["descripcion"] == "El de diciembre"
    assert [plan["cambios"][p]["orden"] for p in ("p1", "p2")] == [0, 1]


def test_una_tarea_con_subtareas_sin_piezas_se_queda_y_sus_subtareas_suben():
    tareas = [
        _t("web", orden=0, asignado=3),
        _t("textos", "web", orden=0, asignado=4),
        _t("fotos", "web", orden=1),
        _t("retiro", orden=1),
    ]
    plan = m0090.aplanar(tareas, con_tarjeta=set(), externos=set())
    assert plan["borrar"] == [] and plan["archivos"] == {}
    assert plan["cambios"]["textos"] == {"parent_id": None, "orden": 1}
    assert plan["cambios"]["fotos"] == {"parent_id": None, "orden": 2}
    # Lo que venía después de la tarea se corre detrás de sus subtareas.
    assert plan["cambios"]["retiro"] == {"orden": 3}
    # Las subtareas no toman a nadie como responsable: no son de una agencia.
    assert "responsable_id" not in plan["cambios"]["textos"]


def test_tres_niveles_y_subtareas_sueltas_dentro_de_un_envoltorio():
    tareas = [
        _t("a", orden=0, descripcion="Detalle de arriba", asignado=7),
        _t("b", "a", orden=0),
        _t("c", "b", orden=0, para="agencia", tipo="banners"),
        _t("d", "b", orden=5, asignado=5),  # una subtarea común
    ]
    plan = m0090.aplanar(tareas, con_tarjeta=set(), externos=set())
    assert sorted(plan["borrar"]) == ["a", "b"]
    assert plan["cambios"]["c"] == {"parent_id": None, "descripcion": "Detalle de arriba", "responsable_id": 7}
    assert plan["cambios"]["d"] == {"parent_id": None, "orden": 1}
    assert plan["archivos"] == {"b": ["c"], "a": ["c"]}


def test_una_cuenta_de_agencia_no_queda_de_responsable_de_tienda():
    tareas = [
        _t("afuera", orden=0, asignado=99),
        _t("pieza", "afuera", orden=1, para="agencia", tipo="banners"),
    ]
    plan = m0090.aplanar(tareas, con_tarjeta=set(), externos={99})
    assert "responsable_id" not in plan["cambios"]["pieza"]


def test_una_pieza_de_tienda_no_lleva_responsable_y_lo_que_ya_tenia_se_respeta():
    tareas = [
        _t("afuera", orden=0, asignado=7),
        _t("rompe", "afuera", orden=1, para="tienda", tipo="cenefas", asignado=3),
        _t("ban", "afuera", orden=2, para="agencia", tipo="banners", responsable=8),
    ]
    plan = m0090.aplanar(tareas, con_tarjeta=set(), externos=set())
    assert "responsable_id" not in plan["cambios"]["rompe"]
    assert "responsable_id" not in plan["cambios"]["ban"]


def test_una_tarea_con_su_tarjeta_cuenta_como_pieza_aunque_no_tenga_tipo():
    tareas = [_t("afuera", orden=0), _t("ex", "afuera", orden=1)]
    assert m0090.aplanar(tareas, con_tarjeta={"ex"}, externos=set())["borrar"] == ["afuera"]
    assert m0090.aplanar(tareas, con_tarjeta=set(), externos=set())["borrar"] == []


def test_las_acciones_sin_nada_anidado_no_se_tocan():
    tareas = [_t("x", orden=5), _t("y", orden=9, barra="br-2"), _t("z", orden=0, barra="br-2")]
    assert m0090.aplanar(tareas, con_tarjeta=set(), externos=set()) == {"cambios": {}, "borrar": [], "archivos": {}}
    # Si una acción tiene algo anidado, las demás igual quedan como estaban.
    tareas.append(_t("hija", "x", orden=6))
    plan = m0090.aplanar(tareas, con_tarjeta=set(), externos=set())
    assert set(plan["cambios"]) == {"x", "hija"}


# --- La migración: las plantillas guardadas -------------------------------------------

def test_una_plantilla_guardada_se_aplana_igual():
    tareas = [
        {"id": "t1", "titulo": "Brief", "asignadoA": 7, "descripcion": "Lo de siempre"},
        {"id": "t2", "titulo": "Banners", "parentId": "t1", "para": "agencia", "agencia": "Publicis", "tipo": "banners"},
        {"id": "t3", "titulo": "Retiro", "asignadoA": 4},
        {"id": "t4", "titulo": "Fotos", "parentId": "t3"},
    ]
    nuevas = m0090.aplanar_plantilla(tareas)
    assert [t["id"] for t in nuevas] == ["t2", "t3", "t4"]
    assert all(t["parentId"] is None for t in nuevas)
    assert nuevas[0]["descripcion"] == "Lo de siempre" and nuevas[0]["responsable"] == 7
    assert "responsable" not in nuevas[2]
    # La original no se toca.
    assert tareas[1]["parentId"] == "t1"


# --- El responsable de Tienda, con la API ---------------------------------------------

if URL:
    from app.models.calendario import CalendarioTarea
    from test_tablero_agencia_api import Cliente, _avisos, _pedir_banners, _persona, correr

_con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")


@_con_base
def test_el_responsable_de_tienda_la_tiene_en_mis_tareas_y_la_sigue():
    async def prueba(d):
        lider, lucia, aprob = Cliente(d.http, d.lider), Cliente(d.http, d.lucia), Cliente(d.http, d.aprob2)
        tarea_id, r = await _pedir_banners(d, d.lucia, responsable=d.aprob2.id)
        assert r["responsable"] == d.aprob2.id
        # En Mis tareas de quien la lleva por Tienda, aunque no la haga.
        mias = (await aprob.get("/calendario/mis-tareas")).json()
        [t] = [t for t in mias if t["id"] == tarea_id]
        assert t["responsable"] == d.aprob2.id and t["asignadoA"] is None and t["para"] == "agencia"
        # Y es "suya" en el tablero (se ve aunque la acción quede lejos).
        r = await aprob.get(f"/calendario/tareas/{tarea_id}/entregas")
        assert r.status_code == 200, r.text

        # Cambiar el responsable lo hace quien gestiona las tareas, y le avisa.
        assert (await lucia.patch(f"/calendario/tareas/{tarea_id}", json={"responsable": d.lucia.id})).status_code == 403
        r = await lider.patch(f"/calendario/tareas/{tarea_id}", json={"responsable": d.lucia.id})
        assert r.status_code == 200, r.text
        assert any("te dejó de responsable" in n.mensaje for n in await _avisos(d, d.lucia, tarea_id))
        assert not [t for t in (await aprob.get("/calendario/mis-tareas")).json() if t["id"] == tarea_id]

        # Una cuenta de una agencia no es responsable de Tienda.
        r = await lider.patch(f"/calendario/tareas/{tarea_id}", json={"responsable": d.a1.id})
        assert r.status_code == 422
        # Sacárselo.
        r = await lider.patch(f"/calendario/tareas/{tarea_id}", json={"responsable": None})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, tarea_id)).responsable_id is None
    correr(prueba)


@_con_base
def test_una_tarea_de_tienda_no_lleva_responsable_aparte():
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        # Al crearla, el responsable de una tarea de Tienda no se guarda: la
        # lleva quien la tiene asignada.
        tid = f"ta-ti-{uuid.uuid4().hex[:8]}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": tid, "titulo": "Textos", "asignadoA": d.lucia.id, "responsable": d.aprob2.id})
        assert r.status_code == 201 and r.json()["responsable"] is None
        assert (await lider.patch(f"/calendario/tareas/{tid}", json={"responsable": d.aprob2.id})).status_code == 422

        # Si una de la agencia pasa a alguien de Tienda, deja de tener responsable aparte.
        pieza, _ = await _pedir_banners(d, d.lider, responsable=d.aprob2.id)
        r = await lider.patch(f"/calendario/tareas/{pieza}", json={"asignadoA": d.lucia.id})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, pieza)
            assert (t.para, t.responsable_id) == ("tienda", None)
    correr(prueba)


@_con_base
def test_quien_solo_pide_piezas_crea_la_tarea_para_la_agencia_en_el_primer_nivel():
    async def prueba(d):
        nath = await _persona(d, "Nath Pide", permisos=("calendario.view", "calendario.pedidos"))
        tarea_id, r = await _pedir_banners(d, nath, responsable=nath.id)
        assert r["para"] == "agencia" and r["responsable"] == nath.id
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, tarea_id)).parent_id is None
        # Y nadie la cuelga de otra.
        r = await Cliente(d.http, nath).post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-x-{uuid.uuid4().hex[:8]}", "parentId": tarea_id, "titulo": "Adentro"})
        assert r.status_code == 422
    correr(prueba)
