"""Pedirle trabajo a cualquier agencia (26/11/2026, H-018 y H-090 del cuaderno).

Ivan (25/11/2026): «esta plataforma la van a usar varias agencias a la vez,
así que tiene que adaptarse a su forma de trabajar, no al revés». Hasta acá
«¿Quién la hace?» ofrecía solo los tres tableros de siempre (Publicis, Another
Monday y Diseñadores): la agencia que sí tenía cuenta, o una recién dada de
alta, no estaba. Y una tarjeta creada desde Tableros no se podía pasar a otra
agencia: la de verdad nunca recibía el pedido.

- GET /calendario/tableros: los tres tableros (aunque no tengan cuentas) y
  cualquier otra agencia con alguna cuenta activa. Son las mismas que acepta
  el alta de una tarea, y con esa lista el equipo ve una pestaña por agencia.
- PATCH /calendario/tareas/{id} con `agencia`: se la pasa a esa agencia
  entera, como si se hubiera pedido para ella. Lo hace quien gestiona tareas.

Necesitan TEST_DATABASE_URL; corren en una transacción que se deshace al final.
"""
import os
import uuid

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")

if URL:
    from sqlalchemy import select, update

    from app.models.calendario import CalendarioTarea
    from app.models.notificacion import Notificacion
    from app.models.user import User
    from test_tablero_agencia_api import MUNDO, Cliente, _persona, _tarjeta, correr

TRES_TABLEROS = ["Publicis", "Another Monday", "Diseñadores"]


async def _agencias(cliente) -> list[dict]:
    r = await cliente.get("/calendario/tableros", params={"mundo": MUNDO})
    assert r.status_code == 200, r.text
    return r.json()


async def _nueva_tarjeta(d, quien, **campos):
    """Una «Nueva tarjeta» de Tableros (sin acción)."""
    tarea_id = f"ta-{uuid.uuid4().hex[:10]}"
    r = await Cliente(d.http, quien).post("/calendario/tarjetas", json={
        "id": tarea_id, "mundo": MUNDO, "titulo": "Flyer Ciberlunes", "tipo": "banners", "opciones": ["Header"],
        **campos,
    })
    return tarea_id, r


async def _le_pidieron(d, usuario, tarea_id) -> int:
    """Cuántos avisos de «te pidió» le llegaron a esa cuenta por esa tarjeta."""
    async with d.Sesion() as s:
        mensajes = (await s.execute(
            select(Notificacion.mensaje).where(
                Notificacion.user_id == usuario.id, Notificacion.origen_ref.contains(tarea_id),
            )
        )).scalars().all()
    return sum("te pidió" in m for m in mensajes)


async def _quien_la_hace(d, tarea_id) -> tuple:
    async with d.Sesion() as s:
        t = await s.get(CalendarioTarea, tarea_id)
        return t.para, t.agencia, t.asignado_a_id


def test_quien_la_hace_ofrece_todas_las_agencias_que_pueden_recibir_trabajo():
    async def prueba(d):
        lucia, promo = Cliente(d.http, d.lucia), Cliente(d.http, d.promo)
        pampa, sur = f"Agencia Pampa {d.sufijo}", f"Estudio Sur {d.sufijo}"

        lista = await _agencias(lucia)
        nombres = [a["nombre"] for a in lista]
        cuentas = {a["nombre"]: a["cuentas"] for a in lista}
        # Primero los tres de siempre (valen aunque no tengan cuentas) y
        # después las demás, por nombre. Pampa tiene dos cuentas escritas
        # distinto («agencia  pampa»): es una sola agencia.
        assert nombres[:3] == TRES_TABLEROS
        assert pampa in nombres and sur in nombres
        assert 2 < nombres.index(pampa) < nombres.index(sur)
        assert cuentas[pampa] == 2 and cuentas[sur] == 1
        assert len([n for n in nombres if n.lower().split() == pampa.lower().split()]) == 1

        # Una agencia dada de alta recién en el panel aparece enseguida.
        nueva = f"Agencia Sofía {d.sufijo}"
        r = await promo.post("/admin/users", json={
            "email": f"sofia.{d.sufijo}@example.com", "full_name": "Sofía Nueva",
            "password": "Clave-segura-123", "es_externo": True, "empresa": nueva})
        assert r.status_code == 201, r.text
        assert {"nombre": nueva, "cuentas": 1} in await _agencias(lucia)

        # Una cuya única cuenta se dio de baja no: nadie vería la tarjeta, y
        # el alta tampoco la acepta (es la misma regla).
        baja = await _persona(d, "Carla Baja", externo=True, empresa=f"Estudio Baja {d.sufijo}")
        async with d.Sesion() as s:
            await s.execute(update(User).where(User.id == baja.id).values(is_active=False))
            await s.commit()
        assert f"Estudio Baja {d.sufijo}" not in [a["nombre"] for a in await _agencias(lucia)]
        _, r = await _nueva_tarjeta(d, d.lucia, para="agencia", agencia=f"Estudio Baja {d.sufijo}")
        assert r.status_code == 422, r.text

        # A cada una de la lista se le puede pedir, y la tarjeta le llega.
        for agencia in await _agencias(lucia):
            tarea_id, r = await _nueva_tarjeta(d, d.lucia, para="agencia", agencia=agencia["nombre"])
            assert r.status_code == 201, (agencia, r.text)
            if agencia["nombre"] == pampa:
                assert await _tarjeta(Cliente(d.http, d.a1), tarea_id) is not None

        # A una cuenta externa, solo la suya: también si no es de las tres.
        assert await _agencias(Cliente(d.http, d.a1)) == [{"nombre": pampa, "cuentas": 2}]
    correr(prueba)


def test_una_tarjeta_de_tableros_se_le_pasa_a_otra_agencia():
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        ana, bruno = Cliente(d.http, d.a1), Cliente(d.http, d.b1)
        pampa, sur = f"Agencia Pampa {d.sufijo}", f"Estudio Sur {d.sufijo}"
        # Se pidió para Publicis, que todavía no tiene cuentas.
        tarea_id, r = await _nueva_tarjeta(d, d.lucia, para="agencia", agencia="Publicis", responsable=d.lider.id)
        assert r.status_code == 201, r.text
        ruta = f"/calendario/tareas/{tarea_id}"

        # Quien gestiona las tareas se la pasa a Pampa (escrita como sea): la
        # ven sus dos cuentas, les llega el pedido, y sigue con su responsable.
        r = await lider.patch(ruta, json={"agencia": f"  agencia pampa {d.sufijo} "})
        assert r.status_code == 200, r.text
        assert r.json()["avisados"] == 2
        assert await _quien_la_hace(d, tarea_id) == ("agencia", pampa, None)
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, tarea_id)).responsable_id == d.lider.id
        assert await _tarjeta(ana, tarea_id) is not None and await _le_pidieron(d, d.a1, tarea_id) == 1
        assert await _tarjeta(bruno, tarea_id) is None

        # Pasársela otra vez a la misma no cambia nada ni avisa de nuevo.
        r = await lider.patch(ruta, json={"agencia": pampa})
        assert r.status_code == 200 and r.json()["avisados"] == 0
        assert await _le_pidieron(d, d.a1, tarea_id) == 1

        # De Pampa a Estudio Sur, aunque la tuviera Ana en persona: Pampa deja
        # de verla (Ana incluida) y le llega a Sur.
        assert (await lider.patch(ruta, json={"asignadoA": d.a1.id})).status_code == 200
        r = await lider.patch(ruta, json={"agencia": sur})
        assert r.status_code == 200, r.text
        assert await _quien_la_hace(d, tarea_id) == ("agencia", sur, None)
        assert (await ana.get(f"{ruta}/entregas")).status_code == 404
        assert await _tarjeta(bruno, tarea_id) is not None and await _le_pidieron(d, d.b1, tarea_id) == 1

        # Una que hacía alguien de Tienda también pasa a una agencia, y esa
        # persona deja de tenerla.
        fer = await _persona(d, "Fer Tienda", permisos=("calendario.view",))
        otra, r = await _nueva_tarjeta(d, d.lucia, para="tienda", asignadoA=fer.id)
        assert r.status_code == 201, r.text
        r = await lider.patch(f"/calendario/tareas/{otra}", json={"agencia": pampa})
        assert r.status_code == 200, r.text
        assert await _quien_la_hace(d, otra) == ("agencia", pampa, None)
        assert await _tarjeta(ana, otra) is not None
        assert otra not in [t["id"] for t in (await Cliente(d.http, fer).get("/calendario/mis-tareas")).json()]
    correr(prueba)


def test_pasarla_a_otra_agencia_lo_hace_quien_gestiona_las_tareas():
    async def prueba(d):
        pampa = f"Agencia Pampa {d.sufijo}"
        tarea_id, r = await _nueva_tarjeta(d, d.lucia, para="agencia", agencia="Publicis")
        assert r.status_code == 201, r.text
        suya, r = await _nueva_tarjeta(d, d.lucia, para="agencia", agencia=pampa)
        assert r.status_code == 201, r.text
        ruta = f"/calendario/tareas/{tarea_id}"

        # Quien solo pide piezas (Lucía) no la reparte después.
        assert (await Cliente(d.http, d.lucia).patch(ruta, json={"agencia": pampa})).status_code == 403
        # La agencia tampoco: una tarjeta ajena para ella no existe (404, como
        # lo de otra agencia), y la suya no se la pasa a otra.
        ana = Cliente(d.http, d.a1)
        assert (await ana.patch(ruta, json={"agencia": pampa})).status_code == 404
        assert (await ana.patch(f"/calendario/tareas/{suya}", json={"agencia": "Publicis"})).status_code in (403, 404)
        assert await _quien_la_hace(d, suya) == ("agencia", pampa, None)
        lider = Cliente(d.http, d.lider)
        # Una agencia sin ninguna cuenta (y que no es de las tres) no vería la tarjeta.
        r = await lider.patch(ruta, json={"agencia": "Otra Agencia SA"})
        assert r.status_code == 422 and "no tiene ninguna cuenta" in r.json()["detail"]
        # Vacía no, y a una agencia y a una persona a la vez tampoco.
        assert (await lider.patch(ruta, json={"agencia": None})).status_code == 422
        assert (await lider.patch(ruta, json={"agencia": "   "})).status_code == 422
        assert (await lider.patch(ruta, json={"agencia": pampa, "asignadoA": d.a1.id})).status_code == 422
        # Nada de eso la movió de Publicis.
        assert await _quien_la_hace(d, tarea_id) == ("agencia", "Publicis", None)
        assert await _tarjeta(ana, tarea_id) is None
    correr(prueba)
