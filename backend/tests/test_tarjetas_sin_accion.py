"""Las tarjetas sin acción, creadas desde Tableros (24/11/2026).

Ivan: "deberíamos poder crear acciones o tarjetas también de cosas que estén
por fuera del calendario, quizás mismo en los tableros podríamos tener la
opción de crear una tarjeta". Cuelgan de la acción de sistema de su mundo
(app/services/sin_accion.py): se ven, se entregan y se revisan como cualquier
tarjeta, pero no son del calendario.

Las de base necesitan TEST_DATABASE_URL; corren en una transacción que se
deshace al final.
"""
import os
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.api.routes import calendario as rutas
from app.services import avisos_por_mail, calendario_consultas, revision_ia, sin_accion

URL = os.environ.get("TEST_DATABASE_URL")
_con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")


# ---------------------------------------------------------------------------
# Puras
# ---------------------------------------------------------------------------

def test_cada_mundo_tiene_su_accion_de_sistema():
    assert sin_accion.id_de("tienda_inglesa") == "sin-accion-tienda_inglesa"
    assert "sin-accion-redexpres" in sin_accion.IDS
    assert sin_accion.es_sin_accion("sin-accion-tienda_inglesa")
    # Cualquier id con esa forma: ninguna acción común lo puede usar.
    assert sin_accion.es_sin_accion("sin-accion-otra-cosa")
    assert not sin_accion.es_sin_accion("br-ciberlunes") and not sin_accion.es_sin_accion(None)


def test_toca_cualquier_ventana_del_alcance():
    # Del 2000 al 2099: nunca queda afuera de lo que ve alguien del calendario.
    assert sin_accion.DESDE <= date(2020, 1, 1) and sin_accion.HASTA >= date(2090, 12, 31)


def test_el_nombre_para_los_textos():
    assert sin_accion.nombre_para_texto(SimpleNamespace(id="sin-accion-tienda_inglesa", nombre="Sin acción")) is None
    assert sin_accion.nombre_para_texto(SimpleNamespace(id="br-1", nombre="Ciberlunes")) == "Ciberlunes"


def test_los_avisos_dicen_sin_accion():
    v = date(2026, 12, 3)
    assert rutas.mensaje_de_asignacion("Lucía", "Video", None, v) == "Lucía te asignó una tarea sin acción: Video. Vence el 03/12."
    assert rutas.mensaje_de_asignacion("Lucía", "Video", "Ciberlunes", None) == "Lucía te asignó una tarea en Ciberlunes: Video."
    assert rutas.mensaje_de_tarea_hecha("Lucía", "Video", None) == "Lucía terminó la tarea «Video» (sin acción)."
    assert rutas.mensaje_de_responsable("Lucía", "Banners", None, "Publicis", None) == \
        "Lucía te dejó de responsable de «Banners» (sin acción) (la hace Publicis)."
    # Lo de siempre no cambia.
    assert rutas.mensaje_de_tarea_hecha("Lucía", "Video", "") == "Lucía terminó la tarea «Video» de una acción."


def test_el_mail_de_una_tarjeta_sin_accion_lleva_al_tablero():
    n = SimpleNamespace(origen_tipo="calendario_tarea", origen_ref="sin-accion-tienda_inglesa:ta-123", watchlist_item_id=None)
    assert avisos_por_mail.destino(n) == "/entregas?tarea=ta-123"
    n = SimpleNamespace(origen_tipo="calendario_tarea", origen_ref="br-1:ta-123", watchlist_item_id=None)
    assert avisos_por_mail.destino(n) == "/calendario?accion=br-1"


def test_don_tino_la_nombra_sin_link():
    b = SimpleNamespace(id="sin-accion-tienda_inglesa", nombre="Sin acción", mundo="tienda_inglesa", seccion="comercial", banda="Sin acción")
    ref = calendario_consultas.ref_accion(b)
    assert ref == {"nombre": "Sin acción", "mundo": "Tienda Inglesa", "sin_accion": True}


def test_la_ia_sabe_que_es_un_pedido_suelto():
    c = revision_ia.Contexto(
        tipo_pieza="banner", brief={}, mundo="tienda_inglesa", accion="", accion_desde=None, accion_hasta=None,
        tarea="Banners febrero", fase="Entrega", ronda=1, comentario=None, hoy=date(2026, 11, 24),
    )
    texto = revision_ia.texto_del_pedido(c)
    assert "Acción: ninguna: es un pedido suelto" in texto and "Mundo: Tienda Inglesa" in texto
    con = revision_ia.Contexto(**{**c.__dict__, "accion": "Ciberlunes"})
    assert "Acción: Ciberlunes" in revision_ia.texto_del_pedido(con)
    # Lo que arma el Contexto desde la acción.
    assert revision_ia._accion_para_la_ia(SimpleNamespace(id="sin-accion-tienda_inglesa", nombre="Sin acción",
                                                          desde=date(2000, 1, 1), hasta=date(2099, 12, 31))) ==         {"accion": "", "accion_desde": None, "accion_hasta": None}


# ---------------------------------------------------------------------------
# De punta a punta, con la API y una base de verdad
# ---------------------------------------------------------------------------

if URL:
    from sqlalchemy import select

    from app.models.calendario import CalendarioBarra, CalendarioTarea
    from app.models.notificacion import Notificacion
    from test_tablero_agencia_api import JPEG, MUNDO, Cliente, _persona, _tarjeta, correr


def _id() -> str:
    return f"ta-{uuid.uuid4().hex[:10]}"


async def _crear(d, quien, **campos):
    cuerpo = {"id": _id(), "mundo": MUNDO, **campos}
    return cuerpo["id"], await Cliente(d.http, quien).post("/calendario/tarjetas", json=cuerpo)


def _banners_para_pampa(d, **extra):
    return {"tipo": "banners", "opciones": ["header"], "titulo": "Banners febrero", "descripcion": "Search sin CTA",
            "para": "agencia", "agencia": f"Agencia Pampa {d.sufijo}", "responsable": d.lider.id, **extra}


async def _avisos_de(d, usuario, tarea_id) -> list:
    async with d.Sesion() as s:
        return (await s.execute(
            select(Notificacion).where(Notificacion.user_id == usuario.id, Notificacion.origen_ref.contains(tarea_id))
            .order_by(Notificacion.id)
        )).scalars().all()


@_con_base
def test_lucia_crea_una_tarjeta_sin_accion_y_la_agencia_la_ve_y_la_entrega():
    async def prueba(d):
        tarea_id, r = await _crear(d, d.lucia, **_banners_para_pampa(d))
        assert r.status_code == 201, r.text
        assert r.json()["titulo"] == "Banners febrero" and r.json()["para"] == "agencia"
        # Cuelga de la acción de sistema del mundo.
        async with d.Sesion() as s:
            tarea = await s.get(CalendarioTarea, tarea_id)
            assert tarea.barra_id == sin_accion.id_de(MUNDO) and tarea.responsable_id == d.lider.id

        # La agencia la ve en su tablero, "Sin acción", y la entrega.
        ana = Cliente(d.http, d.a1)
        tarjeta = await _tarjeta(ana, tarea_id)
        assert tarjeta is not None and tarjeta["accion"]["nombre"] == "Sin acción" and tarjeta["accion"]["sinAccion"] is True
        detalle = (await ana.get(f"/calendario/tareas/{tarea_id}/entregas")).json()
        assert detalle["accion"]["sinAccion"] is True and detalle["tarea"]["descripcion"] == "Search sin CTA"
        archivos = [("imagenes", ("a.jpg", JPEG, "image/jpeg")), ("miniaturas", ("m.jpg", JPEG, "image/jpeg"))]
        r = await ana.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-sa-{d.sufijo}"}, files=archivos)
        assert r.status_code == 201, r.text
        # Otra agencia no la ve.
        assert await _tarjeta(Cliente(d.http, d.b1), tarea_id) is None
        assert (await Cliente(d.http, d.b1).get(f"/calendario/tareas/{tarea_id}/entregas")).status_code == 404

        # A Lucía (la aprueba quien la pidió) le llega para revisar; al
        # responsable, que quedó a cargo, y la tiene en Mis tareas.
        para_revisar = await _avisos_de(d, d.lucia, tarea_id)
        assert any("(Sin acción)" in n.mensaje and "Te toca revisarla" in n.mensaje for n in para_revisar)
        al_responsable = await _avisos_de(d, d.lider, tarea_id)
        assert any("responsable" in n.mensaje and "(sin acción)" in n.mensaje for n in al_responsable)
        mias = (await Cliente(d.http, d.lider).get("/calendario/mis-tareas")).json()
        fila = next(t for t in mias if t["id"] == tarea_id)
        assert fila["accion"]["sinAccion"] is True and fila["accion"]["nombre"] == "Sin acción"
        # El análisis de entregas la cuenta sin romperse.
        assert (await Cliente(d.http, d.promo).get("/calendario/entregas/metricas", params={"mundo": MUNDO})).status_code == 200
    correr(prueba)


@_con_base
def test_no_es_del_calendario():
    async def prueba(d):
        tarea_id, r = await _crear(d, d.lucia, **_banners_para_pampa(d))
        assert r.status_code == 201, r.text
        lider = Cliente(d.http, d.lider)
        datos = (await lider.get("/calendario/datos", params={"mundo": MUNDO})).json()
        assert not any(sin_accion.es_sin_accion(b["id"]) for b in datos["barras"])
        assert tarea_id not in [t["id"] for b in datos["barras"] for t in b.get("tareas", [])]
        oculta = sin_accion.id_de(MUNDO)
        # No se abre, ni se cambia, ni se le cargan tareas, piezas o avisos por la acción.
        assert (await lider.get(f"/calendario/ubicar/{oculta}")).status_code == 404
        assert (await lider.patch(f"/calendario/barras/{oculta}", json={"nombre": "Otra"})).status_code == 404
        assert (await lider.delete(f"/calendario/barras/{oculta}")).status_code == 404
        r = await lider.post(f"/calendario/barras/{oculta}/tareas", json={"id": _id(), "titulo": "Algo"})
        assert r.status_code == 404
        r = await lider.post(f"/calendario/barras/{oculta}/copiar", json={"id": f"br-c-{d.sufijo}", "desde": "2026-12-01"})
        assert r.status_code in (404, 422)
        # Ni una copia de otra acción toma ese id (se volvería la oculta).
        r = await Cliente(d.http, d.promo).post(f"/calendario/barras/{d.ciber.id}/copiar", json={
            "id": sin_accion.id_de("tienda_express"), "desde": "2026-12-01"})
        assert r.status_code == 422, r.text
        # Y nadie crea una acción con ese id.
        r = await Cliente(d.http, d.promo).post("/calendario/barras", json={
            "id": sin_accion.id_de("tienda_express"), "mundo": "tienda_inglesa", "seccion": "comercial",
            "banda": "MEGA EVENTO", "nombre": "Trampa", "desde": "2026-12-01", "hasta": "2026-12-03"})
        assert r.status_code == 422, r.text
        # Don Tino no la lista como acción.
        async with d.Sesion() as s:
            barras = await calendario_consultas.FuenteCalendario(s).barras([MUNDO])
        assert not any(sin_accion.es_sin_accion(b.id) for b in barras)
    correr(prueba)


@_con_base
def test_quien_la_puede_crear():
    async def prueba(d):
        cuerpo = _banners_para_pampa(d)
        # El equipo con calendario.pedidos (Lucía) o calendario.tareas (el líder): sí.
        assert (await _crear(d, d.lider, **cuerpo))[1].status_code == 201
        # La agencia, no.
        assert (await _crear(d, d.a1, **cuerpo))[1].status_code == 403
        # Alguien que ve el calendario pero no crea tareas, no.
        assert (await _crear(d, d.aprob2, **cuerpo))[1].status_code == 403
        # Quien no ve el calendario ("No lo ve"), no.
        assert (await _crear(d, d.sin_cal, **cuerpo))[1].status_code == 403
        # Con el calendario en "1 mes", sí, y la ve en su tablero.
        tarea_id, r = await _crear(d, d.limitado, **cuerpo)
        assert r.status_code == 201, r.text
        assert await _tarjeta(Cliente(d.http, d.limitado), tarea_id) is not None
        # Otro mundo: el suyo no; uno que no existe, tampoco.
        r = await Cliente(d.http, d.lucia).post("/calendario/tarjetas", json={"id": _id(), "mundo": "redexpres", **cuerpo})
        assert r.status_code == 403
        r = await Cliente(d.http, d.lucia).post("/calendario/tarjetas", json={"id": _id(), "mundo": "marte", **cuerpo})
        assert r.status_code == 422
        # Sin acción no hay vencimiento contado desde la acción, ni tareas adentro de otra.
        assert (await _crear(d, d.lucia, **cuerpo, ancla="inicio", anclaDias=-2))[1].status_code == 422
        assert (await _crear(d, d.lucia, **cuerpo, parentId="ta-madre"))[1].status_code == 422
    correr(prueba)


@_con_base
def test_otra_cosa_para_alguien_de_tienda_es_una_tarjeta():
    async def prueba(d):
        diseno = await _persona(d, "Disenio Tienda", permisos=("calendario.view",))
        tarea_id, r = await _crear(d, d.lucia, titulo="Video institucional", para="tienda", asignadoA=diseno.id)
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, tarea_id)).tipo == sin_accion.TIPO_POR_DEFECTO
        # Tiene su tarjeta (está en el tablero) y a quien la hace le llega el pedido.
        tarjeta = await _tarjeta(Cliente(d.http, diseno), tarea_id)
        assert tarjeta is not None and tarjeta["titulo"] == "Video institucional"
        avisos = await _avisos_de(d, diseno, tarea_id)
        assert any("te pidió" in n.mensaje for n in avisos)
        # Sin nadie que la haga, no: la tarjeta no tendría tablero.
        assert (await _crear(d, d.lucia, titulo="Algo", para="tienda"))[1].status_code == 422
        # Ni sin nombre ni tipo.
        assert (await _crear(d, d.lucia, para="tienda", asignadoA=diseno.id))[1].status_code == 422
    correr(prueba)


@_con_base
def test_con_tipo_y_sin_nombre_va_el_del_tipo_y_un_reintento_no_duplica():
    async def prueba(d):
        cuerpo = {**_banners_para_pampa(d), "titulo": ""}
        tarea_id, r = await _crear(d, d.lucia, **cuerpo)
        assert r.status_code == 201 and r.json()["titulo"] == "Banners"
        r = await Cliente(d.http, d.lucia).post("/calendario/tarjetas", json={"id": tarea_id, "mundo": MUNDO, **cuerpo})
        assert r.status_code == 201 and r.json().get("yaExistia") is True
        async with d.Sesion() as s:
            n = len((await s.execute(select(CalendarioTarea).where(CalendarioTarea.id == tarea_id))).scalars().all())
            barras = (await s.execute(select(CalendarioBarra).where(CalendarioBarra.id == sin_accion.id_de(MUNDO)))).scalars().all()
        assert n == 1 and len(barras) == 1
    correr(prueba)


@_con_base
def test_se_edita_desde_la_ficha_como_cualquier_tarea():
    async def prueba(d):
        tarea_id, r = await _crear(d, d.lucia, **_banners_para_pampa(d, responsable=None))
        assert r.status_code == 201, r.text
        lider = Cliente(d.http, d.lider)
        vence = (date.today() + timedelta(days=10)).isoformat()
        r = await lider.patch(f"/calendario/tareas/{tarea_id}", json={
            "titulo": "Banners de febrero", "descripcion": "Con CTA Ver más", "vence": vence, "responsable": d.lucia.id})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, tarea_id)
            assert (t.titulo, t.descripcion, t.vence.isoformat(), t.responsable_id) == \
                ("Banners de febrero", "Con CTA Ver más", vence, d.lucia.id)
        avisos = await _avisos_de(d, d.lucia, tarea_id)
        assert any("responsable" in n.mensaje and "(sin acción)" in n.mensaje for n in avisos)
        # Quien solo pide piezas no la edita después (como en una acción).
        r = await Cliente(d.http, d.lucia).patch(f"/calendario/tareas/{tarea_id}", json={"titulo": "Otro"})
        assert r.status_code == 403
    correr(prueba)
