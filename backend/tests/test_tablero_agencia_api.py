"""El tablero de la agencia y el alcance del calendario, de punta a punta con
la API y una base de verdad (0070).

Pedido de Ivan (16/11/2026): la agencia entra a un tablero estilo Trello
(Ingresado, En proceso, Esperando feedback, Finalizado, Archivado) con las
tarjetas que le pide el equipo desde cada acción del calendario; y cada
persona ve del calendario solo lo que un admin le habilitó (No lo ve / 1 mes /
2 meses / 12 meses / Todo).

Necesita una base Postgres en la última migración (TEST_DATABASE_URL); sin
ella se saltea. Todo corre adentro de una transacción que se deshace al final.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")

if URL:
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.api.routes.calendario_ical import firma_del_link
    from app.core import alcance
    from app.core.database import get_db
    from app.core.rate_limit import limiter
    from app.core.security import create_access_token, hash_password
    from app.main import app
    from app.models.calendario import (
        CalendarioAviso, CalendarioBarra, CalendarioPieza, CalendarioPlantilla, CalendarioTarea,
    )
    from app.models.entregas import CalendarioEntrega, CalendarioFase
    from app.models.notificacion import Notificacion
    from app.models.role import ALL_PERMISSIONS
    from app.models.user import User
    from app.services import calendario_consultas as cc
    from app.services import entregas as reglas

API = "/api/v1"
MUNDO = "tienda_inglesa"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
_HASH: list[str] = []


def _clave() -> str:
    if not _HASH:
        _HASH.append(hash_password("Clave-de-prueba-1"))
    return _HASH[0]


class Datos:
    pass


async def _sembrar(s) -> "Datos":
    d = Datos()
    d.sufijo = sufijo = uuid.uuid4().hex[:8]
    hoy = alcance.hoy_en_uruguay()
    d.hoy = hoy
    ahora = datetime.now(timezone.utc)

    def persona(nombre, *, permisos=("calendario.view",), externo=False, empresa=None, alc=None, superusuario=False):
        u = User(
            email=f"{nombre.lower().replace(' ', '.')}.{sufijo}@prueba-tablero.test", full_name=nombre,
            hashed_password=_clave(), permissions=list(permisos), mundos=[MUNDO], is_active=True,
            is_superuser=superusuario, es_externo=externo, empresa=empresa,
            calendario_alcance=alc or alcance.por_defecto(externo),
            must_change_password=False, password_changed_at=ahora,
        )
        s.add(u)
        return u

    d.promo = persona("Promo Jefa", permisos=tuple(ALL_PERMISSIONS), superusuario=True)
    # Lucía: del equipo, edita el calendario y pide piezas, pero NO gestiona
    # tareas (rol "Usuario"; calendario.pedidos desde la 0071).
    d.lucia = persona("Lucia Equipo", permisos=("calendario.view", "calendario.edit", "calendario.pedidos"))
    d.lider = persona("Lider Tareas", permisos=("calendario.view", "calendario.edit", "calendario.tareas"))
    d.aprob2 = persona("Marca Aprobadora")
    d.limitado = persona("Interno Limitado", permisos=("calendario.view", "calendario.edit", "calendario.pedidos"), alc="1m")
    d.sin_cal = persona("Interno Sin Calendario", permisos=("calendario.view", "calendario.edit", "calendario.pedidos"), alc="nada")
    d.a1 = persona("Ana Pampa", externo=True, empresa=f"Agencia Pampa {sufijo}")
    d.a2 = persona("Beto Pampa", externo=True, empresa=f"agencia  pampa {sufijo}")
    d.b1 = persona("Bruno Sur", externo=True, empresa=f"Estudio Sur {sufijo}")
    await s.flush()

    def barra(clave, nombre, desde, dias=3):
        b = CalendarioBarra(
            id=f"br-{clave}-{sufijo}", mundo=MUNDO, seccion="comercial", banda="MEGA EVENTO", carril=0,
            nombre=nombre, desde=desde, hasta=desde + timedelta(days=dias), creado_por_id=d.promo.id,
        )
        s.add(b)
        return b

    d.ciber = barra("ciber", f"Ciberlunes {sufijo}", hoy + timedelta(days=60))
    d.ahora = barra("ahora", f"Promo de hoy {sufijo}", hoy)
    d.viejo = barra("viejo", f"Navidad 2025 {sufijo}", hoy.replace(year=2025, month=12, day=20))
    d.lejos = barra("lejos", f"Algo de 2099 {sufijo}", hoy.replace(year=2099))
    await s.flush()
    return d


class Cliente:
    def __init__(self, http, usuario):
        self.http = http
        self.headers = {"Authorization": f"Bearer {create_access_token(usuario.id)}"}

    async def get(self, ruta, **kw):
        return await self.http.get(API + ruta, headers=self.headers, **kw)

    async def post(self, ruta, **kw):
        return await self.http.post(API + ruta, headers=self.headers, **kw)

    async def patch(self, ruta, **kw):
        return await self.http.patch(API + ruta, headers=self.headers, **kw)

    async def put(self, ruta, **kw):
        return await self.http.put(API + ruta, headers=self.headers, **kw)


def correr(prueba):
    asyncio.run(_correr(prueba))


async def _correr(prueba):
    engine = create_async_engine(URL, poolclass=NullPool, connect_args={"statement_cache_size": 0})
    conn = await engine.connect()
    trans = await conn.begin()
    Sesion = async_sessionmaker(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")

    async def get_db_de_prueba():
        async with Sesion() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = get_db_de_prueba
    limite_antes = limiter.enabled
    limiter.enabled = False
    try:
        async with Sesion() as s:
            d = await _sembrar(s)
            await s.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as http:
            d.http, d.Sesion = http, Sesion
            await prueba(d)
    finally:
        limiter.enabled = limite_antes
        app.dependency_overrides.pop(get_db, None)
        await trans.rollback()
        await conn.close()
        await engine.dispose()


async def _avisos(d, usuario, tarea_id=None) -> list:
    async with d.Sesion() as s:
        q = select(Notificacion).where(Notificacion.user_id == usuario.id)
        if tarea_id:
            q = q.where(Notificacion.origen_ref.contains(tarea_id))
        return (await s.execute(q.order_by(Notificacion.id))).scalars().all()


async def _tarjeta(cliente, tarea_id):
    r = await cliente.get("/calendario/entregas", params={"mundo": MUNDO})
    assert r.status_code == 200, r.text
    return next((t for t in r.json()["tarjetas"] if t["tareaId"] == tarea_id), None)


async def _persona(d, nombre, *, permisos=("calendario.view",), alc=None, externo=False, empresa=None):
    """Una cuenta más, para la prueba que la necesita (las de _sembrar son de todas)."""
    async with d.Sesion() as s:
        u = User(
            email=f"{nombre.lower().replace(' ', '.')}.{d.sufijo}@prueba-tablero.test", full_name=nombre,
            hashed_password=_clave(), permissions=list(permisos), mundos=[MUNDO], is_active=True,
            is_superuser=False, es_externo=externo, empresa=empresa,
            calendario_alcance=alc or alcance.por_defecto(externo),
            must_change_password=False, password_changed_at=datetime.now(timezone.utc),
        )
        s.add(u)
        await s.commit()
        return u


async def _estado(d, tarea_id) -> str:
    async with d.Sesion() as s:
        return (await s.get(CalendarioTarea, tarea_id)).estado


async def _entregar_link(cliente, tarea_id, version_id):
    r = await cliente.post(f"/calendario/tareas/{tarea_id}/versiones", data={
        "versionId": version_id, "link": "https://drive.example.com/ronda"})
    return r


async def _pedir_banners(d, quien, *, barra=None, tarea_id=None, **extra):
    tarea_id = tarea_id or f"ta-{uuid.uuid4().hex[:10]}"
    cuerpo = {"id": tarea_id, "tipo": "banners", "opciones": ["header", "Checkout"], "detalles": {"cta": "Ver ofertas"},
              "para": "agencia", "agencia": f"AGENCIA PAMPA {d.sufijo}", "ancla": "inicio", "anclaDias": -3}
    cuerpo.update(extra)
    r = await Cliente(d.http, quien).post(f"/calendario/barras/{(barra or d.ciber).id}/tareas", json=cuerpo)
    assert r.status_code == 201, r.text
    return tarea_id, r.json()


# ---------------------------------------------------------------------------
# El alcance del calendario
# ---------------------------------------------------------------------------

def test_por_defecto_la_agencia_no_ve_el_calendario_y_el_equipo_si():
    async def prueba(d):
        promo = Cliente(d.http, d.promo)
        r = await promo.post("/admin/users", json={
            "email": f"nueva.{d.sufijo}@pampa.uy", "full_name": "Nueva", "password": "Clave-segura-123",
            "es_externo": True, "empresa": "Agencia Nueva"})
        assert r.status_code == 201, r.text
        r2 = await promo.post("/admin/users", json={
            "email": f"interna.{d.sufijo}@ti.uy", "full_name": "Interna", "password": "Clave-segura-123"})
        assert r2.status_code == 201, r2.text
        lista = {u["id"]: u for u in (await promo.get("/admin/users")).json()}
        assert lista[r.json()["id"]]["calendario_alcance"] == "nada"
        assert lista[r2.json()["id"]]["calendario_alcance"] == "todo"
        me = (await Cliente(d.http, d.a1).get("/auth/me")).json()
        assert me["calendario_alcance"] == "nada" and me["ventana"] is None
        # El admin le da 2 meses: lo ve en /me con sus fechas.
        r = await promo.patch(f"/admin/users/{d.a1.id}/alcance", json={"calendario_alcance": "2m"})
        assert r.status_code == 200, r.text
        me = (await Cliente(d.http, d.a1).get("/auth/me")).json()
        v = alcance.ventana_de_alcance(d.hoy, "2m")
        assert me["calendario_alcance"] == "2m" and me["ventana"] == {"desde": v[0].isoformat(), "hasta": v[1].isoformat()}
        # Un alcance que no existe, no.
        assert (await promo.patch(f"/admin/users/{d.a1.id}/alcance", json={"calendario_alcance": "3m"})).status_code == 422
    correr(prueba)


def test_no_lo_ve_queda_afuera_de_todo_el_calendario_pero_ve_su_tablero():
    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lucia)
        for usuario in (d.a1, d.sin_cal):
            c = Cliente(d.http, usuario)
            assert (await c.get("/calendario/datos", params={"mundo": MUNDO})).status_code == 403
            assert (await c.get("/calendario/personas", params={"mundo": MUNDO})).status_code == 403
            # Mis tareas: a la agencia no (lo suyo es el tablero); a alguien del
            # equipo sí, siempre: lo que le asignan le tiene que llegar.
            assert (await c.get("/calendario/mis-tareas")).status_code == (403 if usuario.es_externo else 200)
            assert (await c.get("/calendario/ical/link")).status_code == 403
            assert (await c.get(f"/calendario/ubicar/{d.ahora.id}")).status_code == 404
            r = await d.http.get(f"{API}/calendario/ical/{usuario.id}/{firma_del_link(usuario.id, 0)}.ics")
            assert r.status_code == 404
            async with d.Sesion() as s:
                yo = await s.get(User, usuario.id)
                texto = await cc.ejecutar("calendario_acciones", {}, yo, s)
            assert "error" in texto and d.ahora.nombre not in texto
        # Ni cargar una acción quien edita pero no ve el calendario.
        r = await Cliente(d.http, d.sin_cal).post("/calendario/barras", json={
            "id": f"br-x-{d.sufijo}", "seccion": "comercial", "banda": "X", "nombre": "X",
            "desde": d.hoy.isoformat(), "hasta": d.hoy.isoformat()})
        assert r.status_code == 403
        # Pero su tablero sí: la agencia ve su tarjeta de una campaña de dentro de 2 meses.
        tarjeta = await _tarjeta(Cliente(d.http, d.a1), tarea_id)
        assert tarjeta is not None and tarjeta["columna"] == "ingresado"
        assert set(tarjeta["accion"]) == {"id", "mundo", "nombre", "color", "desde", "hasta"}
    correr(prueba)


def test_un_interno_con_alcance_limitado_tambien_se_filtra():
    async def prueba(d):
        c = Cliente(d.http, d.limitado)
        datos = (await c.get("/calendario/datos", params={"mundo": MUNDO})).json()
        ids = {b["id"] for b in datos["barras"]}
        assert d.ahora.id in ids and not ids & {d.ciber.id, d.viejo.id, d.lejos.id}
        assert datos["opaca"] is True
        assert (await c.get(f"/calendario/ubicar/{d.ciber.id}")).status_code == 404
        # Una tarjeta ajena de afuera de su alcance: no existe (ni en el
        # buscador). Una suya (la aprueba él) aunque la campaña quede fuera de
        # su alcance: sí, entera (abajo).
        ajena, _ = await _pedir_banners(d, d.lucia)
        assert (await c.get(f"/calendario/tareas/{ajena}/entregas")).status_code == 404
        assert await _tarjeta(c, ajena) is None
        r = await c.get("/calendario/entregas/buscar", params={"mundo": MUNDO, "q": f"Ciberlunes {d.sufijo} banners"})
        assert ajena not in [t["tareaId"] for t in r.json()["enTablero"] + r.json()["archivadas"]]
        # No puede pedir piezas en una acción que no ve; en una que ve, sí.
        r = await c.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-l-{d.sufijo}", "tipo": "totem", "para": "agencia", "agencia": f"Agencia Pampa {d.sufijo}"})
        assert r.status_code == 404
        propia, _ = await _pedir_banners(d, d.limitado, barra=d.ahora)
        assert (await c.get(f"/calendario/tareas/{propia}/entregas")).status_code == 200

        # «Navidad - Banners», dentro de dos meses, la aprueba él (1 mes): la
        # ve en su tablero, la abre, ve la imagen, la decide y la finaliza.
        # Revisión del 16/11/2026: antes ninguna prueba lo cubría.
        suya, _ = await _pedir_banners(d, d.lider)
        r = await Cliente(d.http, d.lider).put(f"/calendario/tareas/{suya}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.limitado.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text
        a1 = Cliente(d.http, d.a1)
        archivos = [("imagenes", ("a.jpg", JPEG, "image/jpeg")), ("miniaturas", ("m.jpg", JPEG, "image/jpeg"))]
        r = await a1.post(f"/calendario/tareas/{suya}/versiones", data={"versionId": f"ve-l1-{d.sufijo}"}, files=archivos)
        assert r.status_code == 201, r.text
        tarjeta = await _tarjeta(c, suya)
        assert tarjeta is not None and tarjeta["columna"] == "esperando" and tarjeta["puedo"]["decidir"] is True
        detalle = await c.get(f"/calendario/tareas/{suya}/entregas")
        assert detalle.status_code == 200, detalle.text
        imagen = detalle.json()["fases"][0]["versiones"][0]["imagenes"][0]["id"]
        assert (await c.get(f"/calendario/entregas/imagenes/{imagen}")).status_code == 200
        # Decide (pide cambios): a quien ve una parte no le viaja el contador de todos.
        r = await c.post(f"/calendario/versiones/ve-l1-{d.sufijo}/decision", json={
            "decision": "cambios", "comentario": "El precio más grande"})
        assert r.status_code == 200, r.text
        assert r.json()["rev"] is None
        assert (await _entregar_link(a1, suya, f"ve-l2-{d.sufijo}")).status_code == 201
        r = await c.post(f"/calendario/tareas/{suya}/mover", json={"desde": "esperando", "a": "finalizado"})
        assert r.status_code == 200, r.text
        assert r.json()["columna"] == "finalizado" and r.json()["rev"] is None
        # Ni mover una acción fuera de lo que ve.
        r = await c.patch(f"/calendario/barras/{d.ahora.id}", json={"desde": d.ciber.desde.isoformat(),
                                                                    "hasta": d.ciber.hasta.isoformat()})
        assert r.status_code == 422
    correr(prueba)


def test_todo_es_sin_limite():
    async def prueba(d):
        datos = (await Cliente(d.http, d.promo).get("/calendario/datos", params={"mundo": MUNDO})).json()
        ids = {b["id"] for b in datos["barras"]}
        assert {d.ahora.id, d.ciber.id, d.viejo.id, d.lejos.id} <= ids
        assert "opaca" not in datos
    correr(prueba)


# ---------------------------------------------------------------------------
# Pedir una tarjeta
# ---------------------------------------------------------------------------

def test_lucia_pide_una_tarjeta_para_la_agencia_y_le_llega_a_toda_la_agencia():
    async def prueba(d):
        tarea_id, r = await _pedir_banners(d, d.lucia)
        assert r["titulo"] == f"{d.ciber.nombre} - Banners"
        assert r["para"] == "agencia" and r["agencia"] == f"Agencia Pampa {d.sufijo}"
        assert r["vence"] == (d.ciber.desde - timedelta(days=3)).isoformat()
        assert r["entrega"]["columna"] == "ingresado"
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, tarea_id)
            e = await s.get(CalendarioEntrega, tarea_id)
            fases = (await s.execute(select(CalendarioFase).where(CalendarioFase.tarea_id == tarea_id))).scalars().all()
        assert t.opciones == ["Header", "Checkout"] and t.detalles == {"cta": "Ver ofertas"}
        assert t.ancla == "inicio" and t.ancla_dias == -3
        assert e.aprobadores == [d.lucia.id] and [f.nombre for f in fases] == ["Entrega"]
        assert "Header (web 1920×416 · mobile 640×260)" in e.brief["detalle"]
        # Un aviso a cada cuenta de la agencia, que dice quién pidió qué; a la otra agencia, nada.
        for u in (d.a1, d.a2):
            avisos = await _avisos(d, u, tarea_id)
            assert len(avisos) == 1 and avisos[0].origen_tipo == "calendario_entrega"
            assert avisos[0].mensaje.startswith(f"Lucia Equipo te pidió: {d.ciber.nombre} - Banners (Header, Checkout).")
        assert await _avisos(d, d.b1, tarea_id) == []
        # La agencia lo ve en su campanita aunque no vea el calendario.
        r = await Cliente(d.http, d.a1).get("/notificaciones")
        assert any(tarea_id in (n["origen_ref"] or "") for n in r.json())
        # Una tarea común: Lucía sí, con calendario.pedidos (17/11/2026: las
        # tareas las crea el equipo). Quien solo edita el calendario, no.
        r = await Cliente(d.http, d.lucia).post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-c-{d.sufijo}", "titulo": "Común", "asignadoA": d.aprob2.id})
        assert r.status_code == 201, r.text
        solo_edita = await _persona(d, "Solo Edita", permisos=("calendario.view", "calendario.edit"))
        r = await Cliente(d.http, solo_edita).post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-c2-{d.sufijo}", "titulo": "Común"})
        assert r.status_code == 403 and "calendario.pedidos" in r.json()["detail"]
        r = await Cliente(d.http, solo_edita).post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-c3-{d.sufijo}", "tipo": "banners", "opciones": ["Header"], "asignadoA": d.lucia.id})
        assert r.status_code == 403
        # Una agencia que no tiene cuentas: no.
        r = await Cliente(d.http, d.lucia).post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-n-{d.sufijo}", "tipo": "totem", "para": "agencia", "agencia": "No Existe SA"})
        assert r.status_code == 422
    correr(prueba)


def test_una_plantilla_con_dos_tarjetas_le_manda_un_solo_aviso_a_cada_uno():
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        r = await lider.put(f"/calendario/plantillas/pl-{d.sufijo}", json={
            "mundo": MUNDO, "nombre": "Mega", "tareas": [
                {"id": "t1", "titulo": "Banners", "tipo": "banners", "opciones": ["Header"], "para": "agencia",
                 "agencia": f"Agencia Pampa {d.sufijo}", "ancla": "inicio", "dias": -3},
                {"id": "t2", "titulo": "Cenefas", "tipo": "cenefas", "opciones": ["A4"], "para": "agencia",
                 "agencia": f"Agencia Pampa {d.sufijo}", "ancla": "inicio", "dias": -2},
                {"id": "t3", "titulo": "Retirar carteles", "ancla": "fin", "dias": 1, "asignadoA": d.aprob2.id},
            ]})
        assert r.status_code == 200, r.text
        ids = {"t1": f"ta-p1-{d.sufijo}", "t2": f"ta-p2-{d.sufijo}", "t3": f"ta-p3-{d.sufijo}"}
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/plantilla", json={"plantillaId": f"pl-{d.sufijo}", "ids": ids})
        assert r.status_code == 201, r.text
        assert r.json()["tarjetas"] == 2
        # Un reintento de lo mismo no crea ni avisa otra vez.
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/plantilla", json={"plantillaId": f"pl-{d.sufijo}", "ids": ids})
        assert r.json().get("yaExistia") is True
        for u in (d.a1, d.a2):
            async with d.Sesion() as s:
                avisos = (await s.execute(select(Notificacion).where(
                    Notificacion.user_id == u.id, Notificacion.origen_tipo == "calendario_entrega"))).scalars().all()
            assert len(avisos) == 1 and "te pidió 2 tarjetas" in avisos[0].mensaje
        a1 = Cliente(d.http, d.a1)
        tarjetas = {t["tareaId"]: t for t in (await a1.get("/calendario/entregas", params={"mundo": MUNDO})).json()["tarjetas"]}
        assert set(tarjetas) == {ids["t1"], ids["t2"]}
        assert tarjetas[ids["t1"]]["titulo"] == f"{d.ciber.nombre} - Banners"
        # La tarea común de Tienda no es tarjeta y le llegó el aviso de siempre.
        assert len(await _avisos(d, d.aprob2, ids["t3"])) == 1
    correr(prueba)


def test_otra_agencia_fuera_de_la_plataforma_la_carga_alguien_del_equipo():
    async def prueba(d):
        tarea_id = f"ta-f-{d.sufijo}"
        lider = Cliente(d.http, d.lider)
        r = await lider.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
            "id": tarea_id, "tipo": "mailing", "opciones": ["Físico (impreso)"], "detalles": {"paginas": 16},
            "para": "fuera", "agencia": "Estudio Afuera"})
        assert r.status_code == 422  # falta quién carga
        r = await lider.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
            "id": tarea_id, "tipo": "mailing", "opciones": ["Físico (impreso)"], "detalles": {"paginas": 16},
            "para": "fuera", "agencia": "Estudio Afuera", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text
        tarjeta = await _tarjeta(lider, tarea_id)
        assert tarjeta["hace"] == {"tipo": "fuera", "nombre": "Estudio Afuera", "carga": "Lucia Equipo"}
        # Lucía carga lo que mandó la agencia de afuera.
        r = await Cliente(d.http, d.lucia).post(f"/calendario/tareas/{tarea_id}/versiones", data={
            "versionId": f"ve-f-{d.sufijo}", "link": "https://drive.example.com/folleto"})
        assert r.status_code == 201, r.text
        assert (await _tarjeta(lider, tarea_id))["columna"] == "esperando"
    correr(prueba)


# ---------------------------------------------------------------------------
# El recorrido de una tarjeta
# ---------------------------------------------------------------------------

def test_el_recorrido_completo_con_las_reglas_de_cada_uno():
    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lucia)
        a1, a2, b1, lucia = (Cliente(d.http, u) for u in (d.a1, d.a2, d.b1, d.lucia))
        mover = lambda c, desde, a, **kw: c.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": desde, "a": a, **kw})  # noqa: E731

        # La otra agencia no la ve por ningún lado.
        assert await _tarjeta(b1, tarea_id) is None
        assert (await b1.get(f"/calendario/tareas/{tarea_id}/entregas")).status_code == 404
        assert (await mover(b1, "ingresado", "en-proceso")).status_code == 404
        r = await b1.get("/calendario/entregas/buscar", params={"mundo": MUNDO, "q": "ciberlunes banners"})
        assert r.json()["enTablero"] == [] and r.json()["archivadas"] == []

        # La agencia la arranca; no puede finalizarla.
        t = await _tarjeta(a1, tarea_id)
        assert t["puedo"]["mover"] == ["en-proceso", "esperando"]
        assert (await mover(a1, "ingresado", "finalizado")).status_code == 403
        r = await mover(a1, "ingresado", "en-proceso")
        assert r.status_code == 200 and r.json()["columna"] == "en-proceso"
        # Si otra cuenta de la agencia la quiere mover desde donde estaba: ya se movió.
        r = await mover(a2, "ingresado", "en-proceso")
        assert r.status_code == 409 and "En proceso" in r.json()["detail"]
        # A Esperando feedback se llega entregando, no arrastrando.
        assert (await mover(a1, "en-proceso", "esperando")).status_code == 409

        # Entrega con imagen; le avisa a quien aprueba (Lucía).
        archivos = [("imagenes", ("a.jpg", JPEG, "image/jpeg")), ("miniaturas", ("m.jpg", JPEG, "image/jpeg"))]
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-1-{d.sufijo}"}, files=archivos)
        assert r.status_code == 201, r.text
        assert (await _tarjeta(lucia, tarea_id))["columna"] == "esperando"
        assert len(await _avisos(d, d.lucia, tarea_id)) == 1
        # La agencia no se la devuelve ni la aprueba.
        assert (await mover(a1, "esperando", "en-proceso", comentario="x")).status_code == 403
        assert (await mover(a1, "esperando", "finalizado")).status_code == 403

        # Lucía la devuelve: sin decir qué cambiar, no.
        assert (await mover(lucia, "esperando", "en-proceso")).status_code == 422
        r = await mover(lucia, "esperando", "en-proceso", comentario="El precio más grande")
        assert r.status_code == 200 and r.json()["columna"] == "en-proceso"
        t = await _tarjeta(a1, tarea_id)
        assert t["volvioConCambios"] is True and t["columna"] == "en-proceso"
        for u in (d.a1, d.a2):
            cambios = [n for n in await _avisos(d, u, tarea_id) if n.origen_ref.endswith(":cambios")]
            assert len(cambios) == 1

        # Reentrega (con un link solo) y Lucía la finaliza.
        r = await a2.post(f"/calendario/tareas/{tarea_id}/versiones", data={
            "versionId": f"ve-2-{d.sufijo}", "link": "https://drive.example.com/ronda2"})
        assert r.status_code == 201, r.text
        r = await mover(lucia, "esperando", "finalizado")
        assert r.status_code == 200 and r.json()["columna"] == "finalizado"
        for u in (d.a1, d.a2):
            aprobadas = [n for n in await _avisos(d, u, tarea_id) if n.origen_ref.endswith(":aprobada")]
            assert len(aprobadas) == 1
        # Quien la creó es quien la aprobó: no se avisa a sí misma.
        assert not [n for n in await _avisos(d, d.lucia, tarea_id) if n.origen_ref.endswith(":hecha")]

        # Archivado a mano y de vuelta.
        assert (await mover(a1, "finalizado", "archivado")).status_code == 403
        assert (await mover(lucia, "finalizado", "archivado")).json()["columna"] == "archivado"
        # «Ver más» de Archivado: la ve quien la lleva; ni la otra agencia ni
        # un interno con el alcance limitado al que no le toca (revisión del
        # 16/11/2026: antes solo lo pedía Lucía, que ve todo).
        def ids_de(r):
            assert r.status_code == 200, r.text
            return [t["tareaId"] for t in r.json()["tarjetas"]]
        assert tarea_id in ids_de(await lucia.get("/calendario/entregas/archivadas", params={"mundo": MUNDO}))
        for otro in (b1, Cliente(d.http, d.limitado)):
            assert tarea_id not in ids_de(await otro.get("/calendario/entregas/archivadas", params={"mundo": MUNDO}))
        assert (await mover(lucia, "archivado", "finalizado")).json()["columna"] == "finalizado"

        # 11 días después (fecha simulada: la finalización y el desarchivo,
        # 11 días antes), pasa sola a Archivado; el loop diario lo anota.
        async with d.Sesion() as s:
            e = await s.get(CalendarioEntrega, tarea_id)
            e.finalizada_at = datetime.now(timezone.utc) - timedelta(days=11)
            e.desarchivada_at = datetime.now(timezone.utc) - timedelta(days=11)
            await s.commit()
        assert (await _tarjeta(lucia, tarea_id))["columna"] == "archivado"
        async with d.Sesion() as s:
            assert await reglas.archivar_finalizadas(s) >= 1
            e = await s.get(CalendarioEntrega, tarea_id)
            assert e.archivada_at is not None and e.archivada_por_id is None

        # A los 30 días en Archivado ya ni se carga; el buscador la encuentra aparte.
        async with d.Sesion() as s:
            e = await s.get(CalendarioEntrega, tarea_id)
            e.archivada_at = datetime.now(timezone.utc) - timedelta(days=31)
            await s.commit()
        assert await _tarjeta(lucia, tarea_id) is None
        for q in ("ciberlunes banners", f"Ciberlunes {d.sufijo} - Banners", "CÍBERLUNES   banners"):
            r = await a1.get("/calendario/entregas/buscar", params={"mundo": MUNDO, "q": q})
            assert [t["tareaId"] for t in r.json()["archivadas"]] == [tarea_id], (q, r.text)
        # La otra agencia, tampoco en lo archivado de verdad.
        r = await b1.get("/calendario/entregas/buscar", params={"mundo": MUNDO, "q": "ciberlunes banners"})
        assert r.json()["enTablero"] == [] and r.json()["archivadas"] == []
        # Y se abre, con sus materiales.
        detalle = (await a1.get(f"/calendario/tareas/{tarea_id}/entregas")).json()
        imagen = detalle["fases"][0]["versiones"][0]["imagenes"][0]["id"]
        assert (await lucia.get(f"/calendario/entregas/imagenes/{imagen}")).status_code == 200
    correr(prueba)


def test_con_cadena_de_aprobadores_finaliza_recien_cuando_aprueba_el_ultimo():
    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lider)
        lider, marca, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.aprob2), Cliente(d.http, d.a1)
        r = await lider.put(f"/calendario/tareas/{tarea_id}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.aprob2.id, d.lucia.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text
        await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={
            "versionId": f"ve-c-{d.sufijo}", "link": "https://drive.example.com/c"})
        lucia = Cliente(d.http, d.lucia)
        # A Lucía todavía no le toca: primero aprueba Marca.
        t = await _tarjeta(lucia, tarea_id)
        assert t["puedo"]["decidir"] is False
        r = await lucia.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": "esperando", "a": "finalizado"})
        assert r.status_code == 403
        r = await marca.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": "esperando", "a": "finalizado"})
        assert r.status_code == 200 and r.json()["columna"] == "esperando"  # sigue esperando a Lucía
        r = await lucia.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": "esperando", "a": "finalizado"})
        assert r.status_code == 200 and r.json()["columna"] == "finalizado"
        # Finalizada: a la agencia y a quien la creó (el líder), una vez.
        assert len([n for n in await _avisos(d, d.lider, tarea_id) if n.origen_ref.endswith(":hecha")]) == 1
    correr(prueba)


def test_el_tablero_carga_poco_y_pagina_lo_archivado():
    async def prueba(d):
        lucia = Cliente(d.http, d.lucia)
        ids = []
        for i in range(25):
            tarea_id, _ = await _pedir_banners(d, d.lucia, barra=d.ahora, tarea_id=f"ta-arch{i}-{d.sufijo}")
            ids.append(tarea_id)
        async with d.Sesion() as s:
            for i, tarea_id in enumerate(ids):
                e = await s.get(CalendarioEntrega, tarea_id)
                e.momento, e.fase_actual_id = "aprobada", None
                e.finalizada_at = datetime.now(timezone.utc) - timedelta(days=12 + i)
            await s.commit()
        r = (await lucia.get("/calendario/entregas", params={"mundo": MUNDO})).json()
        archivadas = [t for t in r["tarjetas"] if t["columna"] == "archivado"]
        # 25 (o más, si la base de prueba ya tenía): viajan las primeras 20 y
        # se dice cuántas hay.
        assert len(archivadas) == 20
        assert r["archivadas"]["total"] >= 25 and r["archivadas"]["mostradas"] == 20
        # Liviana: ni historia ni marcas.
        assert "fases" not in archivadas[0] and "marcas" not in str(archivadas[0])
        # "Ver más", de a 20, hasta traerlas todas.
        vistas = {t["tareaId"] for t in archivadas}
        desde = 20
        while desde < r["archivadas"]["total"]:
            mas = (await lucia.get("/calendario/entregas/archivadas", params={"mundo": MUNDO, "desde": desde})).json()
            assert 0 < len(mas["tarjetas"]) <= 20
            vistas |= {t["tareaId"] for t in mas["tarjetas"]}
            desde = mas["hasta"]
        assert vistas >= set(ids)
    correr(prueba)


# ---------------------------------------------------------------------------
# Lo que encontró la revisión del 16/11/2026
# ---------------------------------------------------------------------------

def test_quien_pide_y_carga_lo_de_una_agencia_de_afuera_lo_puede_aprobar():
    """El camino por defecto del formulario: Lucía pide un mailing a una agencia
    de afuera y lo carga ella. Antes la tarjeta quedaba trabada en Esperando
    feedback: era la única aprobadora y no podía decidir sobre lo que subió."""
    async def prueba(d):
        tarea_id = f"ta-fa-{d.sufijo}"
        lucia = Cliente(d.http, d.lucia)
        r = await lucia.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
            "id": tarea_id, "tipo": "mailing", "opciones": ["Físico (impreso)"], "detalles": {"paginas": 16},
            "para": "fuera", "agencia": "Estudio Afuera", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text
        r = await lucia.post(f"/calendario/tareas/{tarea_id}/versiones", data={
            "versionId": f"ve-fa-{d.sufijo}", "link": "https://drive.example.com/folleto"})
        assert r.status_code == 201, r.text
        tarjeta = await _tarjeta(lucia, tarea_id)
        assert tarjeta["columna"] == "esperando" and tarjeta["puedo"]["decidir"] is True
        # Es la única que decide: ve lo que encontró la IA (antes, no).
        detalle = (await lucia.get(f"/calendario/tareas/{tarea_id}/entregas")).json()
        assert detalle["puedo"]["verRevisionIA"] is True
        assert (await lucia.get(f"/calendario/versiones/ve-fa-{d.sufijo}/revision-ia")).status_code == 200
        # «Configurar» con quien carga entre quienes aprueban: se puede guardar
        # (antes daba 422 y había que sacarla de la cadena). Revisión del 16/11/2026.
        fase = detalle["fases"][0]["id"]
        r = await Cliente(d.http, d.lider).put(f"/calendario/tareas/{tarea_id}/entregas", json={
            "tipoPieza": "otro", "aprobadores": [d.lucia.id], "fases": [{"id": fase, "nombre": "Entrega"}]})
        assert r.status_code == 200, r.text
        r = await lucia.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": "esperando", "a": "finalizado"})
        assert r.status_code == 200, r.text
        assert (await _tarjeta(lucia, tarea_id))["columna"] == "finalizado"
        # El retrabajo de esa ronda es de la agencia de afuera, no de Lucía.
        r = await Cliente(d.http, d.lider).get("/calendario/entregas/metricas", params={"mundo": MUNDO})
        assert r.status_code == 200, r.text
        grupos = {g["clave"]: g for g in r.json()["porResponsable"]}
        assert d.lucia.id not in grupos
        assert grupos["fuera:estudio afuera"]["nombre"] == "Estudio Afuera (agencia de afuera)"
    correr(prueba)


def test_una_pieza_de_tienda_que_uno_se_pide_a_si_mismo_la_aprueba_otro():
    """Nadie decide sobre lo que subió: si Lucía se pide una pieza a sí misma no
    puede quedar de única aprobadora. Nace sin cadena, al entregar se les avisa
    a quienes pueden aprobar como respaldo, y uno de ellos la finaliza."""
    async def prueba(d):
        tarea_id = f"ta-yo-{d.sufijo}"
        lucia = Cliente(d.http, d.lucia)
        r = await lucia.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
            "id": tarea_id, "tipo": "banners", "opciones": ["Header"], "para": "tienda", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioEntrega, tarea_id)).aprobadores == []
        r = await lucia.post(f"/calendario/tareas/{tarea_id}/versiones", data={
            "versionId": f"ve-yo-{d.sufijo}", "link": "https://drive.example.com/banner"})
        assert r.status_code == 201, r.text
        # Les llegó a quienes lideran (y no a ella ni a la agencia).
        assert len(await _avisos(d, d.lider, tarea_id)) == 1
        assert await _avisos(d, d.lucia, tarea_id) == [] and await _avisos(d, d.a1, tarea_id) == []
        r = await lucia.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": "esperando", "a": "finalizado"})
        assert r.status_code == 403
        r = await Cliente(d.http, d.lider).post(
            f"/calendario/tareas/{tarea_id}/mover", json={"desde": "esperando", "a": "finalizado"})
        assert r.status_code == 200, r.text
        # Pedida para otra persona, sigue como siempre: la aprueba quien la pidió.
        otra = f"ta-otra-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
            "id": otra, "tipo": "banners", "opciones": ["Header"], "para": "tienda", "asignadoA": d.aprob2.id})
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioEntrega, otra)).aprobadores == [d.lucia.id]
    correr(prueba)


def test_al_renombrar_o_copiar_la_accion_las_tarjetas_llevan_el_nombre_nuevo():
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        a_mano = f"ta-mano-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": a_mano, "titulo": "Revisar textos", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text

        r = await lider.patch(f"/calendario/barras/{d.ciber.id}", json={"nombre": f"Ciber Monday {d.sufijo}"})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, tarea_id)).titulo == f"Ciber Monday {d.sufijo} - Banners"
            assert (await s.get(CalendarioTarea, a_mano)).titulo == "Revisar textos"   # la escrita a mano no se toca

        copia = f"br-copia-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/copiar", json={
            "id": copia, "desde": (d.hoy + timedelta(days=20)).isoformat(), "nombre": f"Hot Sale {d.sufijo}"})
        assert r.status_code == 201, r.text
        tareas = r.json()["barra"]["tareas"]
        pieza = next(x for x in tareas if x.get("tipo") == "banners")
        assert pieza["titulo"] == f"Hot Sale {d.sufijo} - Banners"
        # La copia ya trae su tarjeta: la ficha no la muestra como tarea común.
        assert pieza.get("entrega"), pieza
        # Y a la agencia le llegó con el nombre de la acción nueva.
        avisos = await _avisos(d, d.a1, pieza["id"])
        assert avisos and f"Hot Sale {d.sufijo} - Banners" in avisos[0].mensaje
    correr(prueba)


def test_corregir_la_empresa_de_la_agencia_no_le_saca_las_tarjetas_ni_el_calendario():
    async def prueba(d):
        promo = Cliente(d.http, d.promo)
        # Estudio Sur tiene una sola cuenta, con el calendario habilitado a 1 mes.
        assert (await promo.patch(f"/admin/users/{d.b1.id}/alcance", json={"calendario_alcance": "1m"})).status_code == 200
        tarea_id, _ = await _pedir_banners(d, d.lider, agencia=f"Estudio Sur {d.sufijo}")
        assert await _tarjeta(Cliente(d.http, d.b1), tarea_id) is not None

        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={
            "es_externo": True, "empresa": f"Estudio del Sur {d.sufijo}"})
        assert r.status_code == 200, r.text
        # Sigue viendo su tarjeta (pasó al nombre nuevo) y conserva su alcance.
        assert await _tarjeta(Cliente(d.http, d.b1), tarea_id) is not None
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, tarea_id)).agencia == f"Estudio del Sur {d.sufijo}"
            assert (await s.get(User, d.b1.id)).calendario_alcance == "1m"

        # Pampa tiene dos cuentas: si una se va a otra empresa, las tarjetas
        # siguen siendo de la agencia (de la otra cuenta), no se van con ella.
        de_pampa, _ = await _pedir_banners(d, d.lider)
        r = await promo.patch(f"/admin/users/{d.a1.id}/externo", json={
            "es_externo": True, "empresa": f"Otra Agencia {d.sufijo}"})
        assert r.status_code == 200, r.text
        assert await _tarjeta(Cliente(d.http, d.a2), de_pampa) is not None
        assert await _tarjeta(Cliente(d.http, d.a1), de_pampa) is None
    correr(prueba)


def test_pasar_a_alguien_del_equipo_a_externo_lo_deja_sin_calendario():
    async def prueba(d):
        promo = Cliente(d.http, d.promo)
        r = await promo.patch(f"/admin/users/{d.aprob2.id}/externo", json={"es_externo": True, "empresa": "Agencia X"})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            assert (await s.get(User, d.aprob2.id)).calendario_alcance == "nada"
    correr(prueba)


def test_lo_que_no_se_ve_tampoco_se_borra():
    async def prueba(d):
        # Con alcance de 1 mes, una acción de dentro de dos meses; y sin calendario, cualquiera.
        for usuario, barra in ((d.limitado, d.ciber), (d.sin_cal, d.ahora)):
            r = await d.http.delete(
                f"{API}/calendario/barras/{barra.id}", headers=Cliente(d.http, usuario).headers)
            assert r.status_code == 404, (usuario.full_name, r.status_code)
            async with d.Sesion() as s:
                assert await s.get(CalendarioBarra, barra.id) is not None
        # La que sí ve, la borra.
        r = await d.http.delete(f"{API}/calendario/barras/{d.ahora.id}", headers=Cliente(d.http, d.limitado).headers)
        assert r.status_code == 200, r.text
    correr(prueba)


def test_al_equipo_sus_tareas_le_llegan_aunque_no_vea_la_accion():
    """Un diseñador con el calendario en «1 mes» o «No lo ve»: lo que le asignan
    le aparece igual en Mis tareas y en la campanita (antes vencía sin que se
    enterara). De la acción ve el nombre, sin enlace a una ficha que no abre."""
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        casos = ((d.limitado, d.ciber, f"ta-l-{d.sufijo}"), (d.sin_cal, d.ahora, f"ta-s-{d.sufijo}"))
        for usuario, barra, tarea_id in casos:
            r = await lider.post(f"/calendario/barras/{barra.id}/tareas", json={
                "id": tarea_id, "titulo": "Preparar el brief", "asignadoA": usuario.id})
            assert r.status_code == 201, r.text
            c = Cliente(d.http, usuario)
            mias = (await c.get("/calendario/mis-tareas")).json()
            tarea = next((x for x in mias if x["id"] == tarea_id), None)
            assert tarea is not None, usuario.full_name
            assert tarea["accion"]["nombre"] == barra.nombre and tarea["accion"].get("fueraDeAlcance") is True
            avisos = (await c.get("/notificaciones")).json()
            assert any(tarea_id in (n["origen_ref"] or "") for n in avisos), usuario.full_name
            # La ficha de esa acción sigue cerrada para esa persona.
            assert (await c.get(f"/calendario/ubicar/{barra.id}")).status_code == 404
        # Una hecha de una acción fuera de su alcance ya no se le muestra.
        r = await Cliente(d.http, d.limitado).patch(f"/calendario/tareas/{casos[0][2]}", json={"estado": "hecha"})
        assert r.status_code == 200, r.text
        mias = (await Cliente(d.http, d.limitado).get("/calendario/mis-tareas")).json()
        assert all(x["id"] != casos[0][2] for x in mias)
        # Quien ve todo no tiene ninguna marcada como fuera de alcance.
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-t-{d.sufijo}", "titulo": "Otra", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text
        mias = (await Cliente(d.http, d.lucia).get("/calendario/mis-tareas")).json()
        assert all("fueraDeAlcance" not in x["accion"] for x in mias)
    correr(prueba)


def test_colocacion_respeta_el_alcance_del_calendario():
    async def prueba(d):
        # Sin calendario no hay lista de acciones con fotos; con 1 mes, la ficha
        # de fotos de una acción de dentro de dos meses no existe para esa persona.
        assert (await Cliente(d.http, d.sin_cal).get("/colocacion/resumen", params={"mundo": MUNDO})).status_code == 403
        limitado = Cliente(d.http, d.limitado)
        assert (await limitado.get("/colocacion/resumen", params={"mundo": MUNDO})).status_code == 200
        assert (await limitado.get(f"/colocacion/acciones/{d.ciber.id}")).status_code == 404
        assert (await limitado.get(f"/colocacion/acciones/{d.ahora.id}")).status_code == 200
        assert (await Cliente(d.http, d.lucia).get(f"/colocacion/acciones/{d.ciber.id}")).status_code == 200
    correr(prueba)


# ---------------------------------------------------------------------------
# La tanda de arreglos del servidor (revisión del 16/11/2026)
# ---------------------------------------------------------------------------

def test_una_pieza_cancelada_se_archiva_y_se_puede_sacar_del_archivo():
    """Antes una pieza cancelada quedaba para siempre en Ingresado o En
    proceso, en rojo, para la agencia y para el equipo: solo se archivaba una
    finalizada, y cerrar la tarea a mano («hecha») no tocaba la tarjeta. Ahora
    el equipo la archiva desde el tablero (y la tarea se cierra), o quien
    lidera cierra la tarea y la tarjeta se archiva; reabrirla la trae de vuelta."""
    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lucia)
        a1, lucia, lider = Cliente(d.http, d.a1), Cliente(d.http, d.lucia), Cliente(d.http, d.lider)
        mover = lambda c, desde, a, **kw: c.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": desde, "a": a, **kw})  # noqa: E731

        async def con_cambios(c):
            return [t["tareaId"] for t in (await c.get("/calendario/mis-entregas")).json()["conCambios"]]

        # La ficha sigue al tablero: arrancarla la pone en proceso; volverla, en pendiente.
        assert (await mover(a1, "ingresado", "en-proceso")).status_code == 200
        assert await _estado(d, tarea_id) == "en-proceso"
        assert (await mover(a1, "en-proceso", "ingresado")).status_code == 200
        assert await _estado(d, tarea_id) == "pendiente"

        # La agencia no la archiva; el equipo de la tarjeta sí, desde Ingresado.
        assert (await mover(a1, "ingresado", "archivado")).status_code == 403
        assert (await mover(Cliente(d.http, d.aprob2), "ingresado", "archivado")).status_code == 403
        r = await mover(lucia, "ingresado", "archivado")
        assert r.status_code == 200 and r.json()["columna"] == "archivado", r.text
        assert await _estado(d, tarea_id) == "hecha"
        t = await _tarjeta(a1, tarea_id)
        assert t["columna"] == "archivado" and t["archivadaEl"] is not None
        assert t["puedo"]["entregar"] is False and t["puedo"]["mover"] == []
        assert (await a1.get(f"/calendario/tareas/{tarea_id}/entregas")).json()["puedo"]["entregar"] is False
        assert (await _entregar_link(a1, tarea_id, f"ve-x-{d.sufijo}")).status_code == 409
        # En el calendario también: la tarea lleva su tarjeta en Archivado.
        datos = (await Cliente(d.http, d.promo).get("/calendario/datos", params={"mundo": MUNDO})).json()
        tareas = next(b for b in datos["barras"] if b["id"] == d.ciber.id)["tareas"]
        assert next(x for x in tareas if x["id"] == tarea_id)["entrega"]["columna"] == "archivado"
        # Sale del archivo solo a su columna, y la tarea se reabre.
        assert (await _tarjeta(lucia, tarea_id))["puedo"]["mover"] == ["ingresado"]
        assert (await mover(lucia, "archivado", "finalizado")).status_code == 422
        r = await mover(lucia, "archivado", "ingresado")
        assert r.status_code == 200 and r.json()["columna"] == "ingresado", r.text
        assert await _estado(d, tarea_id) == "pendiente"

        # Vuelve con cambios y quien lidera la cierra con el tilde de la ficha:
        # la tarjeta pasa a Archivado y deja de esperar a la agencia.
        assert (await _entregar_link(a1, tarea_id, f"ve-c1-{d.sufijo}")).status_code == 201
        assert (await mover(lucia, "esperando", "en-proceso", comentario="El precio más grande")).status_code == 200
        assert tarea_id in await con_cambios(a1)
        assert (await lider.patch(f"/calendario/tareas/{tarea_id}", json={"estado": "hecha"})).status_code == 200
        assert (await _tarjeta(a1, tarea_id))["columna"] == "archivado"
        assert tarea_id not in await con_cambios(a1)
        assert (await _entregar_link(a1, tarea_id, f"ve-c2-{d.sufijo}")).status_code == 409
        # Si la reabre, la tarjeta vuelve sola a su columna.
        assert (await lider.patch(f"/calendario/tareas/{tarea_id}", json={"estado": "en-proceso"})).status_code == 200
        t = await _tarjeta(a1, tarea_id)
        assert t["columna"] == "en-proceso" and t["volvioConCambios"] is True and t["puedo"]["entregar"] is True
        assert tarea_id in await con_cambios(a1)

        # Cerrada otra vez, a los 30 días en Archivado ya no se carga: la
        # encuentra el buscador, aparte.
        assert (await lider.patch(f"/calendario/tareas/{tarea_id}", json={"estado": "hecha"})).status_code == 200
        async with d.Sesion() as s:
            e = await s.get(CalendarioEntrega, tarea_id)
            e.archivada_at = datetime.now(timezone.utc) - timedelta(days=31)
            await s.commit()
        assert await _tarjeta(lucia, tarea_id) is None
        r = await lucia.get("/calendario/entregas/buscar", params={"mundo": MUNDO, "q": f"Ciberlunes {d.sufijo} banners"})
        assert r.json()["enTablero"] == [] and [t["tareaId"] for t in r.json()["archivadas"]] == [tarea_id]
    correr(prueba)


def test_el_archivado_nocturno_deja_en_paz_lo_que_no_le_toca():
    """La pasada diaria archiva lo finalizado hace 10 días o más y lo que
    quedó sin terminar con la tarea cerrada a mano (de antes de este
    arreglo). No toca una finalizada hace 9 días, una que alguien sacó del
    archivo hace 2, ni una activa con la tarea abierta."""
    async def prueba(d):
        ids = {}
        for clave in ("nueve", "desarchivada", "once", "activa", "cerrada"):
            ids[clave], _ = await _pedir_banners(d, d.lucia, barra=d.ahora, tarea_id=f"ta-n{clave}-{d.sufijo}")
        ahora = datetime.now(timezone.utc)
        async with d.Sesion() as s:
            for clave, (fin, desarchivada) in {"nueve": (9, None), "desarchivada": (20, 2), "once": (11, None)}.items():
                e = await s.get(CalendarioEntrega, ids[clave])
                e.momento, e.fase_actual_id = "aprobada", None
                e.finalizada_at = ahora - timedelta(days=fin)
                e.desarchivada_at = ahora - timedelta(days=desarchivada) if desarchivada else None
            # Cerrada a mano antes de que cerrarla archivara la tarjeta.
            (await s.get(CalendarioTarea, ids["cerrada"])).estado = "hecha"
            await s.commit()
        async with d.Sesion() as s:
            assert await reglas.archivar_finalizadas(s) >= 2
        async with d.Sesion() as s:
            entregas = {clave: await s.get(CalendarioEntrega, tid) for clave, tid in ids.items()}
        assert entregas["once"].archivada_at is not None and entregas["once"].archivada_por_id is None
        assert entregas["cerrada"].archivada_at is not None
        for clave in ("nueve", "desarchivada", "activa"):
            assert entregas[clave].archivada_at is None, clave
        assert (await _tarjeta(Cliente(d.http, d.lucia), ids["cerrada"]))["columna"] == "archivado"
    correr(prueba)


def test_agregarle_una_fase_a_una_finalizada_la_reabre():
    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lider)
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        mover = lambda desde, a: lider.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": desde, "a": a})  # noqa: E731
        assert (await _entregar_link(a1, tarea_id, f"ve-r1-{d.sufijo}")).status_code == 201
        assert (await mover("esperando", "finalizado")).json()["columna"] == "finalizado"
        assert (await mover("finalizado", "archivado")).json()["columna"] == "archivado"
        assert await _estado(d, tarea_id) == "hecha"
        fase = (await lider.get(f"/calendario/tareas/{tarea_id}/entregas")).json()["fases"][0]["id"]
        r = await lider.put(f"/calendario/tareas/{tarea_id}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.lider.id],
            "fases": [{"id": fase, "nombre": "Entrega"}, {"nombre": "Ajuste final"}]})
        assert r.status_code == 200, r.text
        assert (await _tarjeta(lider, tarea_id))["columna"] == "en-proceso"
        async with d.Sesion() as s:
            e = await s.get(CalendarioEntrega, tarea_id)
            assert e.momento == "produccion" and e.finalizada_at is None and e.archivada_at is None
        assert await _estado(d, tarea_id) == "en-proceso"
        assert (await _entregar_link(a1, tarea_id, f"ve-r2-{d.sufijo}")).status_code == 201
        assert (await mover("esperando", "finalizado")).json()["columna"] == "finalizado"
        assert await _estado(d, tarea_id) == "hecha"
    correr(prueba)


def test_corregir_el_nombre_de_la_agencia_corrige_sus_plantillas():
    """«Publisis» pasa a llamarse «Publicis»: las plantillas que la nombran
    pasan al nombre nuevo, como sus tarjetas. Y si al aplicar una plantilla
    alguna agencia no tiene cuentas, la respuesta lo dice."""
    async def prueba(d):
        lider, promo = Cliente(d.http, d.lider), Cliente(d.http, d.promo)
        plantilla = f"pl-sur-{d.sufijo}"
        r = await lider.put(f"/calendario/plantillas/{plantilla}", json={
            "mundo": MUNDO, "nombre": "Mega", "tareas": [
                {"id": "t1", "titulo": "Banners", "tipo": "banners", "opciones": ["Header"], "para": "agencia",
                 "agencia": f"Estudio Sur {d.sufijo}", "ancla": "inicio", "dias": -3},
                {"id": "t2", "titulo": "Retirar carteles", "ancla": "fin", "dias": 1},
            ]})
        assert r.status_code == 200, r.text
        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={
            "es_externo": True, "empresa": f"Estudio del Sur {d.sufijo}"})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            tareas = (await s.get(CalendarioPlantilla, plantilla)).tareas
        assert tareas[0]["agencia"] == f"Estudio del Sur {d.sufijo}" and tareas[1].get("agencia") is None

        ids = {"t1": f"ta-s1-{d.sufijo}", "t2": f"ta-s2-{d.sufijo}"}
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/plantilla", json={"plantillaId": plantilla, "ids": ids})
        assert r.status_code == 201, r.text
        assert r.json()["agenciasSinCuentas"] == []
        assert await _tarjeta(Cliente(d.http, d.b1), ids["t1"]) is not None
        assert len(await _avisos(d, d.b1, ids["t1"])) == 1

        # El respaldo: una agencia que se quedó sin cuentas. La tarjeta nace
        # igual (la ve el equipo), y la respuesta lo dice para avisarlo.
        async with d.Sesion() as s:
            (await s.get(User, d.b1.id)).is_active = False
            await s.commit()
        ids = {"t1": f"ta-s3-{d.sufijo}", "t2": f"ta-s4-{d.sufijo}"}
        r = await lider.post(f"/calendario/barras/{d.ahora.id}/plantilla", json={"plantillaId": plantilla, "ids": ids})
        assert r.status_code == 201, r.text
        assert r.json()["agenciasSinCuentas"] == [f"Estudio del Sur {d.sufijo}"]
    correr(prueba)


def test_un_gestor_con_el_calendario_limitado_crea_cuentas_y_no_da_mas_de_lo_que_ve():
    """Un Admin (no superadmin) con «1 mes» crea la cuenta de un diseñador
    nuevo desde el panel (que no manda el alcance): nace con «1 mes», no con
    un 403. Pedir más de lo que ve, a propósito, sí da 403, y nadie se sube ni
    le da a otro más de lo que ve."""
    async def prueba(d):
        gestor = await _persona(d, "Gestor Limitado", permisos=("platform.users.manage", "calendario.view"), alc="1m")
        g = Cliente(d.http, gestor)
        r = await g.post("/admin/users", json={
            "email": f"disenador.{d.sufijo}@ti.uy", "full_name": "Diseñador Nuevo", "password": "Clave-segura-123"})
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            assert (await s.get(User, r.json()["id"])).calendario_alcance == "1m"
        r = await g.post("/admin/users", json={
            "email": f"otro.{d.sufijo}@ti.uy", "full_name": "Otro", "password": "Clave-segura-123",
            "calendario_alcance": "todo"})
        assert r.status_code == 403
        assert (await g.patch(f"/admin/users/{gestor.id}/alcance", json={"calendario_alcance": "todo"})).status_code == 403
        assert (await g.patch(f"/admin/users/{d.lucia.id}/alcance", json={"calendario_alcance": "todo"})).status_code == 403
        assert (await g.patch(f"/admin/users/{d.lucia.id}/alcance", json={"calendario_alcance": "1m"})).status_code == 200
        # Sin gestión de usuarios, nada.
        r = await Cliente(d.http, d.lucia).patch(f"/admin/users/{d.aprob2.id}/alcance", json={"calendario_alcance": "1m"})
        assert r.status_code == 403
    correr(prueba)


@pytest.mark.parametrize("caso", ["cambiar-pieza", "quitar-pieza", "quitar-aviso", "borrar-tarea", "copiar"])
def test_lo_que_no_se_ve_tampoco_se_toca_por_su_id(caso):
    """Alguien con «1 mes» no cambia ni borra piezas, avisos o tareas de una
    acción de dentro de dos meses usando sus ids (de Outlook o de Don Tino),
    ni copia esa acción a su mes para verla entera."""
    async def prueba(d):
        limitado = Cliente(d.http, d.limitado)
        lider_limitado = await _persona(
            d, "Lider Limitado", permisos=("calendario.view", "calendario.edit", "calendario.tareas"), alc="1m")
        async with d.Sesion() as s:
            s.add(CalendarioPieza(id=f"pz-{d.sufijo}", barra_id=d.ciber.id, area="fisico", formato="Cenefas"))
            s.add(CalendarioAviso(id=f"av-{d.sufijo}", barra_id=d.ciber.id, dias_antes=3, destinatarios=[d.lucia.id]))
            s.add(CalendarioTarea(id=f"ta-{d.sufijo}", barra_id=d.ciber.id, titulo="Brief", creado_por_id=d.promo.id))
            await s.commit()
        modelo, fila_id = {
            "cambiar-pieza": (CalendarioPieza, f"pz-{d.sufijo}"),
            "quitar-pieza": (CalendarioPieza, f"pz-{d.sufijo}"),
            "quitar-aviso": (CalendarioAviso, f"av-{d.sufijo}"),
            "borrar-tarea": (CalendarioTarea, f"ta-{d.sufijo}"),
            "copiar": (CalendarioBarra, f"br-copia-{d.sufijo}"),
        }[caso]
        if caso == "cambiar-pieza":
            r = await limitado.patch(f"/calendario/piezas/{fila_id}", json={"estado": "publicado"})
        elif caso == "quitar-pieza":
            r = await d.http.delete(f"{API}/calendario/piezas/{fila_id}", headers=limitado.headers)
        elif caso == "quitar-aviso":
            r = await d.http.delete(f"{API}/calendario/avisos/{fila_id}", headers=limitado.headers)
        elif caso == "borrar-tarea":
            r = await d.http.delete(f"{API}/calendario/tareas/{fila_id}", headers=Cliente(d.http, lider_limitado).headers)
        else:
            r = await limitado.post(f"/calendario/barras/{d.ciber.id}/copiar", json={
                "id": fila_id, "desde": d.hoy.isoformat(), "nombre": f"Copia {d.sufijo}"})
        assert r.status_code == 404, (caso, r.status_code, r.text)
        async with d.Sesion() as s:
            fila = await s.get(modelo, fila_id)
            if caso == "copiar":
                assert fila is None
            else:
                assert fila is not None
                if caso == "cambiar-pieza":
                    assert fila.estado == "pendiente"
    correr(prueba)


def test_una_entrega_con_un_link_solo_no_pide_lugar_en_la_base(monkeypatch):
    """Con la base llena, una entrega con imágenes se frena (507); una con un
    link solo no ocupa lugar y pasa. Antes las dos recibían «La imagen no se
    guardó»."""
    from fastapi import HTTPException

    from app.api.routes import entregas as rutas_entregas

    async def sin_lugar(db, bytes_nuevos):
        raise HTTPException(status_code=507, detail="La imagen no se guardó: no hay lugar")

    monkeypatch.setattr(rutas_entregas, "exigir_lugar", sin_lugar)

    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lucia)
        a1 = Cliente(d.http, d.a1)
        archivos = [("imagenes", ("a.jpg", JPEG, "image/jpeg")), ("miniaturas", ("m.jpg", JPEG, "image/jpeg"))]
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-i-{d.sufijo}"}, files=archivos)
        assert r.status_code == 507
        assert (await _entregar_link(a1, tarea_id, f"ve-l-{d.sufijo}")).status_code == 201
    correr(prueba)


def test_el_buscador_encuentra_nombres_con_tildes_y_mayusculas():
    async def prueba(d):
        async with d.Sesion() as s:
            s.add(CalendarioBarra(
                id=f"br-nino-{d.sufijo}", mundo=MUNDO, seccion="comercial", banda="MEGA EVENTO", carril=0,
                nombre=f"DÍA DEL NIÑO {d.sufijo}", desde=d.hoy, hasta=d.hoy + timedelta(days=3),
                creado_por_id=d.promo.id,
            ))
            await s.commit()
        barra = await _barra(d, f"br-nino-{d.sufijo}")
        tarea_id, _ = await _pedir_banners(d, d.lucia, barra=barra)
        r = await Cliente(d.http, d.lucia).get("/calendario/entregas/buscar", params={
            "mundo": MUNDO, "q": f"dia del nino {d.sufijo}"})
        assert [t["tareaId"] for t in r.json()["enTablero"]] == [tarea_id], r.text
    correr(prueba)


async def _barra(d, barra_id):
    async with d.Sesion() as s:
        return await s.get(CalendarioBarra, barra_id)


def test_una_pieza_avisa_como_tarjeta_al_copiarla_y_al_reasignarla():
    """A quien hace una pieza de Tienda le llegaba, al copiar la acción, el
    aviso de la tarjeta y además el de «te asignó N tareas»: ahora uno solo.
    Y reasignarle una pieza le avisa como tarjeta (lleva al tablero)."""
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        pieza = f"ta-pz-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": pieza, "tipo": "banners", "opciones": ["Header"], "para": "tienda", "asignadoA": d.aprob2.id})
        assert r.status_code == 201, r.text
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/copiar", json={
            "id": f"br-cp-{d.sufijo}", "desde": (d.hoy + timedelta(days=20)).isoformat(), "nombre": f"Hot Sale {d.sufijo}"})
        assert r.status_code == 201, r.text
        copia = next(x for x in r.json()["barra"]["tareas"] if x.get("tipo") == "banners")
        avisos = await _avisos(d, d.aprob2, copia["id"])
        assert len(avisos) == 1 and avisos[0].origen_tipo == "calendario_entrega", [a.mensaje for a in avisos]

        r = await lider.patch(f"/calendario/tareas/{pieza}", json={"asignadoA": d.lucia.id})
        assert r.status_code == 200, r.text
        avisos = await _avisos(d, d.lucia, pieza)
        assert len(avisos) == 1 and avisos[0].origen_tipo == "calendario_entrega"
        assert "te pidió" in avisos[0].mensaje
    correr(prueba)


def test_quien_gestiona_las_tareas_sin_ver_el_calendario_elige_aprobadores():
    """«Configurar» del tablero pide la lista de personas: quien gestiona las
    tareas la recibe aunque su calendario sea «No lo ve». Quien no gestiona y
    no ve el calendario, no (se prueba arriba)."""
    async def prueba(d):
        gestor = await _persona(d, "Lider Sin Calendario", permisos=("calendario.view", "calendario.tareas"), alc="nada")
        r = await Cliente(d.http, gestor).get("/calendario/personas", params={"mundo": MUNDO})
        assert r.status_code == 200, r.text
        assert d.lucia.id in {p["id"] for p in r.json()}
        assert (await Cliente(d.http, d.sin_cal).get("/calendario/personas", params={"mundo": MUNDO})).status_code == 403
    correr(prueba)


# ---------------------------------------------------------------------------
# El flujo de las tareas de punta a punta (17/11/2026)
# ---------------------------------------------------------------------------
# Pedido de Ivan: la acción la arma quien lidera; el equipo de analistas crea
# las tareas y, debajo de cada una, pide sus materiales. Una pieza se revisa,
# se devuelve con un texto las veces que haga falta y, aunque ya esté
# aprobada, se puede volver para atrás: cada vuelta abre otra fase (Entrega 2,
# Entrega 3...), sin tope.

async def _detalle(cliente, tarea_id) -> dict:
    r = await cliente.get(f"/calendario/tareas/{tarea_id}/entregas")
    assert r.status_code == 200, r.text
    return r.json()


async def _decidir(cliente, version_id, decision, comentario=None):
    cuerpo = {"decision": decision}
    if comentario:
        cuerpo["comentario"] = comentario
    return await cliente.post(f"/calendario/versiones/{version_id}/decision", json=cuerpo)


def test_la_analista_crea_la_tarea_pide_su_material_y_lo_devuelve_hasta_aprobarlo():
    async def prueba(d):
        nath = await _persona(d, "Nath Analista", permisos=("calendario.view", "calendario.edit", "calendario.pedidos"))
        lucia, nathc = Cliente(d.http, d.lucia), Cliente(d.http, nath)

        # 1. Crear tarea: lo primero, sin tipo.
        tarea = f"ta-web-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": tarea, "titulo": "Web de Ciberlunes", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text

        # 2. Debajo, su material: banners que hace Nath.
        pieza = f"ta-ban-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": pieza, "parentId": tarea, "tipo": "banners", "opciones": ["Header"],
            "para": "tienda", "asignadoA": nath.id})
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, pieza)).parent_id == tarea
            assert (await s.get(CalendarioEntrega, pieza)).aprobadores == [d.lucia.id]
        assert len(await _avisos(d, nath, pieza)) == 1
        datos = (await lucia.get("/calendario/datos", params={"mundo": MUNDO})).json()
        tareas = next(b for b in datos["barras"] if b["id"] == d.ciber.id)["tareas"]
        assert next(t for t in tareas if t["id"] == pieza)["parentId"] == tarea

        # 3. Ronda 1: Nath entrega, Lucía la devuelve con un texto.
        assert (await _entregar_link(nathc, pieza, f"ve-1-{d.sufijo}")).status_code == 201
        det = await _detalle(lucia, pieza)
        assert det["puedo"]["decidir"] and not det["puedo"]["devolver"]
        assert not (await _detalle(nathc, pieza))["puedo"]["decidir"]
        r = await _decidir(lucia, f"ve-1-{d.sufijo}", "cambios")
        assert r.status_code == 422  # devolver pide decir qué cambiar
        r = await _decidir(lucia, f"ve-1-{d.sufijo}", "cambios", "El logo más grande")
        assert r.status_code == 200, r.text
        det = await _detalle(nathc, pieza)
        assert det["resumen"]["momento"] == "cambios" and det["puedo"]["entregar"]

        # 4. Ronda 2: la aprueba. Queda hecha, con una sola fase.
        assert (await _entregar_link(nathc, pieza, f"ve-2-{d.sufijo}")).status_code == 201
        assert (await _decidir(lucia, f"ve-2-{d.sufijo}", "aprobada")).status_code == 200
        assert await _estado(d, pieza) == "hecha"
        det = await _detalle(lucia, pieza)
        assert det["resumen"]["momento"] == "aprobada" and len(det["fases"]) == 1
        assert det["fases"][0]["versiones"][0]["decisiones"][0]["comentario"] == "El logo más grande"

        # 5. Ya aprobada, la puede volver para atrás quien la aprueba, con un texto.
        assert det["puedo"]["devolver"]
        assert not (await _detalle(nathc, pieza))["puedo"]["devolver"]
        assert not (await _detalle(Cliente(d.http, d.aprob2), pieza))["puedo"]["devolver"]
        r = await nathc.post(f"/calendario/tareas/{pieza}/devolver", json={"comentario": "Me olvidé algo"})
        assert r.status_code == 403
        r = await lucia.post(f"/calendario/tareas/{pieza}/devolver", json={"comentario": "   "})
        assert r.status_code == 422
        r = await lucia.post(f"/calendario/tareas/{pieza}/devolver", json={"comentario": "Cambió el precio: ahora es 2x1"})
        assert r.status_code == 200, r.text
        assert r.json()["fase"]["nombre"] == "Entrega 2" and r.json()["avisados"] == 1
        assert await _estado(d, pieza) == "en-proceso"
        det = await _detalle(nathc, pieza)
        assert det["resumen"]["momento"] == "produccion" and det["puedo"]["entregar"]
        assert det["fases"][1]["motivo"] == "Cambió el precio: ahora es 2x1"
        assert det["fases"][1]["abiertaPor"] == d.lucia.id
        assert det["personas"][str(d.lucia.id)]
        avisos = await _avisos(d, nath, pieza)
        assert avisos[-1].mensaje.startswith("Lucia Equipo devolvió")
        assert "Cambió el precio: ahora es 2x1." in avisos[-1].mensaje and "Entrega 2" in avisos[-1].mensaje
        assert (await _tarjeta(lucia, pieza))["columna"] == "en-proceso"

        # 6. Entrega 2: Nath entrega y Lucía la aprueba. Vuelve a quedar hecha.
        assert (await _entregar_link(nathc, pieza, f"ve-3-{d.sufijo}")).status_code == 201
        assert (await _decidir(lucia, f"ve-3-{d.sufijo}", "aprobada")).status_code == 200
        assert await _estado(d, pieza) == "hecha"
    correr(prueba)


def test_devolver_una_aprobada_no_tiene_tope_de_fases():
    """"No podés tener un límite en las fases de entrega... fase 1, fase 2,
    fase 3": cada devolución suma una fase, más allá de las 8 de antes, y la
    configuración se sigue pudiendo guardar con todas."""
    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        for n in range(1, 11):
            assert (await _entregar_link(a1, tarea_id, f"ve-n{n}-{d.sufijo}")).status_code == 201
            assert (await _decidir(lider, f"ve-n{n}-{d.sufijo}", "aprobada")).status_code == 200
            if n < 10:
                r = await lider.post(f"/calendario/tareas/{tarea_id}/devolver", json={"comentario": f"Vuelta {n}"})
                assert r.status_code == 200, r.text
                assert r.json()["fase"]["nombre"] == f"Entrega {n + 1}"
        det = await _detalle(lider, tarea_id)
        assert [f["nombre"] for f in det["fases"]] == ["Entrega"] + [f"Entrega {n}" for n in range(2, 11)]
        assert all(f["estado"] == "aprobada" for f in det["fases"])
        assert det["resumen"]["momento"] == "aprobada"
        r = await lider.put(f"/calendario/tareas/{tarea_id}/entregas", json={
            "tipoPieza": "banner", "aprobadores": det["aprobadores"],
            "fases": [{"id": f["id"], "nombre": f["nombre"]} for f in det["fases"]]})
        assert r.status_code == 200, r.text
    correr(prueba)


def test_devolver_solo_cuando_esta_aprobada_y_nunca_una_agencia():
    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        r = await lider.post(f"/calendario/tareas/{tarea_id}/devolver", json={"comentario": "x"})
        assert r.status_code == 409  # todavía no entregó nada
        assert (await _entregar_link(a1, tarea_id, f"ve-d1-{d.sufijo}")).status_code == 201
        r = await lider.post(f"/calendario/tareas/{tarea_id}/devolver", json={"comentario": "x"})
        assert r.status_code == 409  # en revisión: los cambios se piden al revisar
        assert (await _decidir(lider, f"ve-d1-{d.sufijo}", "aprobada")).status_code == 200
        r = await a1.post(f"/calendario/tareas/{tarea_id}/devolver", json={"comentario": "x"})
        assert r.status_code == 403
        assert not (await _detalle(a1, tarea_id))["puedo"]["devolver"]
        # Archivada después de terminar, se devuelve igual y sale del archivo.
        r = await lider.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": "finalizado", "a": "archivado"})
        assert r.status_code == 200, r.text
        r = await lider.post(f"/calendario/tareas/{tarea_id}/devolver", json={"comentario": "Faltó el legal"})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            e = await s.get(CalendarioEntrega, tarea_id)
            assert e.archivada_at is None and e.finalizada_at is None and e.momento == "produccion"
        # A toda la agencia le llega el aviso con el texto.
        assert "Faltó el legal" in (await _avisos(d, d.a2, tarea_id))[-1].mensaje
    correr(prueba)


def test_subtareas_asignaciones_y_estado_de_las_tareas_comunes():
    async def prueba(d):
        lider, lucia = Cliente(d.http, d.lider), Cliente(d.http, d.lucia)
        madre = f"ta-madre-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": madre, "titulo": "Mailing de Ciberlunes", "asignadoA": d.aprob2.id})
        assert r.status_code == 201, r.text
        assert len(await _avisos(d, d.aprob2, madre)) == 1
        # La subtarea común la arma quien lidera, con aviso a quien la hace.
        hija = f"ta-hija-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": hija, "parentId": madre, "titulo": "Textos", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, hija)).parent_id == madre
        assert len(await _avisos(d, d.lucia, hija)) == 1
        # Reasignar y borrar sigue siendo de quien lidera.
        r = await lucia.patch(f"/calendario/tareas/{madre}", json={"asignadoA": d.lider.id})
        assert r.status_code == 403
        r = await lider.patch(f"/calendario/tareas/{madre}", json={"asignadoA": d.lider.id})
        assert r.status_code == 200, r.text
        # Quien tiene una tarea asignada mueve su estado; otra persona, no.
        r = await lucia.patch(f"/calendario/tareas/{hija}", json={"estado": "en-proceso"})
        assert r.status_code == 200, r.text
        assert await _estado(d, hija) == "en-proceso"
        r = await Cliente(d.http, d.aprob2).patch(f"/calendario/tareas/{hija}", json={"estado": "hecha"})
        assert r.status_code == 403
        assert (await d.http.delete(f"{API}/calendario/tareas/{madre}", headers=lucia.headers)).status_code == 403
        assert (await d.http.delete(f"{API}/calendario/tareas/{madre}", headers=lider.headers)).status_code == 200
        async with d.Sesion() as s:
            assert await s.get(CalendarioTarea, hija) is None  # se fue con su madre
    correr(prueba)


def test_se_pide_un_material_de_redes_sociales_debajo_de_una_tarea():
    async def prueba(d):
        lucia = Cliente(d.http, d.lucia)
        catalogo = (await lucia.get("/calendario/tipos-de-tarea")).json()
        redes = next(t for t in catalogo if t["clave"] == "redes")
        assert [o["nombre"] for o in redes["opciones"]] == ["1:1", "4:5", "9:16", "16:9"]
        madre = f"ta-rrss-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={"id": madre, "titulo": "Lanzamiento en redes"})
        assert r.status_code == 201, r.text
        pieza = f"ta-rrss-p-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": pieza, "parentId": madre, "tipo": "redes", "opciones": ["9:16", "1:1"],
            "para": "tienda", "asignadoA": d.aprob2.id})
        assert r.status_code == 201, r.text
        assert r.json()["titulo"] == f"{d.ciber.nombre} - Redes sociales"
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, pieza)
            assert t.parent_id == madre and t.opciones == ["1:1", "9:16"]
            assert (await s.get(CalendarioEntrega, pieza)).tipo_pieza == "redes"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-rrss-x-{d.sufijo}", "parentId": madre, "tipo": "redes", "opciones": ["3:2"]})
        assert r.status_code == 422
    correr(prueba)


def test_se_pide_una_push_con_titulo_link_y_fecha_y_hora():
    async def prueba(d):
        lucia = Cliente(d.http, d.lucia)
        catalogo = (await lucia.get("/calendario/tipos-de-tarea")).json()
        push = next(t for t in catalogo if t["clave"] == "push")
        assert [(c["clave"], c["tipo"]) for c in push["campos"]] == [
            ("titulo", "texto"), ("link", "link"), ("envio", "fechaHora")]
        madre = f"ta-push-m-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={"id": madre, "titulo": "Avisos del Ciberlunes"})
        assert r.status_code == 201, r.text
        pieza = f"ta-push-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": pieza, "parentId": madre, "tipo": "push", "para": "tienda", "asignadoA": d.aprob2.id,
            "descripcion": "Hasta 50% en tecnología, solo hoy",
            "detalles": {"titulo": "Llegó el Ciberlunes", "link": "https://www.tiendainglesa.com.uy/ciber",
                         "envio": "2026-11-20T18:30"}})
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, pieza)
            assert t.detalles == {"titulo": "Llegó el Ciberlunes", "link": "https://www.tiendainglesa.com.uy/ciber",
                                  "envio": "2026-11-20T18:30"}
        det = (await lucia.get(f"/calendario/tareas/{pieza}/entregas")).json()
        assert "Fecha y hora de envío: 20/11/2026 18:30" in det["tarea"]["pedido"]
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-push-x-{d.sufijo}", "parentId": madre, "tipo": "push", "detalles": {"link": "tiendainglesa.com.uy"}})
        assert r.status_code == 422
    correr(prueba)


def test_los_tres_tableros_y_los_comentarios_de_la_tarjeta():
    """Publicis, Another Monday y Diseñadores (17/11/2026): la pieza va a uno
    de los tres aunque todavía no tenga cuentas; cuando se crean, la ven solo
    ellas; y en la tarjeta se conversa con comentarios, como en Trello."""
    async def prueba(d):
        lucia = Cliente(d.http, d.lucia)
        r = await lucia.get("/calendario/tableros", params={"mundo": MUNDO})
        assert r.status_code == 200, r.text
        assert [t["nombre"] for t in r.json()] == ["Publicis", "Another Monday", "Diseñadores"]

        # La tarea, con su responsable de Tienda, y su pieza para Publicis.
        madre = f"ta-tab-m-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": madre, "titulo": "Web de Ciberlunes", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text
        pieza = f"ta-tab-p-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": pieza, "parentId": madre, "tipo": "banners", "opciones": ["Header"],
            "para": "agencia", "agencia": "  publicis "})
        assert r.status_code == 201, r.text
        assert r.json()["para"] == "agencia" and r.json()["agencia"] == "Publicis"
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, pieza)
            assert t.asignado_a_id is None and t.parent_id == madre

        # Llega Publicis: sus cuentas ven la tarjeta; otra agencia, no.
        p1 = await _persona(d, "Pedro Publicis", externo=True, empresa="Publicis")
        p2 = await _persona(d, "Paula Publicis", externo=True, empresa="PUBLICIS")
        c1 = Cliente(d.http, p1)
        assert (await c1.get(f"/calendario/tareas/{pieza}/entregas")).status_code == 200
        assert await _tarjeta(c1, pieza) is not None
        assert (await Cliente(d.http, d.a1).get(f"/calendario/tareas/{pieza}/entregas")).status_code == 404
        r = await c1.get("/calendario/tableros", params={"mundo": MUNDO})
        assert r.json() == [{"nombre": "Publicis", "cuentas": 2}]

        # Comenta Publicis: le llega a quien la pidió y lleva la tarea, no a quien comentó.
        r = await c1.post(f"/calendario/tareas/{pieza}/comentarios", json={
            "id": f"co-1-{d.sufijo}", "texto": "  ¿El header lleva el precio? "})
        assert r.status_code == 201, r.text
        assert r.json()["comentario"]["texto"] == "¿El header lleva el precio?"
        assert any("comentó en" in n.mensaje for n in await _avisos(d, d.lucia, pieza))
        assert not any("comentó en" in n.mensaje for n in await _avisos(d, p1, pieza))
        # Responde Tienda: le llega a todo el tablero de Publicis.
        r = await lucia.post(f"/calendario/tareas/{pieza}/comentarios", json={
            "id": f"co-2-{d.sufijo}", "texto": "Sí: 2x1 en tecnología"})
        assert r.status_code == 201, r.text
        for cuenta in (p1, p2):
            assert any("Lucia Equipo comentó" in n.mensaje for n in await _avisos(d, cuenta, pieza))
        # Repetir el mismo id no duplica (un reintento).
        r = await lucia.post(f"/calendario/tareas/{pieza}/comentarios", json={
            "id": f"co-2-{d.sufijo}", "texto": "Sí: 2x1 en tecnología"})
        assert r.status_code == 201 and r.json()["avisados"] == 0

        # El detalle trae la conversación en orden, con quién escribió.
        det = (await c1.get(f"/calendario/tareas/{pieza}/entregas")).json()
        assert [c["texto"] for c in det["comentarios"]] == ["¿El header lleva el precio?", "Sí: 2x1 en tecnología"]
        assert det["comentarios"][0]["mio"] is True and det["comentarios"][1]["mio"] is False
        assert det["comentarios"][0]["autorNombre"] == "Pedro Publicis"

        # Otra agencia no comenta, y un comentario vacío no se guarda.
        r = await Cliente(d.http, d.a1).post(f"/calendario/tareas/{pieza}/comentarios", json={
            "id": f"co-3-{d.sufijo}", "texto": "hola"})
        assert r.status_code == 404
        r = await lucia.post(f"/calendario/tareas/{pieza}/comentarios", json={"id": f"co-4-{d.sufijo}", "texto": "   "})
        assert r.status_code == 422

        # Diseñadores y Another Monday también valen sin cuentas; otra agencia sin cuentas, no.
        for tablero in ("Diseñadores", "another monday"):
            r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
                "id": f"ta-tab-{tablero[:3]}-{d.sufijo}", "parentId": madre, "tipo": "push", "para": "agencia", "agencia": tablero})
            assert r.status_code == 201, r.text
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-tab-x-{d.sufijo}", "parentId": madre, "tipo": "push", "para": "agencia", "agencia": "Otra Agencia SA"})
        assert r.status_code == 422
    correr(prueba)
