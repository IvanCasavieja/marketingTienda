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
import io
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")

if URL:
    import httpx
    from sqlalchemy import func, select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.api.routes import entregas as rutas_de_entregas
    from app.core import alcance
    from app.core.database import get_db
    from app.core.rate_limit import limiter
    from app.core.security import create_access_token, hash_password
    from app.main import app
    from app.models.calendario import (
        CalendarioAviso, CalendarioBarra, CalendarioPieza, CalendarioPlantilla, CalendarioTarea,
    )
    from app.models.entregas import (
        CalendarioDecision, CalendarioEntrega, CalendarioFase, CalendarioVersionImagen, CalendarioVersionZip,
    )
    from app.models.notificacion import Notificacion
    from app.models.revision_ia import CalendarioRevisionIA
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

    async def delete(self, ruta, **kw):
        return await self.http.delete(API + ruta, headers=self.headers, **kw)


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
    # El ZIP de una ronda se baja de a partes con su propia sesión
    # (_partes_del_zip, 19/11/2026): que lea de esta misma base de prueba.
    sesiones_antes = rutas_de_entregas.AsyncSessionLocal
    rutas_de_entregas.AsyncSessionLocal = Sesion
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
        rutas_de_entregas.AsyncSessionLocal = sesiones_antes
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
            assert (await c.get(f"/calendario/ubicar/{d.ahora.id}")).status_code == 404
            # Su agenda personal tampoco: es parte del calendario.
            assert (await c.get("/calendario/mi-agenda")).status_code == 403
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
        # La agencia no la finaliza. (Lucía sí podría llevarla a mano: el
        # tablero es libre para el equipo desde el 18/11/2026.)
        r = await a1.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": "esperando", "a": "finalizado"})
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
        # Ella no la aprueba: decide otro.
        assert (await _tarjeta(lucia, tarea_id))["puedo"]["decidir"] is False
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

        # «Sí, pasarlas» (desde el 21/11/2026 el panel pregunta antes).
        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={
            "es_externo": True, "empresa": f"Estudio del Sur {d.sufijo}", "pasar_tarjetas": True})
        assert r.status_code == 200, r.text
        # La respuesta dice cuántas pasaron al nombre nuevo.
        assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (1, 0)
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
        assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (0, 0)
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
            # Don Tino, con la misma regla (19/11/2026: "Don Tino debe amoldarse
            # a cada usuario"): «¿qué tengo pendiente?» la nombra, sin link a una
            # ficha que no abre; y la ficha sigue cerrada.
            async with d.Sesion() as s:
                quien = await s.get(User, usuario.id)
                datos = json.loads(await cc.ejecutar("calendario_tareas", {"responsable": "yo"}, quien, s))
                assert [t["titulo"] for t in datos["tareas"]] == ["Preparar el brief"], usuario.full_name
                accion = datos["tareas"][0]["accion"]
                assert accion["nombre"] == barra.nombre and accion["fuera_de_lo_que_ve"] is True
                assert "link" not in accion and "id" not in accion
                cerrada = json.loads(await cc.ejecutar("calendario_accion", {"accion_id": barra.id}, quien, s))
                assert "error" in cerrada
        # Una hecha de una acción fuera de su alcance ya no se le muestra.
        r = await Cliente(d.http, d.limitado).patch(f"/calendario/tareas/{casos[0][2]}", json={"estado": "hecha"})
        assert r.status_code == 200, r.text
        mias = (await Cliente(d.http, d.limitado).get("/calendario/mis-tareas")).json()
        assert all(x["id"] != casos[0][2] for x in mias)
        async with d.Sesion() as s:
            quien = await s.get(User, d.limitado.id)
            texto = await cc.ejecutar("calendario_tareas", {"responsable": "yo", "estados": ["hecha"]}, quien, s)
            assert "Preparar el brief" not in texto
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

        # La agencia no la archiva; el equipo sí, desde Ingresado.
        assert (await mover(a1, "ingresado", "archivado")).status_code == 403
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
        # Sale del archivo a su columna, y la tarea se reabre. (El equipo la
        # podría llevar a cualquiera: el tablero es libre desde el 18/11/2026.)
        assert "ingresado" in (await _tarjeta(lucia, tarea_id))["puedo"]["mover"]
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
        # «Sí, pasarlas» (desde el 21/11/2026 el panel pregunta antes).
        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={
            "es_externo": True, "empresa": f"Estudio del Sur {d.sufijo}", "pasar_tarjetas": True})
        assert r.status_code == 200, r.text
        assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (0, 1)
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


def test_cambiar_de_tablero_a_la_unica_cuenta_no_se_lleva_las_tarjetas():
    """Revisión del 19/11/2026: Fer, la única cuenta de Diseñadores (una
    agencia externa, como Publicis), pasa a Publicis porque se eligió mal, y
    después vuelve. Eso se tomaba como «le corrigieron el nombre a la
    agencia»: se llevaba a Publicis todas las tarjetas y las plantillas de
    Diseñadores, y al volver se traía las de Publicis. Un tablero no se
    renombra: cada tarjeta y cada plantilla se queda en el suyo, aunque se
    pida pasarlas. Corregir el nombre de una agencia que no es un tablero
    («Publisis» -> «Publicis») las sigue pasando si se pide (desde el
    21/11/2026 el panel pregunta antes), y la respuesta dice cuántas."""
    async def prueba(d):
        lider, promo = Cliente(d.http, d.lider), Cliente(d.http, d.promo)
        fer = await _persona(d, "Fer Disenia", externo=True, empresa="Diseñadores")
        de_dis, de_pub = f"ta-vd-{d.sufijo}", f"ta-vp-{d.sufijo}"
        for tarea_id, agencia in ((de_dis, "Diseñadores"), (de_pub, "Publicis")):
            r = await lider.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
                "id": tarea_id, "tipo": "push", "para": "agencia", "agencia": agencia})
            assert r.status_code == 201, r.text
        plantilla = f"pl-vuelta-{d.sufijo}"
        r = await lider.put(f"/calendario/plantillas/{plantilla}", json={
            "mundo": MUNDO, "nombre": "Mega", "tareas": [
                {"id": "t1", "titulo": "Push", "tipo": "push", "para": "agencia", "agencia": "Diseñadores",
                 "ancla": "inicio", "dias": -3},
                {"id": "t2", "titulo": "Banners", "tipo": "banners", "opciones": ["Header"], "para": "agencia",
                 "agencia": "Publicis", "ancla": "inicio", "dias": -2},
            ]})
        assert r.status_code == 200, r.text

        async def cada_una_en_su_tablero():
            async with d.Sesion() as s:
                assert (await s.get(CalendarioTarea, de_dis)).agencia == "Diseñadores"
                assert (await s.get(CalendarioTarea, de_pub)).agencia == "Publicis"
                tareas = (await s.get(CalendarioPlantilla, plantilla)).tareas
            assert [t["agencia"] for t in tareas] == ["Diseñadores", "Publicis"]

        # Ida y vuelta, aunque se pida pasarlas.
        for empresa in ("Publicis", "Diseñadores"):
            r = await promo.patch(f"/admin/users/{fer.id}/externo", json={
                "es_externo": True, "empresa": empresa, "pasar_tarjetas": True})
            assert r.status_code == 200, r.text
            assert r.json()["empresa"] == empresa
            assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (0, 0)
            await cada_una_en_su_tablero()
        # De vuelta en Diseñadores, Fer ve su tarjeta y no la de Publicis.
        c = Cliente(d.http, fer)
        assert await _tarjeta(c, de_dis) is not None
        assert await _tarjeta(c, de_pub) is None
        # Con el tablero escrito de otra forma («DISENADORES», guardado a mano
        # antes del 19/11) es el mismo tablero: tampoco se lleva nada.
        async with d.Sesion() as s:
            (await s.get(User, fer.id)).empresa = "DISENADORES"
            await s.commit()
        r = await promo.patch(f"/admin/users/{fer.id}/externo", json={
            "es_externo": True, "empresa": "Another Monday", "pasar_tarjetas": True})
        assert r.status_code == 200, r.text
        assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (0, 0)
        await cada_una_en_su_tablero()

        # «Publisis» no es un tablero: es Publicis mal escrito. Su única
        # cuenta pasa a Publicis y, si se pide («Sí, pasarlas»), se lleva su
        # tarjeta y su plantilla.
        publisis = await _persona(d, "Pato Publisis", externo=True, empresa=f"Publisis {d.sufijo}")
        mal_escrita = f"ta-vm-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
            "id": mal_escrita, "tipo": "push", "para": "agencia", "agencia": f"Publisis {d.sufijo}"})
        assert r.status_code == 201, r.text
        r = await lider.put(f"/calendario/plantillas/{plantilla}-m", json={
            "mundo": MUNDO, "nombre": "Mal escrita", "tareas": [
                {"id": "t1", "titulo": "Push", "tipo": "push", "para": "agencia", "agencia": f"Publisis {d.sufijo}",
                 "ancla": "inicio", "dias": -3}]})
        assert r.status_code == 200, r.text
        r = await promo.patch(f"/admin/users/{publisis.id}/externo", json={
            "es_externo": True, "empresa": "Publicis", "pasar_tarjetas": True})
        assert r.status_code == 200, r.text
        assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (1, 1)
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, mal_escrita)).agencia == "Publicis"
            assert (await s.get(CalendarioPlantilla, f"{plantilla}-m")).tareas[0]["agencia"] == "Publicis"
        await cada_una_en_su_tablero()
    correr(prueba)


def test_cambiar_de_agencia_a_la_unica_cuenta_no_se_lleva_nada_si_no_se_pide():
    """Revisión del 19/11/2026: Bruno es la única cuenta de «Estudio Sur» (una
    agencia que no es un tablero) y se lo pasa a Publicis porque se eligió mal
    en la lista. Eso se tomaba como «le corrigieron el nombre a la agencia»:
    se llevaba a Publicis las tarjetas y las plantillas de Estudio Sur sin
    preguntar, y el panel avisaba después. Desde el 21/11/2026 pasan solo si
    el pedido lo dice (`pasar_tarjetas`); el panel pregunta antes, con lo que
    contesta GET /admin/users/{id}/pase-de-agencia. Los tres tableros siguen
    sin pasar nada nunca."""
    async def prueba(d):
        lider, promo = Cliente(d.http, d.lider), Cliente(d.http, d.promo)
        sur = f"Estudio Sur {d.sufijo}"
        tarea_id, _ = await _pedir_banners(d, d.lider, agencia=sur)
        plantilla = f"pl-pase-{d.sufijo}"
        r = await lider.put(f"/calendario/plantillas/{plantilla}", json={
            "mundo": MUNDO, "nombre": "Mega", "tareas": [
                {"id": "t1", "titulo": "Push", "tipo": "push", "para": "agencia", "agencia": sur,
                 "ancla": "inicio", "dias": -3}]})
        assert r.status_code == 200, r.text

        async def de_estudio_sur():
            async with d.Sesion() as s:
                return ((await s.get(CalendarioTarea, tarea_id)).agencia,
                        (await s.get(CalendarioPlantilla, plantilla)).tareas[0]["agencia"])

        # Antes de guardar, el panel pregunta qué se llevaría: «Bruno es la
        # única cuenta de «Estudio Sur», que tiene 1 tarjeta y 1 plantilla».
        r = await promo.get(f"/admin/users/{d.b1.id}/pase-de-agencia", params={"empresa": "publicis"})
        assert r.status_code == 200, r.text
        assert r.json() == {"de": sur, "a": "Publicis", "tarjetas": 1, "plantillas": 1}

        # «No, dejarlas en Estudio Sur»: sin la marca no pasa nada.
        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={"es_externo": True, "empresa": "Publicis"})
        assert r.status_code == 200, r.text
        assert r.json()["empresa"] == "Publicis"
        assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (0, 0)
        assert await de_estudio_sur() == (sur, sur)
        assert await _tarjeta(Cliente(d.http, d.b1), tarea_id) is None
        # Fue un error: vuelve a Estudio Sur y lo de ahí sigue siendo suyo. A
        # Publicis (un tablero) no se le lleva nada aunque se pida.
        r = await promo.get(f"/admin/users/{d.b1.id}/pase-de-agencia", params={"empresa": sur})
        assert (r.json()["tarjetas"], r.json()["plantillas"]) == (0, 0)
        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={
            "es_externo": True, "empresa": sur, "pasar_tarjetas": True})
        assert r.status_code == 200, r.text
        assert (r.json()["empresa"], r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (sur, 0, 0)
        assert await _tarjeta(Cliente(d.http, d.b1), tarea_id) is not None

        # Cómo se escribe (sin tildes ni mayúsculas) no es otra agencia: nada que preguntar.
        r = await promo.get(f"/admin/users/{d.b1.id}/pase-de-agencia", params={"empresa": f"estudio súr {d.sufijo}"})
        assert (r.json()["tarjetas"], r.json()["plantillas"]) == (0, 0)
        # Pampa tiene dos cuentas: lo suyo se queda con la otra, nada que preguntar.
        r = await promo.get(f"/admin/users/{d.a1.id}/pase-de-agencia", params={"empresa": "Publicis"})
        assert r.status_code == 200, r.text
        assert (r.json()["tarjetas"], r.json()["plantillas"]) == (0, 0)

        # «Sí, pasarlas»: con la marca, pasan, y la respuesta dice cuántas.
        nuevo = f"Estudio del Sur {d.sufijo}"
        r = await promo.get(f"/admin/users/{d.b1.id}/pase-de-agencia", params={"empresa": nuevo})
        assert r.json() == {"de": sur, "a": nuevo, "tarjetas": 1, "plantillas": 1}
        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={
            "es_externo": True, "empresa": nuevo, "pasar_tarjetas": True})
        assert r.status_code == 200, r.text
        assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (1, 1)
        assert await de_estudio_sur() == (nuevo, nuevo)
        assert await _tarjeta(Cliente(d.http, d.b1), tarea_id) is not None

        # La única cuenta de un tablero (Diseñadores, una agencia externa):
        # nada que preguntar, y aunque se pida no se lleva nada.
        fer = await _persona(d, "Fer Disenia", externo=True, empresa="Diseñadores")
        de_dis, _ = await _pedir_banners(d, d.lider, agencia="Diseñadores")
        r = await promo.get(f"/admin/users/{fer.id}/pase-de-agencia", params={"empresa": "Another Monday"})
        assert (r.json()["tarjetas"], r.json()["plantillas"]) == (0, 0)
        r = await promo.patch(f"/admin/users/{fer.id}/externo", json={
            "es_externo": True, "empresa": "Another Monday", "pasar_tarjetas": True})
        assert r.status_code == 200, r.text
        assert (r.json()["tarjetas_pasadas"], r.json()["plantillas_pasadas"]) == (0, 0)
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, de_dis)).agencia == "Diseñadores"

        # Solo quien administra usuarios; y una cuenta que no existe, 404.
        r = await Cliente(d.http, d.lucia).get(f"/admin/users/{d.b1.id}/pase-de-agencia", params={"empresa": "Publicis"})
        assert r.status_code == 403
        assert (await promo.get("/admin/users/999999999/pase-de-agencia", params={"empresa": "Publicis"})).status_code == 404
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


def test_aprobado_con_cambios_ya_no_existe_y_las_decisiones_viejas_siguen_valiendo():
    """Ivan (19/11/2026) sacó «Aprobado con cambios» ("me resulta raro ese
    botón. No creo que sume nada"). Una pantalla vieja que lo mande recibe un
    422 con el porqué; y una decisión de esta semana guardada así se sigue
    leyendo como aprobada: la cadena sigue con el siguiente, la versión se
    aprueba cuando aprueba el último y el retrabajo la cuenta."""
    async def prueba(d):
        lider, lucia, aprob2 = Cliente(d.http, d.lider), Cliente(d.http, d.lucia), Cliente(d.http, d.aprob2)
        a1 = Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        r = await lider.put(f"/calendario/tareas/{tarea_id}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.lucia.id, d.aprob2.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text
        version = f"ve-v-{d.sufijo}"
        assert (await _entregar_link(a1, tarea_id, version)).status_code == 201

        # La decisión vieja ya no se acepta, y el mensaje dice qué elegir.
        r = await _decidir(lucia, version, "aprobada-con-cambios", "Una tilde")
        assert r.status_code == 422, r.text
        assert "ya no existe" in r.json()["detail"] and "Pedir cambios" in r.json()["detail"]
        assert (await _decidir(lucia, version, "rechazada")).status_code == 422
        det = await _detalle(lucia, tarea_id)
        assert det["puedo"]["decidir"] and "tildarMarcas" not in det["puedo"]
        # La ruta para tildar ajustes sueltos se fue con la decisión.
        assert (await lider.patch("/calendario/marcas/mk-inventada", json={"corregida": True})).status_code == 404

        # Una decisión de Lucía guardada por el código de antes del 19/11,
        # tal como la dejaba: con el turno ya pasado al segundo de la cadena.
        async with d.Sesion() as s:
            s.add(CalendarioDecision(version_id=version, aprobador_id=d.lucia.id, decidido_por_id=d.lucia.id,
                                     orden=0, decision="aprobada-con-cambios", comentario="Una tilde"))
            (await s.get(CalendarioEntrega, tarea_id)).aprobador_de_turno_id = d.aprob2.id
            await s.commit()
        det = await _detalle(aprob2, tarea_id)
        assert det["puedo"]["decidir"] and det["resumen"]["aprobadorDeTurno"] == d.aprob2.id
        assert det["resumen"]["momento"] == "revision"
        # Se sigue mostrando tal cual se guardó.
        assert det["fases"][0]["versiones"][0]["decisiones"][0]["decision"] == "aprobada-con-cambios"
        # Lucía ya decidió: no le toca otra vez.
        assert (await _decidir(lucia, version, "aprobada")).status_code == 403
        # Aprueba el último: la versión y la fase quedan aprobadas, la tarea hecha.
        assert (await _decidir(aprob2, version, "aprobada")).status_code == 200
        assert await _estado(d, tarea_id) == "hecha"
        det = await _detalle(lider, tarea_id)
        assert det["resumen"]["momento"] == "aprobada"
        assert det["fases"][0]["versiones"][0]["estado"] == "aprobada"
        assert (await _tarjeta(lider, tarea_id))["columna"] == "finalizado"
        aviso = (await _avisos(d, d.a1, tarea_id))[-1].mensaje
        assert "aprobó la ronda 1" in aviso and "con cambios" not in aviso and "justes" not in aviso
        # El retrabajo la cuenta: una fase aprobada en la ronda 1.
        r = await lider.get("/calendario/entregas/metricas", params={"mundo": MUNDO})
        assert r.status_code == 200, r.text
        assert r.json()["fases"] >= 1 and r.json()["rondasPromedio"] >= 1
    correr(prueba)


def test_el_analisis_de_entregas_dice_cuanto_tarda_cada_agencia_y_cuantas_se_pasan_de_fecha():
    """Ivan (20/11/2026): «Retrabajo» pasa a ser «Análisis de entregas» ("el
    retrabajo sí sirve, pero sería más un análisis") y suma "cuánto tarda cada
    agencia y cuántas piezas se pasan de fecha". El equipo ve todas las
    agencias; una agencia, solo lo suyo. Las rondas siguen viajando igual."""
    async def prueba(d):
        lider, lucia, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.lucia), Cliente(d.http, d.a1)
        pampa, sur = f"agencia:agencia pampa {d.sufijo}", f"agencia:estudio sur {d.sufijo}"
        # 1. Pampa la entrega a los 3 días de pedida, a tiempo, y se aprueba.
        a_tiempo, _ = await _pedir_banners(d, d.lider)
        r = await lider.put(f"/calendario/tareas/{a_tiempo}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.lucia.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text
        # 2. A Pampa se le pasó otra: vencía ayer y todavía no entregó nada.
        vencida, _ = await _pedir_banners(d, d.lider)
        # 3. Estudio Sur entrega hoy una que vencía hace 3 días (pedida hace 5).
        tarde, _ = await _pedir_banners(d, d.lider, agencia=f"Estudio Sur {d.sufijo}")
        async with d.Sesion() as s:
            for tarea_id, dias in ((a_tiempo, 3), (tarde, 5)):
                await s.execute(update(CalendarioEntrega).where(CalendarioEntrega.tarea_id == tarea_id)
                                .values(created_at=CalendarioEntrega.created_at - timedelta(days=dias)))
            for tarea_id, dias in ((vencida, 1), (tarde, 3)):
                await s.execute(update(CalendarioTarea).where(CalendarioTarea.id == tarea_id)
                                .values(vence=d.hoy - timedelta(days=dias), ancla=None, ancla_dias=None))
            await s.commit()
        version = f"ve-at-{d.sufijo}"
        assert (await _entregar_link(a1, a_tiempo, version)).status_code == 201
        assert (await _decidir(lucia, version, "aprobada")).status_code == 200
        assert (await _entregar_link(Cliente(d.http, d.b1), tarde, f"ve-ta-{d.sufijo}")).status_code == 201

        # El equipo: cada agencia con lo suyo.
        r = await lider.get("/calendario/entregas/metricas", params={"mundo": MUNDO})
        assert r.status_code == 200, r.text
        m = r.json()
        grupos = {g["clave"]: g for g in m["porAgencia"]}
        assert grupos[pampa]["nombre"] == f"Agencia Pampa {d.sufijo}"
        assert grupos[pampa]["entregadas"] == 1 and grupos[pampa]["diasHastaEntregar"] == 3.0
        assert grupos[pampa]["aprobadas"] == 1 and grupos[pampa]["diasHastaAprobar"] == 3.0
        assert grupos[pampa]["aTiempo"] == 100 and grupos[pampa]["entregaronTarde"] == 0
        assert grupos[pampa]["vencidas"] == 1 and grupos[pampa]["sePasaron"] == 1
        assert grupos[sur]["diasHastaEntregar"] == 5.0 and grupos[sur]["aTiempo"] == 0
        assert grupos[sur]["entregaronTarde"] == 1 and grupos[sur]["sePasaron"] == 1
        assert m["tiempos"]["entregadas"] >= 2 and m["tiempos"]["sePasaron"] >= 2
        # Las rondas siguen viajando como antes.
        assert m["fases"] >= 1 and "porResponsable" in m and "porTipo" in m

        # La agencia: solo lo suyo.
        r = await a1.get("/calendario/entregas/metricas", params={"mundo": MUNDO})
        assert r.status_code == 200, r.text
        m = r.json()
        assert [g["clave"] for g in m["porAgencia"]] == [pampa]
        assert m["tiempos"]["entregadas"] == 1 and m["tiempos"]["vencidas"] == 1 and m["tiempos"]["sePasaron"] == 1
        assert "Estudio Sur" not in json.dumps(m)
    correr(prueba)


def _zip_de_prueba(archivos: dict) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nombre, datos in archivos.items():
            zf.writestr(nombre, datos)
    return buf.getvalue()


def test_la_entrega_acepta_un_zip_que_la_ia_revisa_en_segundo_plano(monkeypatch):
    """Ivan (19/11/2026): "¿Qué pasaría si en vez de una imagen me hubieran
    pasado una carpeta o un link? (…) vos directamente como plataforma ya
    descargués todas las cosas". El ZIP viaja en el campo `zip` del
    multipart y se le pasa en memoria a la revisión de la IA, que corre
    después de contestar (además se guarda tal cual: ver las pruebas de abajo).
    Acá la revisión es un espía: lo de abrir el ZIP está en test_materiales.py."""
    from app.services import revision_ia

    llamadas = []

    async def espia(version_id, **kw):
        llamadas.append((version_id, kw))

    monkeypatch.setattr(revision_ia, "activa", lambda: True)
    monkeypatch.setattr(revision_ia, "revisar_version", espia)

    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        det = await _detalle(lider, tarea_id)
        assert det["limites"]["bytesZip"] == 40 * 1024 * 1024
        zip_bueno = _zip_de_prueba({"Cenefas/cenefa 1.jpg": JPEG, "folleto.pdf": b"%PDF-1.4 x", "notas.txt": b"hola"})
        imagen = [("imagenes", ("a.jpg", JPEG, "image/jpeg")), ("miniaturas", ("m.jpg", JPEG, "image/jpeg"))]

        # Un ZIP solo alcanza si de adentro sale al menos una imagen para que
        # quien aprueba vea la pieza. Acá nada se puede abrir (la «cenefa» y el
        # «folleto» son de mentira): se rechaza, diciendo por qué.
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-z0-{d.sufijo}"},
                          files=[("zip", ("piezas.zip", zip_bueno, "application/zip"))])
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == (
            "Del ZIP no salió ninguna imagen para mostrar («Cenefas/cenefa 1.jpg»: no se pudo leer la imagen; "
            "«folleto.pdf»: no se pudo leer el PDF (¿está dañado?)): subí una imagen o pegá el link al original, "
            "así quien aprueba ve la pieza"
        )
        # Un ZIP que no es un ZIP, o sin nada para revisar adentro.
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-z0-{d.sufijo}"},
                          files=imagen + [("zip", ("piezas.zip", b"esto no es un zip", "application/zip"))])
        assert r.status_code == 422 and "no es un ZIP" in r.json()["detail"], r.text
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-z0-{d.sufijo}"},
                          files=imagen + [("zip", ("fuentes.zip", _zip_de_prueba({"a.ttf": b"x"}), "application/zip"))])
        assert r.status_code == 422 and "no trae nada para revisar" in r.json()["detail"], r.text
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-z0-{d.sufijo}"},
                          files=imagen + [("zip", ("malo.zip", _zip_de_prueba({"../x.jpg": JPEG}), "application/zip"))])
        assert r.status_code == 422 and "rutas que no van" in r.json()["detail"], r.text
        assert llamadas == []  # nada de eso se entregó

        # Con una imagen y el ZIP: queda la versión, y la IA recibe el ZIP.
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-z1-{d.sufijo}"},
                          files=imagen + [("zip", ("piezas.zip", zip_bueno, "application/zip"))])
        assert r.status_code == 201, r.text
        assert r.json()["zip"] == {"nombre": "piezas.zip", "tamano": len(zip_bueno), "guardado": True, "sumadas": 0,
                                   "archivos": ["Cenefas/cenefa 1.jpg", "folleto.pdf"], "ignorados": ["notas.txt"]}
        assert llamadas == [(f"ve-z1-{d.sufijo}", {"zip_datos": zip_bueno, "zip_nombre": "piezas.zip",
                                                    "zip_saltar": frozenset(), "zip_paginas": {}})]
        det = await _detalle(lider, tarea_id)
        assert det["resumen"]["momento"] == "revision" and len(det["fases"][0]["versiones"][0]["imagenes"]) == 1
        assert (await _decidir(lider, f"ve-z1-{d.sufijo}", "cambios", "Volvé a mandarla")).status_code == 200

        # Un link solo también se manda a revisar (antes no: la IA lo baja ella).
        assert (await _entregar_link(a1, tarea_id, f"ve-z2-{d.sufijo}")).status_code == 201
        assert llamadas[-1] == (f"ve-z2-{d.sufijo}", {"zip_datos": None, "zip_nombre": None, "zip_saltar": frozenset(),
                                                      "zip_paginas": {}})
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": f"ve-z2-{d.sufijo}"},
                          files=imagen)
        assert r.status_code == 201 and r.json()["yaExistia"] and r.json().get("zip") is None

        # Lo que encontró la IA, con el archivo de cada observación y lo que
        # no se pudo abrir, lo ve quien aprueba (una revisión guardada).
        async with d.Sesion() as s:
            s.add(CalendarioRevisionIA(
                version_id=f"ve-z2-{d.sufijo}", estado="lista", modelo="simulado",
                observaciones=[{"id": "ob-1", "tipo": "legal", "texto": "Faltan los legales", "gravedad": "importante",
                                "imagenId": None, "x": 0.5, "y": 0.9, "archivo": "Cenefas/cenefa 1.jpg", "pagina": None,
                                "origen": "zip", "estado": "nueva", "marcaId": None, "numero": None, "por": None, "fecha": None}],
                materiales={"revisados": [{"nombre": "Cenefas/cenefa 1.jpg", "origen": "zip", "paginas": None}],
                            "noSePudoAbrir": ["No se pudo abrir el link (drive.example.com/ronda): el link devolvió una página web"],
                            "ignorados": ["notas.txt"]},
            ))
            await s.commit()
        r = await lider.get(f"/calendario/versiones/ve-z2-{d.sufijo}/revision-ia")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["estado"] == "lista" and out["observaciones"][0]["archivo"] == "Cenefas/cenefa 1.jpg"
        assert out["observaciones"][0]["origen"] == "zip" and out["observaciones"][0]["imagenId"] is None
        assert out["revisados"] == [{"nombre": "Cenefas/cenefa 1.jpg", "origen": "zip", "paginas": None}]
        assert out["noSePudoAbrir"][0].startswith("No se pudo abrir el link") and out["ignorados"] == ["notas.txt"]
        # Una revisión sin lo de la ronda anterior (la de antes volvió sin
        # marcas, o es de antes del 19/11/2026): la lista va vacía.
        assert out["cambiosPedidos"] == []
        # La agencia (quien entrega) sigue sin ver nada de esto.
        assert (await a1.get(f"/calendario/versiones/ve-z2-{d.sufijo}/revision-ia")).status_code == 403

        # Las imágenes que el navegador ya sacó del ZIP y subió como imágenes
        # de la ronda (`zipYaSubidas`: su lugar en el índice) la IA no las
        # mira dos veces.
        assert (await _decidir(lider, f"ve-z2-{d.sufijo}", "cambios", "Otra vuelta")).status_code == 200
        for malo in ("no es una lista", '["0"]', "[-1]", "{}"):
            r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones",
                              data={"versionId": f"ve-z3-{d.sufijo}", "zipYaSubidas": malo},
                              files=imagen + [("zip", ("piezas.zip", zip_bueno, "application/zip"))])
            assert r.status_code == 422 and "sacadas del ZIP" in r.json()["detail"], (malo, r.text)
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones",
                          data={"versionId": f"ve-z3-{d.sufijo}", "zipYaSubidas": "[0]"},
                          files=imagen + [("zip", ("piezas.zip", zip_bueno, "application/zip"))])
        assert r.status_code == 201, r.text
        assert r.json()["zip"]["archivos"] == ["folleto.pdf"]
        assert llamadas[-1] == (f"ve-z3-{d.sufijo}", {"zip_datos": zip_bueno, "zip_nombre": "piezas.zip",
                                                    "zip_saltar": frozenset({0}), "zip_paginas": {}})
    correr(prueba)


# ---------------------------------------------------------------------------
# El ZIP original de la ronda y las páginas de los PDF (19/11/2026)
# ---------------------------------------------------------------------------

def _jpeg_de_verdad(ancho=400, alto=300, color="white") -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), color).save(buf, "JPEG", quality=75)
    return buf.getvalue()


def _pdf_de_prueba(paginas: int) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for i in range(paginas):
        doc.new_page().insert_text((72, 72), f"Folleto, página {i + 1}")
    datos = doc.tobytes()
    doc.close()
    return datos


def _espiar_la_ia(monkeypatch) -> list:
    from app.services import revision_ia

    llamadas = []

    async def espia(version_id, **kw):
        llamadas.append((version_id, kw))

    monkeypatch.setattr(revision_ia, "activa", lambda: True)
    monkeypatch.setattr(revision_ia, "revisar_version", espia)
    return llamadas


async def _entregar(cliente, tarea_id, version_id, *, imagenes=0, zip_=None, ya_subidas=None, link=None,
                    color="white"):
    data = {"versionId": version_id}
    if ya_subidas is not None:
        data["zipYaSubidas"] = ya_subidas
    if link:
        data["link"] = link
    files = []
    for i in range(imagenes):
        files += [("imagenes", (f"i{i}.jpg", _jpeg_de_verdad(color=color), "image/jpeg")),
                  ("miniaturas", (f"m{i}.jpg", _jpeg_de_verdad(64, 48, color), "image/jpeg"))]
    if zip_ is not None:
        files.append(("zip", (zip_[0], zip_[1], "application/zip")))
    return await cliente.post(f"/calendario/tareas/{tarea_id}/versiones", data=data, files=files or None)


def test_el_zip_se_guarda_tal_cual_y_lo_bajan_el_equipo_y_su_agencia(monkeypatch, caplog):
    """Ivan (19/11/2026): "no es más fácil guardar el zip en vez de guardar las
    imágenes? (…) cuando lo subís deberías de subir la carpeta comprimida, no
    los archivos sueltos". El ZIP queda guardado como el original de la ronda
    y se baja con las mismas reglas que las imágenes de esa versión: el
    equipo y la agencia de la tarjeta sí; otra agencia, o alguien a quien la
    acción le queda fuera de su alcance, no (el mismo 404 que lo que no existe).

    Se baja de a partes de 1 MB (revisión del 19/11/2026: entero eran unos 80
    MB de memoria por un ZIP de 40): este mide justo 3 partes, y llega igual."""
    _espiar_la_ia(monkeypatch)

    async def prueba(d):
        lider, a1, a2, b1 = (Cliente(d.http, u) for u in (d.lider, d.a1, d.a2, d.b1))
        tarea_id, _ = await _pedir_banners(d, d.lider)
        # Sin comprimir, lo que el ZIP suma alrededor de los archivos no
        # cambia con lo que pesan: se ajusta la fuente para que mida 3 MB justos.
        header = _jpeg_de_verdad()
        alrededor = len(_zip_de_prueba({"Banners/header.jpg": header, "fuentes/Gotham.otf": b""}))
        zip_ = _zip_de_prueba({"Banners/header.jpg": header,
                               "fuentes/Gotham.otf": os.urandom(3 * 1024 * 1024 - alrededor)})
        assert len(zip_) == 3 * rutas_de_entregas._PARTE_DEL_ZIP
        version = f"ve-zo-{d.sufijo}"
        r = await _entregar(a1, tarea_id, version, imagenes=1, zip_=("piezas niño.zip", zip_), ya_subidas="[0]")
        assert r.status_code == 201, r.text
        assert r.json()["zip"]["guardado"] is True and r.json()["zip"]["sumadas"] == 0

        # Queda en su lugar, tal cual, con su nombre, su peso y la fecha.
        async with d.Sesion() as s:
            fila = (await s.execute(select(
                CalendarioVersionZip.nombre, CalendarioVersionZip.tamano, CalendarioVersionZip.datos,
                CalendarioVersionZip.created_at,
            ).where(CalendarioVersionZip.version_id == version))).one()
            assert tuple(fila[:3]) == ("piezas niño.zip", len(zip_), zip_) and fila[3] is not None
        # El detalle de la versión lo dice (sin los bytes), al equipo y a la agencia.
        for c in (lider, a1):
            v = (await _detalle(c, tarea_id))["fases"][0]["versiones"][0]
            assert {k: v["zip"][k] for k in ("nombre", "tamano", "guardado")} == {
                "nombre": "piezas niño.zip", "tamano": len(zip_), "guardado": True}
            assert v["zip"]["fecha"]

        # Lo bajan el equipo y las cuentas de la agencia de la tarjeta: tal
        # cual, con su nombre y con lo que pesa (el avance de la bajada).
        for c in (lider, a1, a2):
            r = await c.get(f"/calendario/versiones/{version}/zip")
            assert r.status_code == 200, r.text
            assert r.content == zip_ and r.headers["content-type"] == "application/zip"
            assert r.headers["content-length"] == str(len(zip_))
            assert r.headers["content-disposition"] == (
                "attachment; filename=\"piezas ni_o.zip\"; filename*=UTF-8''piezas%20ni%C3%B1o.zip")
        # Con partes que no lo dividen justo, también; y midiendo justo partes
        # enteras termina sin otra vuelta a la base (no avisa nada).
        for parte in (len(zip_) - 1, 100_000):
            monkeypatch.setattr(rutas_de_entregas, "_PARTE_DEL_ZIP", parte)
            r = await lider.get(f"/calendario/versiones/{version}/zip")
            assert r.content == zip_ and r.headers["content-length"] == str(len(zip_)), parte
        assert "se borró mientras se bajaba" not in caplog.text
        # Las mismas reglas que las imágenes de la versión: otra agencia, y
        # alguien del equipo a quien la acción le queda fuera de su alcance,
        # ni la imagen ni el ZIP (el 404 de lo que no existe).
        imagen = (await _detalle(lider, tarea_id))["fases"][0]["versiones"][0]["imagenes"][0]["id"]
        for u in (d.b1, d.limitado, d.sin_cal):
            c = Cliente(d.http, u)
            assert (await c.get(f"/calendario/entregas/imagenes/{imagen}")).status_code == 404, u.full_name
            r = await c.get(f"/calendario/versiones/{version}/zip")
            assert r.status_code == 404 and r.json()["detail"] == "Esa ronda no tiene un ZIP", (u.full_name, r.text)
        assert (await b1.get(f"/calendario/versiones/{version}/zip")).status_code == 404
        # Una ronda sin ZIP, o que no existe: 404.
        assert (await _decidir(lider, version, "cambios", "Otra vuelta")).status_code == 200
        assert (await _entregar_link(a1, tarea_id, f"ve-zl-{d.sufijo}")).status_code == 201
        assert (await _detalle(lider, tarea_id))["fases"][0]["versiones"][-1]["zip"] is None
        assert (await lider.get(f"/calendario/versiones/ve-zl-{d.sufijo}/zip")).status_code == 404
        assert (await lider.get("/calendario/versiones/ve-no-existe/zip")).status_code == 404
    correr(prueba)


def test_el_zip_va_a_la_base_de_a_uno_en_todo_el_proceso(monkeypatch):
    """Revisión del 19/11/2026: mandarle a la base un ZIP de 40 MB arma copias
    en memoria (unos 120 MB más), y dos entregas grandes a la vez no entran en
    los 512 MB del servidor. El INSERT del ZIP sale con el semáforo tomado, y
    adentro no pasa nada más (no espera candados de la base: no se traba)."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    semaforo = rutas_de_entregas._UN_ZIP_POR_VEZ
    assert isinstance(semaforo, asyncio.Semaphore)

    async def de_a_uno():
        async with semaforo:
            return semaforo.locked()
    assert asyncio.run(de_a_uno())  # con un ZIP adentro, el siguiente espera

    class Espia:
        tomado = False

        async def __aenter__(self):
            Espia.tomado = True

        async def __aexit__(self, *error):
            Espia.tomado = False

    adentro = []

    def anotar(conn, cursor, sentencia, parametros, contexto, varios):
        if Espia.tomado:
            adentro.append(" ".join(sentencia.split()[:3]))

    _espiar_la_ia(monkeypatch)
    monkeypatch.setattr(rutas_de_entregas, "_UN_ZIP_POR_VEZ", Espia())

    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lider)
        zip_ = _zip_de_prueba({"pieza.jpg": _jpeg_de_verdad()})
        r = await _entregar(Cliente(d.http, d.a1), tarea_id, f"ve-uno-{d.sufijo}", imagenes=1,
                            zip_=("pieza.zip", zip_), ya_subidas="[0]")
        assert r.status_code == 201 and r.json()["zip"]["guardado"] is True, r.text

    event.listen(Engine, "before_cursor_execute", anotar)
    try:
        correr(prueba)
    finally:
        event.remove(Engine, "before_cursor_execute", anotar)
    assert adentro == ["INSERT INTO calendario_version_zips"]


def test_un_zip_con_solo_un_pdf_alcanza_y_sus_paginas_se_ven_y_se_marcan(monkeypatch):
    """Ivan no entendía por qué un ZIP con solo el PDF del folleto no
    alcanzaba para entregar ("no entendí este punto"): no tenía que pasar. Al
    entregar, el servidor llena los lugares de imagen que quedan con las
    páginas de los PDF (y las imágenes que el navegador no pudo sacar), en el
    orden del ZIP, y quedan como cualquier imagen de la ronda: quien aprueba
    las ve y las marca. La IA no vuelve a mirar lo que ya está en la ronda."""
    from PIL import Image

    llamadas = _espiar_la_ia(monkeypatch)

    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)

        # Solo el folleto, de dos páginas: alcanza.
        zip_ = _zip_de_prueba({"folleto.pdf": _pdf_de_prueba(2), "leeme.txt": b"hola"})
        v1 = f"ve-pdf1-{d.sufijo}"
        r = await _entregar(a1, tarea_id, v1, zip_=("folleto.zip", zip_))
        assert r.status_code == 201, r.text
        assert r.json()["zip"]["sumadas"] == 2 and r.json()["zip"]["archivos"] == []
        imagenes = (await _detalle(lider, tarea_id))["fases"][0]["versiones"][0]["imagenes"]
        assert [im["orden"] for im in imagenes] == [0, 1]
        for im in imagenes:
            r = await lider.get(f"/calendario/entregas/imagenes/{im['id']}")
            assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
            assert Image.open(io.BytesIO(r.content)).size == (1131, 1600)
            r = await a1.get(f"/calendario/entregas/imagenes/{im['id']}", params={"tam": "mini"})
            assert r.status_code == 200 and max(Image.open(io.BytesIO(r.content)).size) == 320
        # Todo el ZIP ya está en la ronda: la IA mira las imágenes de la ronda
        # y no recibe el ZIP (no queda ocupando memoria esperando su turno).
        assert llamadas[-1] == (v1, {"zip_datos": None, "zip_nombre": None, "zip_saltar": frozenset({0}),
                                     "zip_paginas": {}})
        # Quien aprueba marca sobre una página como sobre cualquier imagen.
        r = await lider.post(f"/calendario/versiones/{v1}/decision", json={
            "decision": "cambios", "marcas": [{"imagenId": imagenes[1]["id"], "x": 0.5, "y": 0.2, "texto": "El precio"}]})
        assert r.status_code == 200, r.text

        # Con una imagen subida y un PDF largo: llena los 3 lugares que quedan,
        # y la IA mira las páginas que siguen (desde la 4).
        zip_ = _zip_de_prueba({"header.jpg": _jpeg_de_verdad(), "catalogo.pdf": _pdf_de_prueba(6)})
        v2 = f"ve-pdf2-{d.sufijo}"
        r = await _entregar(a1, tarea_id, v2, imagenes=1, zip_=("catalogo.zip", zip_), ya_subidas="[0]")
        assert r.status_code == 201, r.text
        assert r.json()["zip"]["sumadas"] == 3 and r.json()["zip"]["archivos"] == ["catalogo.pdf"]
        assert len((await _detalle(lider, tarea_id))["fases"][0]["versiones"][1]["imagenes"]) == 4
        assert llamadas[-1] == (v2, {"zip_datos": zip_, "zip_nombre": "catalogo.zip", "zip_saltar": frozenset({0}),
                                     "zip_paginas": {1: 3}})
        assert (await _decidir(lider, v2, "cambios", "Otra vuelta")).status_code == 200

        # Una imagen que la persona sacó de la ronda a propósito (va en
        # zipYaSubidas) no vuelve; una que el navegador no pudo sacar, sí.
        zip_ = _zip_de_prueba({"a.jpg": _jpeg_de_verdad(), "b.jpg": _jpeg_de_verdad(), "c.jpg": _jpeg_de_verdad()})
        v3 = f"ve-pdf3-{d.sufijo}"
        r = await _entregar(a1, tarea_id, v3, imagenes=1, zip_=("abc.zip", zip_), ya_subidas="[0, 1]")
        assert r.status_code == 201, r.text
        assert r.json()["zip"]["sumadas"] == 1
        assert len((await _detalle(lider, tarea_id))["fases"][0]["versiones"][2]["imagenes"]) == 2
        assert (await _decidir(lider, v3, "cambios", "Otra más")).status_code == 200

        # Un ZIP del que no sale nada para ver (el PDF pide contraseña) no
        # alcanza solo, y dice por qué; con el link, sí.
        import pymupdf
        doc = pymupdf.open()
        doc.new_page()
        cerrado = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="x")
        doc.close()
        zip_ = _zip_de_prueba({"cerrado.pdf": cerrado})
        r = await _entregar(a1, tarea_id, f"ve-pdf4-{d.sufijo}", zip_=("cerrado.zip", zip_))
        assert r.status_code == 422 and "«cerrado.pdf»: el PDF está protegido con contraseña" in r.json()["detail"], r.text
        r = await _entregar(a1, tarea_id, f"ve-pdf4-{d.sufijo}", zip_=("cerrado.zip", zip_),
                            link="https://we.tl/t-AbCdEf12")
        assert r.status_code == 201, r.text
        assert r.json()["zip"]["sumadas"] == 0 and r.json()["zip"]["guardado"] is True
    correr(prueba)


async def _zips_guardados(d) -> int:
    """Lo que ocupan entre todos los ZIP guardados (con sus bytes)."""
    async with d.Sesion() as s:
        return (await s.execute(
            select(func.coalesce(func.sum(CalendarioVersionZip.tamano), 0))
            .where(CalendarioVersionZip.datos.isnot(None))
        )).scalar_one()


def test_con_el_tope_de_los_zip_lleno_no_se_guarda_la_entrega_sigue_y_no_se_borra_nada(monkeypatch, caplog):
    """Revisión del 19/11/2026: los ZIP tienen su propio tope entre todos
    (ZIP_TOPE_MB), aunque la base tenga lugar; antes era una reserva que no
    protegía a las imágenes. Con el tope lleno la entrega se hace igual: la
    versión y sus imágenes, y del ZIP el nombre y el peso, para que la ficha
    diga que no se guardó. NUNCA se borra nada para hacerle lugar. Y con
    lugar se guarda: lo que cuenta es lo que pesan los guardados (uno que no
    se guardó no ocupa nada)."""
    from sqlalchemy import text

    from app.core.config import settings

    _espiar_la_ia(monkeypatch)

    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        mb = 1024 * 1024
        async with d.Sesion() as s:
            tamano = (await s.execute(text("SELECT pg_database_size(current_database())"))).scalar_one()
        # La base, con lugar de sobra: lo que frena acá es el tope de los ZIP.
        monkeypatch.setattr(settings, "BASE_TOPE_MB", -(-tamano // mb) + 200)
        primero = _zip_de_prueba({"pieza.jpg": _jpeg_de_verdad()})
        v1, v2, v3 = (f"ve-zt{i}-{d.sufijo}" for i in (1, 2, 3))
        r = await _entregar(a1, tarea_id, v1, imagenes=1, zip_=("r1.zip", primero), ya_subidas="[0]")
        assert r.status_code == 201 and r.json()["zip"]["guardado"] is True, r.text
        assert (await _decidir(lider, v1, "cambios", "Otra vuelta")).status_code == 200

        # El tope, con entre 1 y 2 MB libres: un ZIP de 3 MB no entra.
        ocupado = await _zips_guardados(d)
        assert ocupado >= len(primero)
        monkeypatch.setattr(settings, "ZIP_TOPE_MB", -(-ocupado // mb) + 1)
        segundo = _zip_de_prueba({"pieza.jpg": _jpeg_de_verdad(), "fuente.otf": os.urandom(3 * mb)})
        caplog.clear()
        r = await _entregar(a1, tarea_id, v2, imagenes=1, zip_=("r2.zip", segundo), ya_subidas="[0]")
        assert r.status_code == 201, r.text
        assert r.json()["zip"]["guardado"] is False
        # Lo frenó el tope de los ZIP (queda en el log para quien administra), no la base.
        assert "(ZIP_TOPE_MB)" in caplog.text and "(BASE_TOPE_MB)" not in caplog.text
        det = await _detalle(lider, tarea_id)
        v_1, v_2 = det["fases"][0]["versiones"]
        assert v_2["zip"]["guardado"] is False and v_2["zip"]["tamano"] == len(segundo)
        assert len(v_2["imagenes"]) == 1 and det["resumen"]["momento"] == "revision"
        r = await lider.get(f"/calendario/versiones/{v2}/zip")
        assert r.status_code == 404 and "no se guardó porque no había lugar en la base" in r.json()["detail"]
        # Lo de antes, entero.
        assert v_1["zip"]["guardado"] is True
        assert (await lider.get(f"/calendario/versiones/{v1}/zip")).content == primero
        assert await _zips_guardados(d) == ocupado

        # Con lugar justo para él (el que no se guardó no cuenta), se guarda.
        assert (await _decidir(lider, v2, "cambios", "Otra vuelta más")).status_code == 200
        monkeypatch.setattr(settings, "ZIP_TOPE_MB", -(-(ocupado + len(segundo)) // mb))
        assert (ocupado + len(segundo) + len(segundo)) > settings.ZIP_TOPE_MB * mb
        r = await _entregar(a1, tarea_id, v3, imagenes=1, zip_=("r3.zip", segundo), ya_subidas="[0]")
        assert r.status_code == 201 and r.json()["zip"]["guardado"] is True, r.text
        assert (await lider.get(f"/calendario/versiones/{v3}/zip")).content == segundo
        assert await _zips_guardados(d) == ocupado + len(segundo)
    correr(prueba)


def test_con_la_base_llena_el_zip_no_se_guarda_la_entrega_sigue_y_no_se_borra_nada(monkeypatch, caplog):
    """Si la base no tiene lugar para el ZIP, aunque entre en el tope de los
    ZIP, la entrega se hace igual: quedan la versión y sus imágenes, y del ZIP
    el nombre y el peso, para que la ficha diga que no se guardó. NUNCA se
    borra nada para hacerle lugar: el ZIP y las imágenes de la ronda anterior
    siguen enteros."""
    from sqlalchemy import text

    from app.core.config import settings

    _espiar_la_ia(monkeypatch)

    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        primero = _zip_de_prueba({"pieza.jpg": _jpeg_de_verdad()})
        v1, v2 = f"ve-ll1-{d.sufijo}", f"ve-ll2-{d.sufijo}"
        assert (await _entregar(a1, tarea_id, v1, imagenes=1, zip_=("r1.zip", primero), ya_subidas="[0]")).status_code == 201
        assert (await _decidir(lider, v1, "cambios", "Otra vuelta")).status_code == 200
        async with d.Sesion() as s:
            antes = {
                "zips": (await s.execute(select(func.count()).select_from(CalendarioVersionZip))).scalar_one(),
                "imagenes": (await s.execute(select(func.count()).select_from(CalendarioVersionImagen))).scalar_one(),
            }
            tamano = (await s.execute(text("SELECT pg_database_size(current_database())"))).scalar_one()
        # La base, casi en el tope: entre 1 y 2 MB libres, que alcanzan para
        # las imágenes y no para el ZIP. El tope de los ZIP, con lugar.
        mb = 1024 * 1024
        monkeypatch.setattr(settings, "BASE_TOPE_MB", -(-tamano // mb) + 1)
        monkeypatch.setattr(settings, "ZIP_TOPE_MB", 1000)
        segundo = _zip_de_prueba({"pieza.jpg": _jpeg_de_verdad(), "fuente.otf": os.urandom(3 * mb)})
        caplog.clear()
        r = await _entregar(a1, tarea_id, v2, imagenes=1, zip_=("r2.zip", segundo), ya_subidas="[0]")
        assert r.status_code == 201, r.text
        assert r.json()["zip"]["guardado"] is False
        # Lo frenó la base (el tope de los ZIP tenía lugar).
        assert "(BASE_TOPE_MB)" in caplog.text and "(ZIP_TOPE_MB)" not in caplog.text
        det = await _detalle(lider, tarea_id)
        v_1, v_2 = det["fases"][0]["versiones"]
        assert v_2["zip"]["guardado"] is False and v_2["zip"]["tamano"] == len(segundo)
        assert len(v_2["imagenes"]) == 1 and det["resumen"]["momento"] == "revision"
        r = await lider.get(f"/calendario/versiones/{v2}/zip")
        assert r.status_code == 404 and "no se guardó porque no había lugar en la base" in r.json()["detail"]
        # Lo de antes, entero.
        assert v_1["zip"]["guardado"] is True
        assert (await lider.get(f"/calendario/versiones/{v1}/zip")).content == primero
        assert (await lider.get(f"/calendario/entregas/imagenes/{v_1['imagenes'][0]['id']}")).status_code == 200
        async with d.Sesion() as s:
            assert (await s.execute(select(func.count()).select_from(CalendarioVersionZip))).scalar_one() == antes["zips"] + 1
            assert (await s.execute(select(func.count()).select_from(CalendarioVersionImagen))).scalar_one() == antes["imagenes"] + 1
            assert (await s.execute(
                select(CalendarioVersionZip.datos).where(CalendarioVersionZip.version_id == v2)
            )).scalar_one() is None
    correr(prueba)


def test_la_ia_recibe_lo_que_se_pidio_en_la_ronda_anterior_y_lo_ve_solo_quien_aprueba(monkeypatch):
    """Ivan (19/11/2026), cuando se le contó que la IA no comparaba con la
    ronda anterior: "debería de hacerlo (...) si ves que algo no anda, ¿por
    qué no arreglarlo?". Con la base de verdad: lo que la IA recibe de la
    ronda anterior (cada marca con su imagen por orden y su lugar, y el
    comentario de quien pidió los cambios, no la nota interna) y que lo que
    contestó lo ve quien aprueba, nunca la agencia. Lo que hace la IA con eso
    está en test_revision_ia.py. Desde la revisión del 19/11/2026 recibe
    además las miniaturas de esa ronda, para comparar."""
    from app.services import revision_ia

    # Entregar no dispara la revisión de verdad (acá no hay clave; por las dudas).
    monkeypatch.setattr(revision_ia, "activa", lambda: False)

    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        # Las miniaturas, de verdad y de distinto tamaño: así se ve su orden.
        dos = [("imagenes", ("a.jpg", JPEG, "image/jpeg")),
               ("miniaturas", ("m.jpg", _jpeg_de_verdad(64, 48), "image/jpeg")),
               ("imagenes", ("b.jpg", JPEG, "image/jpeg")),
               ("miniaturas", ("n.jpg", _jpeg_de_verdad(48, 64), "image/jpeg"))]
        v1, v2, v3 = (f"ve-r{i}-{d.sufijo}" for i in (1, 2, 3))
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": v1}, files=dos)
        assert r.status_code == 201, r.text
        det = await _detalle(lider, tarea_id)
        im1, im2 = [i["id"] for i in det["fases"][0]["versiones"][0]["imagenes"]]
        r = await lider.post(f"/calendario/versiones/{v1}/decision", json={
            "decision": "cambios", "comentario": "Revisen también los legales.",
            "notaInterna": "Ojo: comercial todavía no confirmó el precio",
            "marcas": [{"imagenId": im2, "x": 0.5, "y": 0.9, "texto": "Falta la tilde en «Válido»"},
                       {"imagenId": im1, "x": 0.12, "y": 0.08, "texto": "Agrandar el -40%"}]})
        assert r.status_code == 200, r.text
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": v2}, files=dos)
        assert r.status_code == 201, r.text

        async with d.Sesion() as s:
            contexto, imagenes = await revision_ia.cargar_version(s, v2)
            assert contexto.ronda == 2 and len(imagenes) == 2
            antes = contexto.ronda_anterior
            assert (antes.ronda, antes.imagenes, antes.comentarios) == (1, 2, ("Revisen también los legales.",))
            assert [(m.numero, m.texto, m.imagen, m.x, m.y) for m in antes.marcas] == [
                (1, "Falta la tilde en «Válido»", 2, 0.5, 0.9), (2, "Agrandar el -40%", 1, 0.12, 0.08)]
            marcas = [m.marca_id for m in antes.marcas]
            texto = revision_ia.texto_del_pedido(contexto)
            assert "- Marca 1, en la imagen 2, abajo en el centro (50% del ancho, 90% del alto): Falta la tilde" in texto
            # La nota interna no va: es del equipo, no algo que se le pidió a la agencia.
            assert "comercial" not in texto
            # La primera ronda no tiene nada antes.
            assert (await revision_ia.cargar_version(s, v1))[0].ronda_anterior is None
            # Las miniaturas de la ronda 1, en su orden y con el número de su imagen.
            assert [(m.numero, m.ancho, m.alto) for m in antes.miniaturas] == [(1, 64, 48), (2, 48, 64)]
            # Una que no está (la purga de antes del 19/11/2026 vació algunas)
            # no va, y la otra conserva su número: el que dicen las marcas.
            await s.execute(update(CalendarioVersionImagen).where(CalendarioVersionImagen.id == im1)
                            .values(miniatura=None))
            antes = (await revision_ia.cargar_version(s, v2))[0].ronda_anterior
            assert [(m.numero, m.ancho, m.alto) for m in antes.miniaturas] == [(2, 48, 64)]
            assert [(m.numero, m.imagen) for m in antes.marcas] == [(1, 2), (2, 1)]
            await s.rollback()  # la purga era solo para esta prueba

        # Lo que contestó la IA (una revisión guardada) lo ve quien aprueba;
        # la agencia, nunca.
        async with d.Sesion() as s:
            s.add(CalendarioRevisionIA(
                version_id=v2, estado="lista", modelo="simulado", observaciones=[],
                cambios_pedidos=[
                    {"marcaId": marcas[0], "numero": 1, "veredicto": "falta", "nota": "Sigue sin tilde."},
                    {"marcaId": marcas[1], "numero": 2, "veredicto": "hecho", "nota": "El -40% ahora es más grande."},
                ],
            ))
            await s.commit()
        r = await lider.get(f"/calendario/versiones/{v2}/revision-ia")
        assert r.status_code == 200, r.text
        assert r.json()["cambiosPedidos"] == [
            {"marcaId": marcas[0], "numero": 1, "veredicto": "falta", "nota": "Sigue sin tilde."},
            {"marcaId": marcas[1], "numero": 2, "veredicto": "hecho", "nota": "El -40% ahora es más grande."},
        ]
        assert (await a1.get(f"/calendario/versiones/{v2}/revision-ia")).status_code == 403
        # Sin revisión guardada (la primera ronda), nada.
        r = await lider.get(f"/calendario/versiones/{v1}/revision-ia")
        assert r.status_code == 200 and r.json()["estado"] == "nada" and r.json()["cambiosPedidos"] == []

        # Si vuelve solo con un comentario, sin marcas, el comentario es lo que
        # se pidió (20/11/2026: antes no iba nada y la agencia no veía el
        # control): cada renglón, un pedido sin lugar en la imagen.
        assert (await _decidir(lider, v2, "cambios", "Otra vuelta: todo más grande")).status_code == 200
        r = await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": v3}, files=dos)
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            anterior = (await revision_ia.cargar_version(s, v3))[0].ronda_anterior
            assert [(m.marca_id, m.texto, m.x) for m in anterior.marcas] == [
                ("comentario-1", "Otra vuelta: todo más grande", None)]
            assert anterior.comentarios == ()
    correr(prueba)


def test_la_ia_le_avisa_a_la_agencia_antes_de_entregar(monkeypatch):
    """Ivan (20/11/2026): "que a la agencia, cuando va a subir los archivos,
    la IA le diga 'che, pará, acá faltan estas cositas de los cambios'".
    Antes de mandar, con las mismas imágenes: a la agencia vuelve solo el
    veredicto de cada marca pedida; si entrega exactamente esas, la revisión
    del aprobador sale de ahí (no se paga dos veces); si cambió algo, corre la
    de siempre. Sin IA, 'no-disponible' (la pantalla manda igual)."""
    import json

    import ia_simulada as sim

    from app.core.config import settings
    from app.models.revision_ia import CalendarioControlPrevio
    from app.services import ia_cliente, revision_ia

    monkeypatch.setattr(settings, "IA_REVISION_ACTIVA", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-simulada")
    monkeypatch.setattr(settings, "MODELO_IA_REVISION", "claude-opus-5-5")
    monkeypatch.setattr(settings, "IA_REVISION_POR_DIA", 10_000)
    en_segundo_plano = []

    async def espia(version_id, **kw):
        en_segundo_plano.append(version_id)

    monkeypatch.setattr(revision_ia, "revisar_version", espia)

    def respuesta(*cambios):
        cuerpo = {
            "observaciones": [{"tipo": "ortografia", "texto": "Dice «Valido»: debería ser «Válido».",
                               "gravedad": "importante", "imagen": 2, "x": 150, "y": 300}],
            "cambios_pedidos": list(cambios),
        }
        return sim.mensaje([sim.pensamiento(), sim.texto(json.dumps(cuerpo))], entrada=5_000, salida=900)

    api = sim.ApiGrabada([respuesta(
        {"numero": 1, "veredicto": "falta", "nota": "Sigue diciendo «Valido», sin tilde."},
        {"numero": 2, "veredicto": "hecho", "nota": "El -40% ahora ocupa más lugar."},
    )])
    monkeypatch.setattr(ia_cliente, "cliente_anthropic", lambda: api.cliente())

    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        mini = _jpeg_de_verdad(64, 48)

        def ronda(*colores):
            files = []
            for i, color in enumerate(colores):
                files += [("imagenes", (f"i{i}.jpg", _jpeg_de_verdad(400, 300 + i, color), "image/jpeg")),
                          ("miniaturas", (f"m{i}.jpg", mini, "image/jpeg"))]
            return files

        dos = ronda("white", "black")
        solo_imagenes = [f for f in dos if f[0] == "imagenes"]
        control = f"/calendario/tareas/{tarea_id}/control-previo"
        versiones = f"/calendario/tareas/{tarea_id}/versiones"
        v1, v2, v3 = (f"ve-cp{i}-{d.sufijo}" for i in (1, 2, 3))

        # Primera ronda: no hay cambios pedidos que controlar; la IA ni se entera.
        r = await a1.post(control, files=solo_imagenes)
        assert r.status_code == 200 and r.json() == {"estado": "sin-pedido", "cambios": [], "controlId": None}, r.text
        assert (await a1.post(versiones, data={"versionId": v1}, files=dos)).status_code == 201
        assert en_segundo_plano == [v1]  # la revisión de siempre
        det = await _detalle(lider, tarea_id)
        im1, im2 = [i["id"] for i in det["fases"][0]["versiones"][0]["imagenes"]]
        r = await lider.post(f"/calendario/versiones/{v1}/decision", json={
            "decision": "cambios", "comentario": "Dos cositas.",
            "marcas": [{"imagenId": im2, "x": 0.5, "y": 0.9, "texto": "Falta la tilde en «Válido»"},
                       {"imagenId": im1, "x": 0.12, "y": 0.08, "texto": "Agrandar el -40%"}]})
        assert r.status_code == 200, r.text

        # Solo quien entrega la pide.
        assert (await lider.post(control, files=solo_imagenes)).status_code == 403

        # Vuelve: antes de mandar, la IA dice marca por marca. A la agencia, solo eso.
        r = await a1.post(control, data={"comentario": "Corregí la tilde"}, files=solo_imagenes)
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["estado"] == "listo" and cuerpo["controlId"]
        assert cuerpo["cambios"] == [
            {"numero": 1, "texto": "Falta la tilde en «Válido»", "veredicto": "falta",
             "nota": "Sigue diciendo «Valido», sin tilde."},
            {"numero": 2, "texto": "Agrandar el -40%", "veredicto": "hecho", "nota": "El -40% ahora ocupa más lugar."},
        ]
        assert "observaciones" not in json.dumps(cuerpo) and "OFERTA" not in json.dumps(cuerpo)
        assert len(api.pedidos) == 1
        texto = api.pedidos[0]["messages"][0]["content"][-1]["text"]
        assert "<cambios_pedidos>" in texto and "Falta la tilde en «Válido»" in texto and "ronda 2" in texto

        # Entrega exactamente esas: la revisión sale del control, sin volver a llamar a la IA.
        assert (await a1.post(versiones, data={"versionId": v2}, files=dos)).status_code == 201
        assert en_segundo_plano == [v1] and len(api.pedidos) == 1
        r = await lider.get(f"/calendario/versiones/{v2}/revision-ia")
        assert r.status_code == 200, r.text
        revision = r.json()
        det = await _detalle(lider, tarea_id)
        de_v2 = next(v for v in det["fases"][0]["versiones"] if v["id"] == v2)["imagenes"]
        assert revision["estado"] == "lista"
        [obs] = revision["observaciones"]
        assert obs["imagenId"] == de_v2[1]["id"] and (obs["x"], obs["y"]) == (0.375, 0.997)
        assert [(c["numero"], c["veredicto"]) for c in revision["cambiosPedidos"]] == [(1, "falta"), (2, "hecho")]
        assert (await a1.get(f"/calendario/versiones/{v2}/revision-ia")).status_code == 403
        async with d.Sesion() as s:
            fila = await s.get(CalendarioControlPrevio, cuerpo["controlId"])
            assert fila.usado_en_version_id == v2 and fila.input_tokens == 5_000 and fila.estado == "lista"
            assert (await s.get(CalendarioRevisionIA, v2)).input_tokens == 5_000

        # Otra vuelta, pero entrega imágenes distintas de las del control: corre la de siempre.
        r = await lider.post(f"/calendario/versiones/{v2}/decision", json={
            "decision": "cambios",
            "marcas": [{"imagenId": de_v2[1]["id"], "x": 0.5, "y": 0.9, "texto": "Sigue sin tilde"}]})
        assert r.status_code == 200, r.text
        api.respuestas.append(respuesta({"numero": 1, "veredicto": "dudoso", "nota": "No se lee bien."}))
        r = await a1.post(control, files=solo_imagenes)
        assert r.json()["estado"] == "listo" and r.json()["cambios"][0]["veredicto"] == "dudoso", r.text
        segundo = r.json()["controlId"]
        assert (await a1.post(versiones, data={"versionId": v3}, files=ronda("white", "red"))).status_code == 201
        assert en_segundo_plano == [v1, v3]
        async with d.Sesion() as s:
            assert (await s.get(CalendarioControlPrevio, segundo)).usado_en_version_id is None

        # Sin la IA, 'no-disponible': la pantalla entrega igual.
        r = await lider.post(f"/calendario/versiones/{v3}/decision", json={
            "decision": "cambios", "marcas": [{"x": 0.5, "y": 0.5, "texto": "Una más",
                                               "imagenId": next(v for v in (await _detalle(lider, tarea_id))["fases"][0]["versiones"] if v["id"] == v3)["imagenes"][0]["id"]}]})
        assert r.status_code == 200, r.text
        # Si la IA falla (acá, se niega), 'no-disponible' y queda anotado.
        api.respuestas.append(sim.mensaje([sim.texto("")], stop_reason="refusal", entrada=900, salida=10))
        r = await a1.post(control, files=solo_imagenes)
        assert r.status_code == 200 and r.json() == {"estado": "no-disponible", "cambios": [], "controlId": None}, r.text
        async with d.Sesion() as s:
            # Todo corre en una transacción: created_at es igual en todas; se
            # busca por descarte de los dos de antes.
            ultimo = (await s.execute(select(CalendarioControlPrevio).where(
                CalendarioControlPrevio.tarea_id == tarea_id,
                CalendarioControlPrevio.id.notin_([cuerpo["controlId"], segundo]),
            ))).scalar_one()
            assert ultimo.estado == "error" and "refusal" in ultimo.motivo and ultimo.input_tokens == 900
        # Sin clave, ni se le pregunta.
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
        r = await a1.post(control, files=solo_imagenes)
        assert r.status_code == 200 and r.json()["estado"] == "no-disponible", r.text
        assert len(api.pedidos) == 3
    correr(prueba)


def test_la_ia_tambien_controla_lo_pedido_solo_en_el_comentario(monkeypatch):
    """Ivan (20/11/2026): "me comenta la agencia que al momento de subir la
    entrega no les apareció la IA para las correcciones". Se habían pedido
    los cambios solo con texto (sin marcas): ahora cada renglón del
    comentario es un pedido que la IA controla antes de entregar."""
    import json

    import ia_simulada as sim

    from app.core.config import settings
    from app.services import ia_cliente, revision_ia

    monkeypatch.setattr(settings, "IA_REVISION_ACTIVA", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-simulada")
    monkeypatch.setattr(settings, "IA_REVISION_POR_DIA", 10_000)

    async def espia(version_id, **kw):
        return None

    monkeypatch.setattr(revision_ia, "revisar_version", espia)
    cuerpo = {"observaciones": [], "cambios_pedidos": [
        {"numero": 1, "veredicto": "falta", "nota": "Sigue diciendo $249."},
        {"numero": 2, "veredicto": "hecho", "nota": "El logo viejo ya no está."},
    ]}
    api = sim.ApiGrabada([sim.mensaje([sim.texto(json.dumps(cuerpo))], entrada=3_000, salida=300)])
    monkeypatch.setattr(ia_cliente, "cliente_anthropic", lambda: api.cliente())

    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        imagenes = [("imagenes", ("i.jpg", _jpeg_de_verdad(400, 300, "white"), "image/jpeg")),
                    ("miniaturas", ("m.jpg", _jpeg_de_verdad(64, 48), "image/jpeg"))]
        v1 = f"ve-co1-{d.sufijo}"
        assert (await a1.post(f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": v1}, files=imagenes)).status_code == 201
        # Cambios pedidos solo con texto, como desde el tablero ("¿Qué hay que cambiar?").
        r = await lider.post(f"/calendario/versiones/{v1}/decision", json={
            "decision": "cambios", "comentario": "- Cambiar el precio a $199\n- Sacar el logo viejo"})
        assert r.status_code == 200, r.text

        r = await a1.post(f"/calendario/tareas/{tarea_id}/control-previo", files=[imagenes[0]])
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "listo"
        assert [(c["numero"], c["texto"], c["veredicto"]) for c in r.json()["cambios"]] == [
            (1, "Cambiar el precio a $199", "falta"), (2, "Sacar el logo viejo", "hecho"),
        ]
        texto = api.pedidos[0]["messages"][0]["content"][-1]["text"]
        assert "pedida en el comentario" in texto and "Cambiar el precio a $199" in texto
    correr(prueba)


def test_la_ia_controla_solo_la_ronda_anterior_de_la_misma_fase(monkeypatch):
    """Revisión del 19/11/2026: lo que se pidió cuenta solo dentro de la misma
    fase. El Boceto vuelve con cambios y una marca, su ronda 2 se aprueba y
    arranca el Arte final: su ronda 1 no tiene nada que controlar (lo de antes
    es de otra fase), y su ronda 2 recibe lo que se pidió en su ronda 1, con
    sus miniaturas. Las marcas del Boceto no aparecen nunca."""
    from app.models.entregas import CalendarioMarca
    from app.services import revision_ia

    monkeypatch.setattr(revision_ia, "activa", lambda: False)

    async def prueba(d):
        lider, a1 = Cliente(d.http, d.lider), Cliente(d.http, d.a1)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        r = await lider.put(f"/calendario/tareas/{tarea_id}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.lider.id],
            "fases": [{"nombre": "Boceto"}, {"nombre": "Arte final"}]})
        assert r.status_code == 200, r.text
        b1, b2, f1, f2 = (f"ve-{n}-{d.sufijo}" for n in ("bo1", "bo2", "af1", "af2"))

        # Boceto: la ronda 1 vuelve con cambios y una marca; la 2 se aprueba.
        assert (await _entregar(a1, tarea_id, b1, imagenes=1)).status_code == 201
        imagen = (await _detalle(lider, tarea_id))["fases"][0]["versiones"][0]["imagenes"][0]["id"]
        r = await lider.post(f"/calendario/versiones/{b1}/decision", json={
            "decision": "cambios", "comentario": "Boceto: probemos otra foto",
            "marcas": [{"imagenId": imagen, "x": 0.5, "y": 0.5, "texto": "Boceto: otra foto de fondo"}]})
        assert r.status_code == 200, r.text
        assert (await _entregar(a1, tarea_id, b2, imagenes=1)).status_code == 201
        assert (await _decidir(lider, b2, "aprobada")).status_code == 200

        # Arte final, ronda 1: lo de antes es del Boceto, otra fase. Nada que controlar.
        assert (await _entregar(a1, tarea_id, f1, imagenes=1, color="black")).status_code == 201
        async with d.Sesion() as s:
            contexto, _ = await revision_ia.cargar_version(s, f1)
        assert (contexto.fase, contexto.ronda, contexto.ronda_anterior) == ("Arte final", 1, None)
        assert "Boceto:" not in revision_ia.texto_del_pedido(contexto)

        # Arte final, ronda 2: lo que se pidió en su ronda 1, con sus miniaturas.
        imagen = (await _detalle(lider, tarea_id))["fases"][1]["versiones"][0]["imagenes"][0]["id"]
        r = await lider.post(f"/calendario/versiones/{f1}/decision", json={
            "decision": "cambios", "comentario": "Arte final: falta el legal",
            "marcas": [{"imagenId": imagen, "x": 0.5, "y": 0.9, "texto": "Arte final: agregar el legal"}]})
        assert r.status_code == 200, r.text
        assert (await _entregar(a1, tarea_id, f2, imagenes=1, color="black")).status_code == 201
        async with d.Sesion() as s:
            contexto, _ = await revision_ia.cargar_version(s, f2)
            del_boceto = set((await s.execute(
                select(CalendarioMarca.id).where(CalendarioMarca.version_id.in_([b1, b2]))
            )).scalars())
            miniaturas = dict((await s.execute(
                select(CalendarioVersionImagen.version_id, CalendarioVersionImagen.miniatura)
                .where(CalendarioVersionImagen.version_id.in_([b1, f1]))
            )).all())
        antes = contexto.ronda_anterior
        assert (contexto.fase, contexto.ronda, antes.ronda) == ("Arte final", 2, 1)
        assert [m.texto for m in antes.marcas] == ["Arte final: agregar el legal"]
        assert antes.comentarios == ("Arte final: falta el legal",)
        assert len(del_boceto) == 1 and not del_boceto & {m.marca_id for m in antes.marcas}
        assert "Boceto:" not in revision_ia.texto_del_pedido(contexto)
        # Las miniaturas son las de su ronda 1, no las del Boceto.
        assert miniaturas[f1] != miniaturas[b1]
        assert [m.datos for m in antes.miniaturas] == [miniaturas[f1]]
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


def test_cambiarle_el_nombre_y_ordenar_las_tareas_arrastrando():
    """Ivan (20/11/2026): "editar el título de una tarea ya creada y ordenar
    las tareas arrastrando". Lo hace quien gestiona las tareas; se ordenan
    entre hermanas y las demás no se mueven."""
    async def prueba(d):
        lider, lucia = Cliente(d.http, d.lider), Cliente(d.http, d.lucia)
        ids = [f"ta-ord{i}-{d.sufijo}" for i in range(3)]
        for i, tid in enumerate(ids):
            r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={"id": tid, "titulo": f"Tarea {i}"})
            assert r.status_code == 201, r.text
        hija = f"ta-ordh-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={"id": hija, "parentId": ids[0], "titulo": "Hija"})
        assert r.status_code == 201, r.text

        async def ordenes():
            async with d.Sesion() as s:
                filas = (await s.execute(
                    select(CalendarioTarea).where(CalendarioTarea.barra_id == d.ciber.id)
                    .order_by(CalendarioTarea.orden, CalendarioTarea.created_at, CalendarioTarea.id)
                )).scalars().all()
                return [t.id for t in filas if t.id in ids], {t.id: t.orden for t in filas}

        # Cambiarle el nombre.
        r = await lider.patch(f"/calendario/tareas/{ids[1]}", json={"titulo": "  Mailing final  "})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioTarea, ids[1])).titulo == "Mailing final"
        assert (await lider.patch(f"/calendario/tareas/{ids[1]}", json={"titulo": "   "})).status_code == 422

        # Ordenar: la última pasa primera. La hija no se mueve.
        _, antes = await ordenes()
        nuevo = [ids[2], ids[0], ids[1]]
        r = await lider.put(f"/calendario/barras/{d.ciber.id}/tareas/orden", json={"ids": nuevo})
        assert r.status_code == 200, r.text
        en_orden, despues = await ordenes()
        assert en_orden == nuevo
        assert despues[hija] == antes[hija]
        assert sorted(despues[i] for i in ids) == sorted(antes[i] for i in ids)

        # Quien no gestiona las tareas, no; ni mezclar niveles, ni una tarea de otra acción.
        assert (await lucia.put(f"/calendario/barras/{d.ciber.id}/tareas/orden", json={"ids": ids})).status_code == 403
        r = await lider.put(f"/calendario/barras/{d.ciber.id}/tareas/orden", json={"ids": [ids[0], hija]})
        assert r.status_code == 422
        r = await lider.put(f"/calendario/barras/{d.ciber.id}/tareas/orden", json={"ids": [ids[0], "ta-no-existe"]})
        assert r.status_code == 404
        r = await lider.put(f"/calendario/barras/{d.ciber.id}/tareas/orden", json={"ids": [ids[0], ids[0]]})
        assert r.status_code == 422
        assert (await ordenes())[0] == nuevo
    correr(prueba)


def test_un_aviso_contado_desde_la_fecha_de_un_envio():
    """Ivan (20/11/2026): "que un aviso se pueda programar según la fecha de
    un envío, no solo según el arranque de la acción" (0084). Sale aunque la
    acción ya haya arrancado, se mueve con el envío y se va si se saca."""
    async def prueba(d):
        from app.services import calendario_avisos
        lucia = Cliente(d.http, d.lucia)
        hoy, accion = d.hoy, d.ahora  # arranca hoy
        mail = f"pz-mail-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{accion.id}/piezas", json={
            "id": mail, "area": "email", "formato": "Mailing digital", "desde": (hoy + timedelta(days=3)).isoformat()})
        assert r.status_code == 201, r.text
        web = f"pz-web-{d.sufijo}"
        assert (await lucia.post(f"/calendario/barras/{accion.id}/piezas", json={
            "id": web, "area": "web-home", "formato": "Banner"})).status_code == 201

        # Solo desde un envío de la misma acción.
        base = {"diasAntes": 2, "destinatarios": [d.lucia.id]}
        r = await lucia.post(f"/calendario/barras/{accion.id}/avisos", json={**base, "id": f"av-w-{d.sufijo}", "piezaId": web})
        assert r.status_code == 422
        r = await lucia.post(f"/calendario/barras/{d.ciber.id}/avisos", json={**base, "id": f"av-o-{d.sufijo}", "piezaId": mail})
        assert r.status_code == 404

        aviso = f"av-mail-{d.sufijo}"
        r = await lucia.post(f"/calendario/barras/{accion.id}/avisos", json={**base, "id": aviso, "piezaId": mail})
        assert r.status_code == 201, r.text
        assert r.json()["enviadosAhora"] == 0  # el envío sale en 3 días: todavía no
        datos = (await lucia.get("/calendario/datos", params={"mundo": MUNDO})).json()
        ficha = next(b for b in datos["barras"] if b["id"] == accion.id)
        assert next(a for a in ficha["avisos"] if a["id"] == aviso)["piezaId"] == mail

        async def mensajes():
            async with d.Sesion() as s:
                return [n.mensaje for n in (await s.execute(select(Notificacion).where(
                    Notificacion.user_id == d.lucia.id, Notificacion.origen_ref == f"{accion.id}:{aviso}",
                ))).scalars()]

        # Mañana la acción ya arrancó, pero faltan 2 días para el mailing: sale.
        async with d.Sesion() as s:
            await calendario_avisos.revisar_avisos(s, hoy=hoy + timedelta(days=1), barra_id=accion.id)
        assert await mensajes() == [
            f"{accion.nombre} · Mailing digital (Email) sale en 2 días, el {(hoy + timedelta(days=3)).strftime('%d/%m')}."
            " Aviso configurado por Lucia Equipo."
        ]

        # Sacar el envío se lleva el aviso.
        assert (await d.http.delete(f"{API}/calendario/piezas/{mail}", headers=lucia.headers)).status_code == 200
        async with d.Sesion() as s:
            assert await s.get(CalendarioAviso, aviso) is None
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


def test_la_tarjeta_abierta_se_entera_de_los_cambios():
    """Ivan (20/11/2026): "si se completa una tarea o una entrega y tengo
    abierta la tarjeta, su estado no se actualiza solo". La tarjeta pregunta
    con su huella: si no cambió nada, una línea; si cambió, todo de nuevo."""
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        pieza, _ = await _pedir_banners(d, d.lider)
        r = await lider.put(f"/calendario/tareas/{pieza}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.lider.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text

        async def huella_y_cambio(h):
            r = await lider.get(f"/calendario/tareas/{pieza}/entregas", params={"huella": h})
            assert r.status_code == 200, r.text
            return r.json()["huella"], not r.json().get("sinCambios", False)

        h0 = (await lider.get(f"/calendario/tareas/{pieza}/entregas")).json()["huella"]
        assert await huella_y_cambio(h0) == (h0, False)
        # Sin cambios, la respuesta es solo eso.
        r = await lider.get(f"/calendario/tareas/{pieza}/entregas", params={"huella": h0})
        assert set(r.json()) == {"huella", "sinCambios"}

        # Un comentario la cambia.
        assert (await lider.post(f"/calendario/tareas/{pieza}/comentarios", json={
            "id": f"co-h-{d.sufijo}", "texto": "¿Va con precio?"})).status_code == 201
        h1, cambio = await huella_y_cambio(h0)
        assert cambio and h1 != h0

        # Entrega la agencia: cambia; y la respuesta trae la tarjeta entera.
        a1 = Cliente(d.http, d.a1)
        assert (await _entregar_link(a1, pieza, f"ve-h1-{d.sufijo}")).status_code == 201
        r = await lider.get(f"/calendario/tareas/{pieza}/entregas", params={"huella": h1})
        assert r.json()["huella"] != h1 and r.json()["columna"] == "esperando"
        h2 = r.json()["huella"]

        # Se aprueba: cambia otra vez.
        r = await lider.post(f"/calendario/versiones/ve-h1-{d.sufijo}/decision", json={"decision": "aprobada"})
        assert r.status_code == 200, r.text
        h3, cambio = await huella_y_cambio(h2)
        assert cambio and h3 != h2

        # Completar la tarea a mano (quien lidera) también.
        assert (await lider.patch(f"/calendario/tareas/{pieza}", json={"estado": "en-proceso"})).status_code == 200
        _, cambio = await huella_y_cambio(h3)
        assert cambio
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


def test_la_agencia_se_elige_y_se_compara_sin_tildes_ni_mayusculas():
    """Ivan (19/11/2026): "¿no debería ser una selección?". La empresa de una
    cuenta externa se escribía a mano, y una cuenta con «Disenadores» (sin ñ)
    no veía las tarjetas de Diseñadores (una agencia externa, como Publicis).
    Ahora se elige de una lista, lo que se guarda queda como ya está escrito,
    y lo que ya estaba guardado se compara sin tildes ni mayúsculas, sin tocar
    los datos."""
    async def prueba(d):
        lider, promo = Cliente(d.http, d.lider), Cliente(d.http, d.promo)
        pieza = f"ta-dis-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
            "id": pieza, "tipo": "push", "para": "agencia", "agencia": "disenadores "})
        assert r.status_code == 201, r.text
        assert r.json()["agencia"] == "Diseñadores"

        # Una cuenta guardada antes a mano, sin ñ y en mayúsculas: ve su
        # tarjeta, la abre, ve su tablero y le llega lo nuevo.
        vieja = await _persona(d, "Vieja Cuenta", externo=True, empresa="DISENADORES")
        c = Cliente(d.http, vieja)
        assert await _tarjeta(c, pieza) is not None
        assert (await c.get(f"/calendario/tareas/{pieza}/entregas")).status_code == 200
        assert (await c.get("/calendario/tableros", params={"mundo": MUNDO})).json() == [
            {"nombre": "Diseñadores", "cuentas": 1}]
        otra = f"ta-dis2-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ahora.id}/tareas", json={
            "id": otra, "tipo": "push", "para": "agencia", "agencia": "Diseñadores"})
        assert r.status_code == 201, r.text
        assert len(await _avisos(d, vieja, otra)) == 1

        # La lista del panel: cada agencia una vez, los tres tableros primero.
        r = await promo.get("/admin/agencias")
        assert r.status_code == 200, r.text
        lista = r.json()
        assert lista[:3] == ["Publicis", "Another Monday", "Diseñadores"] and "DISENADORES" not in lista
        assert lista.count(f"Agencia Pampa {d.sufijo}") == 1
        assert (await Cliente(d.http, d.lucia).get("/admin/agencias")).status_code == 403

        # Al crear una cuenta, una agencia que ya existe queda como ya está; una nueva, como se escribió.
        for escrita, guardada in (("  diseñadores", "Diseñadores"),
                                  (f"AGENCIA  PAMPA {d.sufijo}", f"Agencia Pampa {d.sufijo}"),
                                  (f"  Estudio   Nuevo {d.sufijo} ", f"Estudio Nuevo {d.sufijo}")):
            r = await promo.post("/admin/users", json={
                "email": f"n{uuid.uuid4().hex[:6]}.{d.sufijo}@agencia-prueba.uy", "full_name": "Cuenta Nueva",
                "password": "Clave-segura-123", "es_externo": True, "empresa": escrita})
            assert r.status_code == 201, r.text
            assert r.json()["empresa"] == guardada
        # Al editarla, igual: la vieja pasa a escribirse como el tablero y sigue viendo su tarjeta.
        r = await promo.patch(f"/admin/users/{vieja.id}/externo", json={"es_externo": True, "empresa": "disenadores"})
        assert r.status_code == 200, r.text
        assert r.json()["empresa"] == "Diseñadores"
        assert await _tarjeta(c, pieza) is not None
        # A la única cuenta de una agencia se le puede corregir cómo se escribe.
        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={
            "es_externo": True, "empresa": f"Estudio Súr {d.sufijo}"})
        assert r.status_code == 200 and r.json()["empresa"] == f"Estudio Súr {d.sufijo}"
    correr(prueba)


def test_la_lista_de_agencias_para_editar_una_cuenta_no_la_cuenta_a_ella():
    """Revisión del 19/11/2026: al corregir cómo se escribe la única cuenta de
    una agencia que no es un tablero, el panel decía «Ya existe: se guarda
    como «Estudio Sur»» y el servidor guardaba lo nuevo (no la cuenta a ella
    misma). La lista para editarla, GET /admin/agencias?menos=<id>, tampoco:
    da lo mismo que usa el servidor al guardar."""
    async def prueba(d):
        promo = Cliente(d.http, d.promo)
        sur, pampa = f"Estudio Sur {d.sufijo}", f"Agencia Pampa {d.sufijo}"
        completa = (await promo.get("/admin/agencias")).json()
        assert sur in completa and pampa in completa

        # Bruno es la única cuenta de Estudio Sur: sin él, no existe.
        r = await promo.get("/admin/agencias", params={"menos": d.b1.id})
        assert r.status_code == 200, r.text
        sin_bruno = r.json()
        assert sur not in sin_bruno and pampa in sin_bruno
        assert sin_bruno[:3] == ["Publicis", "Another Monday", "Diseñadores"]
        # Y el servidor guarda lo que se escribe, como dice esa lista.
        r = await promo.patch(f"/admin/users/{d.b1.id}/externo", json={
            "es_externo": True, "empresa": f"estudio súr {d.sufijo}"})
        assert r.status_code == 200 and r.json()["empresa"] == f"estudio súr {d.sufijo}"

        # Pampa tiene dos: sin una de ellas, sigue estando (como la escribió
        # la otra, «agencia  pampa», sin los espacios de más).
        assert f"agencia pampa {d.sufijo}" in (await promo.get("/admin/agencias", params={"menos": d.a1.id})).json()
        assert pampa in (await promo.get("/admin/agencias", params={"menos": d.a2.id})).json()
        # La única cuenta de un tablero: el tablero está siempre.
        fer = await _persona(d, "Fer Disenia", externo=True, empresa="Diseñadores")
        assert "Diseñadores" in (await promo.get("/admin/agencias", params={"menos": fer.id})).json()
        # Quien no administra, tampoco con `menos`; y un `menos` que no es un número no entra.
        assert (await Cliente(d.http, d.lucia).get("/admin/agencias", params={"menos": d.b1.id})).status_code == 403
        assert (await promo.get("/admin/agencias", params={"menos": "x"})).status_code == 422
    correr(prueba)


def test_la_empresa_se_compara_igual_en_la_base_que_en_python():
    """La base (`empresa_en_sql`) y Python (`clave_de_empresa`) tienen que dar
    exactamente lo mismo: si no, el tablero de una agencia y su campanita
    (que buscan en la base) no coincidirían con lo que se decide en Python."""
    from sqlalchemy import literal

    from app.core import externos

    async def prueba(d):
        async with d.Sesion() as s:
            for texto in ("Diseñadores", "  DISEÑADORES  ", "Another\tMonday", "Ñandú   Estudio", "Publicis",
                          "ÁÉÍÓÚ áéíóú Üü Çç Ãã", "agencia  pampa"):
                en_la_base = (await s.execute(select(externos.empresa_en_sql(literal(texto))))).scalar_one()
                assert en_la_base == externos.clave_de_empresa(texto), texto
    correr(prueba)


def test_el_responsable_de_una_tarea_de_tienda_es_alguien_de_tienda():
    """19/11/2026: en «Responsable de Tienda Inglesa» aparecían las cuentas de
    las agencias («Fer (Diseñadores)»), y elegir una convertía la tarea
    interna en una pieza de la agencia, con su tarjeta. Ahora el servidor lo
    rechaza con un mensaje claro y la tarea queda como estaba."""
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        fer = await _persona(d, "Fer Disenia", externo=True, empresa="Diseñadores")
        tarea_id = f"ta-r-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": tarea_id, "titulo": "Brief del Ciberlunes", "asignadoA": fer.id})
        assert r.status_code == 422
        assert r.json()["detail"].startswith("Fer Disenia es de Diseñadores, una agencia externa:")
        async with d.Sesion() as s:
            assert await s.get(CalendarioTarea, tarea_id) is None

        # Con alguien de Tienda, sí; y después pasársela a la agencia, no.
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": tarea_id, "titulo": "Brief del Ciberlunes", "asignadoA": d.aprob2.id})
        assert r.status_code == 201, r.text
        r = await lider.patch(f"/calendario/tareas/{tarea_id}", json={"asignadoA": fer.id})
        assert r.status_code == 422 and "agencia externa" in r.json()["detail"]
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, tarea_id)
            assert (t.para, t.agencia, t.asignado_a_id) == ("tienda", None, d.aprob2.id)
            assert await s.get(CalendarioEntrega, tarea_id) is None
        assert await _avisos(d, fer, tarea_id) == []

        # Lo de una agencia de afuera lo carga alguien de Tienda: tampoco.
        fuera = f"ta-rf-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": fuera, "tipo": "mailing", "opciones": ["Físico (impreso)"], "detalles": {"paginas": 16},
            "para": "fuera", "agencia": "Estudio Afuera", "asignadoA": d.lucia.id})
        assert r.status_code == 201, r.text
        r = await lider.patch(f"/calendario/tareas/{fuera}", json={"asignadoA": fer.id})
        assert r.status_code == 422
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, fuera)
            assert (t.para, t.agencia, t.asignado_a_id) == ("fuera", "Estudio Afuera", d.lucia.id)

        # En una plantilla, lo mismo; y una vieja con alguien de la agencia
        # fijo crea esa tarea sin asignar (no una pieza de la agencia).
        r = await lider.put(f"/calendario/plantillas/pl-r-{d.sufijo}", json={
            "mundo": MUNDO, "nombre": "Mega", "tareas": [
                {"id": "t1", "titulo": "Brief", "ancla": "inicio", "dias": -3, "asignadoA": fer.id}]})
        assert r.status_code == 422 and "agencia externa" in r.json()["detail"]
        async with d.Sesion() as s:
            s.add(CalendarioPlantilla(id=f"pl-vieja-{d.sufijo}", mundo=MUNDO, nombre="Vieja", creado_por_id=d.lider.id,
                                      tareas=[{"id": "t1", "titulo": "Brief viejo", "asignadoA": fer.id},
                                              {"id": "t2", "titulo": "Push", "tipo": "push", "para": "agencia",
                                               "agencia": "disenadores"}]))
            await s.commit()
        ids = {"t1": f"ta-pv1-{d.sufijo}", "t2": f"ta-pv2-{d.sufijo}"}
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/plantilla", json={
            "plantillaId": f"pl-vieja-{d.sufijo}", "ids": ids})
        assert r.status_code == 201, r.text
        assert (r.json()["sinAsignar"], r.json()["tarjetas"]) == (1, 1)
        async with d.Sesion() as s:
            t1, t2 = await s.get(CalendarioTarea, ids["t1"]), await s.get(CalendarioTarea, ids["t2"])
            assert (t1.para, t1.agencia, t1.asignado_a_id) == ("tienda", None, None)
            # La pieza, con la agencia como ya está escrita.
            assert (t2.para, t2.agencia) == ("agencia", "Diseñadores")

        # Una pieza de su agencia sí puede quedar a nombre de alguien de ella.
        pieza = f"ta-rp-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": pieza, "tipo": "push", "para": "agencia", "agencia": "Diseñadores"})
        assert r.status_code == 201, r.text
        r = await lider.patch(f"/calendario/tareas/{pieza}", json={"asignadoA": fer.id})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            t = await s.get(CalendarioTarea, pieza)
            assert (t.para, t.agencia, t.asignado_a_id) == ("agencia", "Diseñadores", fer.id)
    correr(prueba)


def test_copiar_la_accion_no_le_deja_una_tarea_de_tienda_a_alguien_de_una_agencia():
    """Revisión del 19/11/2026: la tarea de Tienda la llevaba alguien que
    después pasó a ser de una agencia (Diseñadores, una agencia externa).
    Copiar la acción la hacía nacer a su nombre, con su aviso y su tarjeta,
    como si fuera una pieza de la agencia. Ahora la copia sale sin
    responsable, como al aplicar una plantilla, y la respuesta lo cuenta. La
    pieza de la agencia sí sigue a nombre de alguien de ella."""
    async def prueba(d):
        lider, promo = Cliente(d.http, d.lider), Cliente(d.http, d.promo)
        fer = await _persona(d, "Fer Disenia", externo=True, empresa="Diseñadores")
        ids = {"brief": f"ta-cb-{d.sufijo}", "pieza": f"ta-cp-{d.sufijo}", "fuera": f"ta-cf-{d.sufijo}",
               "agencia": f"ta-ca-{d.sufijo}"}
        for cuerpo in (
            {"id": ids["brief"], "titulo": "Brief del Ciberlunes", "asignadoA": d.aprob2.id},
            {"id": ids["pieza"], "tipo": "banners", "opciones": ["Header"], "para": "tienda", "asignadoA": d.aprob2.id},
            {"id": ids["fuera"], "tipo": "mailing", "opciones": ["Físico (impreso)"], "detalles": {"paginas": 16},
             "para": "fuera", "agencia": "Estudio Afuera", "asignadoA": d.aprob2.id},
            {"id": ids["agencia"], "tipo": "push", "para": "agencia", "agencia": "Diseñadores", "asignadoA": fer.id},
        ):
            r = await lider.post(f"/calendario/barras/{d.ciber.id}/tareas", json=cuerpo)
            assert r.status_code == 201, r.text
        # Quien las llevaba se pasa a Diseñadores.
        r = await promo.patch(f"/admin/users/{d.aprob2.id}/externo", json={"es_externo": True, "empresa": "Diseñadores"})
        assert r.status_code == 200, r.text

        copia = f"br-cx-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/copiar", json={
            "id": copia, "desde": (d.hoy + timedelta(days=20)).isoformat(), "nombre": f"Hot Sale {d.sufijo}"})
        assert r.status_code == 201, r.text
        assert r.json()["sinResponsable"] == 3
        async with d.Sesion() as s:
            copiadas = (await s.execute(select(CalendarioTarea).where(CalendarioTarea.barra_id == copia))).scalars().all()
        por_tipo = {(t.tipo, t.para): t for t in copiadas}
        assert len(por_tipo) == 4
        assert por_tipo[(None, "tienda")].asignado_a_id is None
        assert por_tipo[("banners", "tienda")].asignado_a_id is None and por_tipo[("banners", "tienda")].agencia is None
        assert por_tipo[("mailing", "fuera")].asignado_a_id is None
        assert por_tipo[("mailing", "fuera")].agencia == "Estudio Afuera"
        pieza_de_la_agencia = por_tipo[("push", "agencia")]
        assert (pieza_de_la_agencia.agencia, pieza_de_la_agencia.asignado_a_id) == ("Diseñadores", fer.id)
        # A la cuenta de la agencia no le llegó nada de lo de Tienda, ni lo ve en su tablero.
        de_tienda = [t.id for t in copiadas if t.para != "agencia"]
        for tarea_id in de_tienda:
            assert await _avisos(d, d.aprob2, tarea_id) == []
            assert await _tarjeta(Cliente(d.http, d.aprob2), tarea_id) is None
        # La de la agencia, sí: es suya (de Diseñadores).
        assert await _tarjeta(Cliente(d.http, d.aprob2), pieza_de_la_agencia.id) is not None
    correr(prueba)


def test_copiar_la_accion_saca_de_los_avisos_a_quien_ahora_es_de_una_agencia():
    """Revisión del 19/11/2026: los avisos son internos (al configurarlos no
    se puede elegir una cuenta externa), pero quien estaba en uno y después
    pasó a ser de una agencia (Diseñadores, una agencia externa) seguía
    abriendo el mundo y se copiaba en el aviso de la acción nueva. Ahora sale,
    y la respuesta lo cuenta con los demás que salen de los avisos. El aviso
    que se queda sin nadie no se copia."""
    async def prueba(d):
        lider, promo = Cliente(d.http, d.lider), Cliente(d.http, d.promo)
        for aviso_id, destinatarios in ((f"av-cx1-{d.sufijo}", [d.aprob2.id, d.lucia.id]),
                                        (f"av-cx2-{d.sufijo}", [d.aprob2.id])):
            r = await lider.post(f"/calendario/barras/{d.ciber.id}/avisos", json={
                "id": aviso_id, "diasAntes": 10, "destinatarios": destinatarios})
            assert r.status_code == 201, r.text
        # La persona de los avisos se pasa a Diseñadores: sigue abriendo el mundo.
        r = await promo.patch(f"/admin/users/{d.aprob2.id}/externo", json={"es_externo": True, "empresa": "Diseñadores"})
        assert r.status_code == 200, r.text

        copia = f"br-cav-{d.sufijo}"
        r = await lider.post(f"/calendario/barras/{d.ciber.id}/copiar", json={
            "id": copia, "desde": (d.hoy + timedelta(days=20)).isoformat(), "nombre": f"Hot Sale {d.sufijo}"})
        assert r.status_code == 201, r.text
        assert (r.json()["destinatariosQuitados"], r.json()["avisosSinNadie"]) == (2, 1), r.json()
        assert r.json()["copiadas"]["avisos"] == 1
        async with d.Sesion() as s:
            avisos = (await s.execute(select(CalendarioAviso).where(CalendarioAviso.barra_id == copia))).scalars().all()
        assert [a.destinatarios for a in avisos] == [[d.lucia.id]]
        # Los de la acción original quedan como estaban: la copia no los toca.
        async with d.Sesion() as s:
            original = await s.get(CalendarioAviso, f"av-cx1-{d.sufijo}")
        assert original.destinatarios == [d.aprob2.id, d.lucia.id]
    correr(prueba)


# ---------------------------------------------------------------------------
# Mi agenda (0074): el calendario de cada persona, solo para ella
# ---------------------------------------------------------------------------

_ICS_UNO = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:uno@prueba
DTSTART;TZID=America/Montevideo:%(dia)sT100000
DTEND;TZID=America/Montevideo:%(dia)sT103000
SUMMARY:Daily de marketing
END:VEVENT
END:VCALENDAR
"""


def _ics(d, titulo="Daily de marketing"):
    return (_ICS_UNO % {b"dia": d.hoy.strftime("%Y%m%d").encode()}).replace(b"Daily de marketing", titulo.encode())


def test_mi_agenda_se_conecta_se_ve_y_es_solo_de_su_duenio(monkeypatch):
    from app.core.security import decrypt_token
    from app.models.agenda import AgendaExterna
    from app.services import agenda_externa

    pedidos: list[str] = []
    respuesta = {"datos": b""}

    async def bajar(url):
        pedidos.append(url)
        if isinstance(respuesta["datos"], Exception):
            raise respuesta["datos"]
        return respuesta["datos"]

    monkeypatch.setattr(agenda_externa, "bajar", bajar)

    async def prueba(d):
        respuesta["datos"] = _ics(d)
        lucia, lider = Cliente(d.http, d.lucia), Cliente(d.http, d.lider)
        r = await lucia.get("/calendario/mi-agenda")
        assert r.status_code == 200 and r.json() == {"conectada": False, "leidaEl": None, "error": None, "eventos": []}

        r = await lucia.put("/calendario/mi-agenda", json={"url": " webcal://calendar.google.com/privado/basic.ics "})
        assert r.status_code == 200, r.text
        assert pedidos == ["https://calendar.google.com/privado/basic.ics"]
        cuerpo = r.json()
        assert cuerpo["conectada"] and cuerpo["error"] is None and cuerpo["leidaEl"]
        assert [e["titulo"] for e in cuerpo["eventos"]] == ["Daily de marketing"]
        # El link se guarda cifrado y nunca vuelve al navegador.
        assert "calendar.google.com" not in r.text
        async with d.Sesion() as s:
            fila = await s.get(AgendaExterna, d.lucia.id)
            assert "calendar.google.com" not in fila.url_cifrada
            assert decrypt_token(fila.url_cifrada) == "https://calendar.google.com/privado/basic.ics"

        # Es de ella: otra persona no la ve (no hay forma de pedir la de otro).
        assert (await lider.get("/calendario/mi-agenda")).json()["conectada"] is False

        # Recién leída: mirarla no vuelve a pedir el link.
        assert (await lucia.get("/calendario/mi-agenda")).json()["eventos"] == cuerpo["eventos"]
        assert len(pedidos) == 1

        # Pasaron 15 minutos: al mirarla se relee y trae lo que agregó.
        async def envejecer():
            async with d.Sesion() as s:
                fila = await s.get(AgendaExterna, d.lucia.id)
                fila.leida_at = datetime.now(timezone.utc) - timedelta(minutes=20)
                await s.commit()

        await envejecer()
        respuesta["datos"] = _ics(d, "Comite de precios")
        r = await lucia.get("/calendario/mi-agenda")
        assert len(pedidos) == 2 and [e["titulo"] for e in r.json()["eventos"]] == ["Comite de precios"]

        # Si el link deja de andar, quedan los eventos de antes con el motivo.
        await envejecer()
        respuesta["datos"] = agenda_externa.AgendaInvalida("El calendario no se pudo leer (el servidor contestó 404).")
        r = await lucia.get("/calendario/mi-agenda")
        assert [e["titulo"] for e in r.json()["eventos"]] == ["Comite de precios"]
        assert "404" in r.json()["error"]

        # "Actualizar" relee aunque esté recién leída.
        respuesta["datos"] = _ics(d, "Reunion nueva")
        r = await lucia.post("/calendario/mi-agenda/actualizar")
        assert r.status_code == 200 and r.json()["error"] is None
        assert [e["titulo"] for e in r.json()["eventos"]] == ["Reunion nueva"]

        r = await lucia.delete("/calendario/mi-agenda")
        assert r.status_code == 200 and r.json()["conectada"] is False
        assert (await lucia.get("/calendario/mi-agenda")).json()["conectada"] is False
        async with d.Sesion() as s:
            assert await s.get(AgendaExterna, d.lucia.id) is None
        # Actualizar sin agenda no hace nada.
        assert (await lucia.post("/calendario/mi-agenda/actualizar")).json()["conectada"] is False
    correr(prueba)


def test_mi_agenda_un_link_que_no_sirve_se_avisa_y_no_se_guarda(monkeypatch):
    from app.models.agenda import AgendaExterna
    from app.services import agenda_externa

    async def bajar(url):
        return b"<html><body>Iniciar sesion</body></html>"

    monkeypatch.setattr(agenda_externa, "bajar", bajar)

    async def prueba(d):
        lucia = Cliente(d.http, d.lucia)
        for url, motivo in (("http://calendar.google.com/x.ics", "https"),
                            ("https://outlook.office365.com/owa/calendar/x/calendar.html", "calendario")):
            r = await lucia.put("/calendario/mi-agenda", json={"url": url})
            assert r.status_code == 422, r.text
            assert motivo in r.json()["detail"]
        async with d.Sesion() as s:
            assert await s.get(AgendaExterna, d.lucia.id) is None
    correr(prueba)


def test_el_equipo_mueve_la_tarjeta_libre_como_trello():
    """Ivan (18/11/2026): "¿por qué en el tablero no puedo mover a esperando
    feedback o finalizado?". Eligió "libre, como Trello": el equipo de Tienda
    lleva la tarjeta a cualquier columna; la agencia, con sus reglas. Moverla
    a mano no entrega ni decide nada, y lo próximo que pasa de verdad (una
    entrega) vuelve a mandar."""
    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lucia)
        a1, lucia, marca = Cliente(d.http, d.a1), Cliente(d.http, d.lucia), Cliente(d.http, d.aprob2)
        mover = lambda c, desde, a: c.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": desde, "a": a})  # noqa: E731

        async def entrega():
            async with d.Sesion() as s:
                return await s.get(CalendarioEntrega, tarea_id)

        # El equipo ve todas las columnas para moverla; la agencia, las suyas.
        assert set((await _tarjeta(marca, tarea_id))["puedo"]["mover"]) == {"en-proceso", "esperando", "finalizado", "archivado"}
        assert "finalizado" not in (await _tarjeta(a1, tarea_id))["puedo"]["mover"]

        # A Esperando feedback, a mano: sin entregar nada. La agencia igual entrega.
        r = await mover(marca, "ingresado", "esperando")
        assert r.status_code == 200 and r.json()["columna"] == "esperando" and r.json()["accion"] == "a-mano", r.text
        assert (await entrega()).columna_manual == "esperando"
        assert await _estado(d, tarea_id) == "en-proceso"
        assert (await _tarjeta(a1, tarea_id))["puedo"]["entregar"] is True
        # Entrega de verdad: vuelve a mandar lo que dicen las entregas.
        assert (await _entregar_link(a1, tarea_id, f"ve-l1-{d.sufijo}")).status_code == 201
        assert (await entrega()).columna_manual is None
        assert (await _tarjeta(lucia, tarea_id))["columna"] == "esperando"

        # Quien no decide la vuelve a En proceso a mano (sin pedir cambios)...
        r = await mover(marca, "esperando", "en-proceso")
        assert r.status_code == 200 and r.json()["columna"] == "en-proceso" and r.json()["accion"] == "a-mano", r.text
        # ...y la da por terminada: queda aprobada y la tarea, hecha.
        r = await mover(marca, "en-proceso", "finalizado")
        assert r.status_code == 200 and r.json()["columna"] == "finalizado", r.text
        e = await entrega()
        assert e.momento == "aprobada" and e.finalizada_at is not None and e.columna_manual is None
        assert await _estado(d, tarea_id) == "hecha"
        # De Finalizado a Ingresado: vuelve a lo que dicen sus entregas, en Ingresado.
        r = await mover(lucia, "finalizado", "ingresado")
        assert r.status_code == 200 and r.json()["columna"] == "ingresado", r.text
        e = await entrega()
        assert e.momento == "revision" and e.columna_manual == "ingresado"
        assert await _estado(d, tarea_id) == "pendiente"
        t = await _tarjeta(a1, tarea_id)
        assert t["columna"] == "ingresado"
        # La agencia, con sus reglas: no la finaliza ni la archiva.
        assert (await mover(a1, "ingresado", "finalizado")).status_code == 403
        assert (await mover(a1, "ingresado", "archivado")).status_code == 403
        # Y el equipo la puede volver a dar por terminada desde ahí.
        r = await lucia.post(f"/calendario/tareas/{tarea_id}/mover", json={"desde": "ingresado", "a": "finalizado"})
        assert r.status_code == 200 and r.json()["columna"] == "finalizado", r.text
    correr(prueba)


def test_redexpres_nace_con_lanzar_y_le_avisa_a_todo_el_equipo():
    """Ivan (18/11/2026): cada acción de Redexpres nace con la tarea Lanzar (60
    días antes) y sus avisos a todo el equipo del mundo, a los 60 y a los 30.
    Cargada con menos tiempo, el aviso sale en el momento (una vez). Desde el
    20/11/2026 el Cierre es manual: no se crea ni avisa solo."""
    async def prueba(d):
        from app.services import calendario_avisos
        hoy = d.hoy
        async with d.Sesion() as s:
            def persona(nombre, permisos, mundos=("redexpres",)):
                u = User(
                    email=f"{nombre.lower().replace(' ', '.')}.{d.sufijo}@prueba-redex.test", full_name=nombre,
                    hashed_password=_clave(), permissions=list(permisos), mundos=list(mundos), is_active=True,
                    is_superuser=False, es_externo=False, empresa=None, calendario_alcance=alcance.por_defecto(False),
                    must_change_password=False, password_changed_at=datetime.now(timezone.utc),
                )
                s.add(u)
                return u
            valen = persona("Valen Redex", ("calendario.view", "calendario.edit", "calendario.pedidos"))
            otra = persona("Otra Redex", ("calendario.view", "calendario.edit"))
            mira = persona("Solo Mira Redex", ("calendario.view",))
            de_ti = persona("De Tienda Nomas", ("calendario.view", "calendario.edit"), mundos=("tienda_inglesa",))
            await s.commit()
        cv = Cliente(d.http, valen)

        async def crear(cliente, id_, banda, dias, mundo="redexpres"):
            return await cliente.post("/calendario/barras", json={
                "id": id_, "mundo": mundo, "seccion": "comercial", "banda": banda, "nombre": f"Accion {id_}",
                "desde": (hoy + timedelta(days=dias)).isoformat(), "hasta": (hoy + timedelta(days=dias + 5)).isoformat(),
            })

        async def de(barra_id):
            async with d.Sesion() as s:
                tareas = {t.titulo: t for t in (await s.execute(
                    select(CalendarioTarea).where(CalendarioTarea.barra_id == barra_id))).scalars()}
                avisos = sorted((a.control, a.dias_antes) for a in (await s.execute(
                    select(CalendarioAviso).where(CalendarioAviso.barra_id == barra_id))).scalars())
            return tareas, avisos

        async def avisos_de(usuario, barra_id):
            async with d.Sesion() as s:
                return [n.mensaje for n in (await s.execute(select(Notificacion).where(
                    Notificacion.user_id == usuario.id, Notificacion.origen_ref.startswith(f"{barra_id}:"),
                ).order_by(Notificacion.id))).scalars()]

        # 1. Con tiempo: la tarea anclada y los dos avisos; todavía nadie recibe nada.
        con_tiempo = f"br-rx-t-{d.sufijo}"
        r = await crear(cv, con_tiempo, "ESPECIAL - CM", 100)
        assert r.status_code == 201 and r.json().get("recargar") is True, r.text
        tareas, avisos = await de(con_tiempo)
        assert set(tareas) == {"Lanzar"}  # el Cierre lo crea Valentina a mano
        assert tareas["Lanzar"].vence == hoy + timedelta(days=40) and tareas["Lanzar"].ancla == "inicio"
        assert avisos == [("lanzar", 30), ("lanzar", 60)]
        assert await avisos_de(otra, con_tiempo) == []
        # La ficha los muestra como controles.
        datos = (await cv.get("/calendario/datos", params={"mundo": "redexpres"})).json()
        accion = next(b for b in datos["barras"] if b["id"] == con_tiempo)
        assert sorted(a.get("control") for a in accion["avisos"]) == ["lanzar", "lanzar"]

        # 2. Tarde (faltan 20 días): vence hoy y sale UN Lanzar, a todo el equipo.
        tarde = f"br-rx-l-{d.sufijo}"
        assert (await crear(cv, tarde, "MAILING - 16 PAG EL PAIS", 20)).status_code == 201
        tareas, _ = await de(tarde)
        assert tareas["Lanzar"].vence == hoy and tareas["Lanzar"].ancla is None and "Cierre" not in tareas
        for u in (valen, otra):
            mensajes = await avisos_de(u, tarde)
            assert [m.split(":")[0] for m in mensajes] == ["Lanzar"], mensajes
        assert await avisos_de(mira, tarde) == [] and await avisos_de(de_ti, tarde) == []
        # Otra vuelta del loop ese día: nada más.
        async with d.Sesion() as s:
            await calendario_avisos.revisar_avisos(s, hoy=hoy, barra_id=tarde)
        assert len(await avisos_de(otra, tarde)) == 1

        # 3. Faltan 45: Lanzar ya y, a los 30, el segundo Lanzar. A los 28, nada (sin Cierre).
        medio = f"br-rx-m-{d.sufijo}"
        assert (await crear(cv, medio, "TÁCTICO (x LOCAL) CM", 45)).status_code == 201
        assert [m.split(":")[0] for m in await avisos_de(otra, medio)] == ["Lanzar"]
        desde = hoy + timedelta(days=45)

        async def loop_el_dia(dia):
            """Una vuelta del loop "ese día": lo que sale queda con esa fecha
            (si no, quedaría con la de hoy y la vuelta siguiente lo vería viejo)."""
            async with d.Sesion() as s:
                antes = (await s.execute(select(func.coalesce(func.max(Notificacion.id), 0)))).scalar_one()
                await calendario_avisos.revisar_avisos(s, hoy=dia, barra_id=medio)
            async with d.Sesion() as s:
                await s.execute(update(Notificacion).where(Notificacion.id > antes).values(
                    created_at=datetime(dia.year, dia.month, dia.day, 15, tzinfo=timezone.utc)))
                await s.commit()

        await loop_el_dia(desde - timedelta(days=30))
        assert [m.split(":")[0] for m in await avisos_de(otra, medio)] == ["Lanzar", "Lanzar"]
        await loop_el_dia(desde - timedelta(days=28))
        await loop_el_dia(desde - timedelta(days=10))
        assert [m.split(":")[0] for m in await avisos_de(otra, medio)] == ["Lanzar", "Lanzar"]

        # El Cierre lo carga Valentina a mano, como cualquier tarea, con la fecha que elija.
        r = await cv.post(f"/calendario/barras/{medio}/tareas", json={
            "id": f"ta-cierre-{d.sufijo}", "titulo": "Cierre", "vence": (desde - timedelta(days=20)).isoformat()})
        assert r.status_code == 201, r.text
        tareas, avisos = await de(medio)
        assert tareas["Cierre"].vence == desde - timedelta(days=20) and avisos == [("lanzar", 30), ("lanzar", 60)]

        # 4. Bombas (semanal) y Tienda Inglesa: sin controles.
        bombas = f"br-rx-b-{d.sufijo}"
        r = await crear(cv, bombas, "BOMBAS", 90)
        assert r.status_code == 201 and "recargar" not in r.json()
        assert await de(bombas) == ({}, [])
        ti = f"br-ti-c-{d.sufijo}"
        assert (await crear(Cliente(d.http, d.lider), ti, "MEGA EVENTO", 90, mundo=MUNDO)).status_code == 201
        assert await de(ti) == ({}, [])

        # 5. Las piezas de Valentina, solo en Redexpres.
        r = await cv.post(f"/calendario/barras/{con_tiempo}/tareas", json={
            "id": f"ta-imp-{d.sufijo}", "titulo": "Imprenta", "tipo": "imprenta", "para": "tienda", "asignadoA": valen.id})
        assert r.status_code == 201, r.text
        r = await Cliente(d.http, d.lucia).post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-imp2-{d.sufijo}", "titulo": "Imprenta", "tipo": "imprenta", "para": "tienda", "asignadoA": d.lucia.id})
        assert r.status_code == 422, r.text
    correr(prueba)


def test_un_super_fds_no_lleva_controles():
    """Ivan (20/11/2026): "FDS no va a existir más". Un Super FDS (de los que
    quedaron hasta noviembre) no lleva tareas ni avisos automáticos, ni al
    crearlo ni al moverlo."""
    async def prueba(d):
        async with d.Sesion() as s:
            valen = User(
                email=f"valen.fds.{d.sufijo}@prueba-redex.test", full_name="Valen FDS", hashed_password=_clave(),
                permissions=["calendario.view", "calendario.edit", "calendario.pedidos"], mundos=["redexpres"],
                is_active=True, is_superuser=False, es_externo=False, empresa=None,
                calendario_alcance=alcance.por_defecto(False), must_change_password=False,
                password_changed_at=datetime.now(timezone.utc),
            )
            s.add(valen)
            await s.commit()
        cv = Cliente(d.http, valen)
        fds = f"br-fds-{d.sufijo}"
        desde = d.hoy + timedelta(days=90)
        r = await cv.post("/calendario/barras", json={
            "id": fds, "mundo": "redexpres", "seccion": "comercial", "banda": "Super FDS", "nombre": "Super FDS",
            "desde": desde.isoformat(), "hasta": (desde + timedelta(days=3)).isoformat()})
        assert r.status_code == 201 and "recargar" not in r.json(), r.text
        r = await cv.patch(f"/calendario/barras/{fds}", json={
            "desde": (desde + timedelta(days=7)).isoformat(), "hasta": (desde + timedelta(days=10)).isoformat()})
        assert r.status_code == 200 and "recargar" not in r.json(), r.text
        async with d.Sesion() as s:
            assert (await s.execute(select(CalendarioTarea).where(CalendarioTarea.barra_id == fds))).first() is None
            assert (await s.execute(select(CalendarioAviso).where(CalendarioAviso.barra_id == fds))).first() is None
    correr(prueba)


def test_eliminar_un_usuario():
    """Ivan (20/11/2026): "necesito que podamos eliminar un usuario creado".
    Se va la cuenta; lo que hizo queda sin su nombre; sale de los avisos; y
    no se puede si aprueba una entrega en curso."""
    async def prueba(d):
        from app.models.audit_log import AuditLog
        promo = Cliente(d.http, d.promo)
        valeria = await _persona(d, "Valeria Borrable", permisos=("calendario.view", "calendario.edit", "calendario.pedidos"))
        otra = await _persona(d, "Otra Que Queda", permisos=("calendario.view",))

        # Tiene historia: creó una tarea y es destinataria de dos avisos.
        tarea = f"ta-val-{d.sufijo}"
        r = await Cliente(d.http, valeria).post(f"/calendario/barras/{d.ciber.id}/tareas", json={"id": tarea, "titulo": "Suya"})
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            s.add(CalendarioAviso(id=f"av-sola-{d.sufijo}", barra_id=d.ciber.id, dias_antes=10, destinatarios=[valeria.id]))
            s.add(CalendarioAviso(id=f"av-dos-{d.sufijo}", barra_id=d.ciber.id, dias_antes=10, destinatarios=[valeria.id, otra.id]))
            await s.commit()

        # Aprueba una entrega en curso: no se puede.
        suya, _ = await _pedir_banners(d, d.lider)
        r = await Cliente(d.http, d.lider).put(f"/calendario/tareas/{suya}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [valeria.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text
        r = await d.http.delete(f"{API}/admin/users/{valeria.id}", headers=promo.headers)
        assert r.status_code == 409 and "aprueba 1 entrega" in r.json()["detail"], r.text
        r = await Cliente(d.http, d.lider).put(f"/calendario/tareas/{suya}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.lider.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text

        # Ni a uno mismo, ni quien no administra usuarios.
        assert (await d.http.delete(f"{API}/admin/users/{d.promo.id}", headers=promo.headers)).status_code == 403
        assert (await d.http.delete(f"{API}/admin/users/{valeria.id}", headers=Cliente(d.http, d.lucia).headers)).status_code == 403

        r = await d.http.delete(f"{API}/admin/users/{valeria.id}", headers=promo.headers)
        assert r.status_code == 204, r.text
        assert (await d.http.delete(f"{API}/admin/users/{valeria.id}", headers=promo.headers)).status_code == 404
        async with d.Sesion() as s:
            assert await s.get(User, valeria.id) is None
            t = await s.get(CalendarioTarea, tarea)
            assert t is not None and t.creado_por_id is None  # la tarea queda, sin su nombre
            assert await s.get(CalendarioAviso, f"av-sola-{d.sufijo}") is None  # se quedó sin nadie
            assert (await s.get(CalendarioAviso, f"av-dos-{d.sufijo}")).destinatarios == [otra.id]
            log = (await s.execute(select(AuditLog).where(
                AuditLog.action == "admin.user.delete", AuditLog.resource_id == str(valeria.id)))).scalar_one()
            assert log.user_id == d.promo.id and log.details["nombre"] == "Valeria Borrable"
    correr(prueba)


def test_eliminar_varias_cuentas_de_una_vez():
    """Ivan (20/11/2026): "seleccionar y seleccionar todo en usuarios, para
    poder agarrar a más de uno y volarlos". Cada una con sus reglas: las que
    no se pueden quedan, con su motivo, y las demás se van igual."""
    async def prueba(d):
        promo = Cliente(d.http, d.promo)
        una = await _persona(d, "Una Para Borrar")
        otra = await _persona(d, "Otra Para Borrar")
        aprueba = await _persona(d, "Aprueba Algo", permisos=("calendario.view", "calendario.edit"))
        suya, _ = await _pedir_banners(d, d.lider)
        r = await Cliente(d.http, d.lider).put(f"/calendario/tareas/{suya}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [aprueba.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text

        ids = [una.id, otra.id, aprueba.id, d.promo.id, 999_999_999]
        r = await Cliente(d.http, d.lucia).post("/admin/users/eliminar", json={"ids": ids})
        assert r.status_code == 403
        r = await promo.post("/admin/users/eliminar", json={"ids": ids})
        assert r.status_code == 200, r.text
        assert sorted(r.json()["eliminados"]) == sorted([una.id, otra.id])
        motivos = {n["id"]: n["motivo"] for n in r.json()["noSePudieron"]}
        assert set(motivos) == {aprueba.id, d.promo.id}
        assert "aprueba 1 entrega" in motivos[aprueba.id] and "propia" in motivos[d.promo.id]
        async with d.Sesion() as s:
            assert await s.get(User, una.id) is None and await s.get(User, otra.id) is None
            assert await s.get(User, aprueba.id) is not None
    correr(prueba)


def test_los_avisos_salen_por_mail_a_quien_los_quiere(monkeypatch):
    """Ivan (18/11/2026): los avisos de la campanita también por mail, al
    momento, y cada uno los apaga en su perfil. Menos los del tablero, que
    quedan solo en la campanita (19/11/2026: tope de 3.000 mails por mes)."""
    from app.services import avisos_por_mail as apm
    from app.services import email_service

    monkeypatch.setattr(apm, "_PAUSA_ENTRE_MAILS", 0)
    configurado = {"si": True}
    monkeypatch.setattr(email_service, "email_configurado", lambda: configurado["si"])
    enviados: list[tuple[str, str]] = []
    falla = {"si": False}

    async def enviar(to, subject, html, plain):
        if falla["si"]:
            raise RuntimeError("el proveedor no contesta")
        enviados.append((to, subject))

    async def prueba(d):
        # Un aviso del tablero: pedir una pieza le avisa a la agencia. Queda solo
        # en la campanita: nace sin mail pendiente.
        tarea_id, _ = await _pedir_banners(d, d.lucia)
        async with d.Sesion() as s:
            nuevos = (await s.execute(select(Notificacion).where(Notificacion.origen_ref.contains(tarea_id)))).scalars().all()
            assert nuevos and not any(n.mail_pendiente for n in nuevos)
            # Uno del tablero que hubiera quedado en la cola de antes del cambio: tampoco sale.
            s.add(Notificacion(user_id=d.lucia.id, tipo="calendario_entrega", mensaje="Del tablero", origen_tipo="calendario_entrega",
                               origen_ref=f"{d.ciber.id}:{tarea_id}:ve-x:hecha", mail_pendiente=True))
            # Uno a quien lo apagó, y uno viejo (de hace dos días).
            lider = await s.get(User, d.lider.id)
            lider.avisos_por_mail = False
            s.add(Notificacion(user_id=d.lider.id, tipo="calendario_aviso", mensaje="No le sale", origen_tipo="calendario_aviso", origen_ref=f"{d.ciber.id}:av-x"))
            viejo = Notificacion(user_id=d.lucia.id, tipo="calendario_aviso", mensaje="Viejo", origen_tipo="calendario_aviso", origen_ref=f"{d.ciber.id}:av-y")
            s.add(viejo)
            s.add(Notificacion(user_id=d.lucia.id, tipo="calendario_aviso", mensaje="Lanzar: Ciberlunes arranca en 60 días.", origen_tipo="calendario_aviso", origen_ref=f"{d.ciber.id}:av-z"))
            await s.flush()
            viejo.created_at = datetime.now(timezone.utc) - timedelta(days=2)
            await s.commit()

        async with d.Sesion() as s:
            salieron = await apm.mandar_pendientes(s, enviar=enviar)
        destinatarios = [t for t, _ in enviados]
        assert d.lucia.email in destinatarios and ("Lanzar: Ciberlunes arranca en 60 días.") in [a for _, a in enviados]
        assert d.lider.email not in destinatarios                     # lo apagó
        assert "Viejo" not in [a for _, a in enviados]                # de hace dos días
        assert "Del tablero" not in [a for _, a in enviados]          # el tablero: solo campanita
        assert salieron == len(enviados)
        async with d.Sesion() as s:
            assert (await s.execute(select(func.count()).select_from(Notificacion).where(
                Notificacion.mail_pendiente.is_(True)))).scalar_one() == 0
            enviada = (await s.execute(select(Notificacion).where(Notificacion.mensaje.like("Lanzar: Ciberlunes%")))).scalar_one()
            assert enviada.mail_enviado_at is not None

        # Si el proveedor falla, se reintenta (hasta 5 veces).
        async with d.Sesion() as s:
            s.add(Notificacion(user_id=d.lucia.id, tipo="calendario_aviso", mensaje="Reintento", origen_tipo="calendario_aviso", origen_ref=f"{d.ciber.id}:av-r"))
            await s.commit()
        falla["si"] = True
        for intento in range(1, 6):
            async with d.Sesion() as s:
                assert await apm.mandar_pendientes(s, enviar=enviar) == 0
            async with d.Sesion() as s:
                n = (await s.execute(select(Notificacion).where(Notificacion.mensaje == "Reintento"))).scalar_one()
                assert n.mail_intentos == intento and n.mail_pendiente is (intento < 5)

        # Sin servicio de mail configurado: no sale nada y no se acumula.
        falla["si"], configurado["si"] = False, False
        antes = len(enviados)
        async with d.Sesion() as s:
            s.add(Notificacion(user_id=d.lucia.id, tipo="calendario_aviso", mensaje="Sin mail", origen_tipo="calendario_aviso", origen_ref=f"{d.ciber.id}:av-s"))
            await s.commit()
        async with d.Sesion() as s:
            await apm.mandar_pendientes(s, enviar=enviar)
        assert len(enviados) == antes
        async with d.Sesion() as s:
            assert (await s.execute(select(Notificacion).where(Notificacion.mensaje == "Sin mail"))).scalar_one().mail_pendiente is False

        # Cada uno lo apaga (y lo prende) en su perfil.
        c = Cliente(d.http, d.lucia)
        assert (await c.get("/auth/me")).json()["avisos_por_mail"] is True
        r = await d.http.patch(f"{API}/auth/me/preferencias", json={"avisosPorMail": False}, headers=c.headers)
        assert r.status_code == 200 and r.json() == {"avisosPorMail": False}, r.text
        assert (await c.get("/auth/me")).json()["avisos_por_mail"] is False
    correr(prueba)
