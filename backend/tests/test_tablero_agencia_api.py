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
    from app.models.calendario import CalendarioBarra, CalendarioTarea
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
    # Lucía: del equipo, edita el calendario pero NO gestiona tareas (rol "Usuario").
    d.lucia = persona("Lucia Equipo", permisos=("calendario.view", "calendario.edit"))
    d.lider = persona("Lider Tareas", permisos=("calendario.view", "calendario.edit", "calendario.tareas"))
    d.aprob2 = persona("Marca Aprobadora")
    d.limitado = persona("Interno Limitado", permisos=("calendario.view", "calendario.edit"), alc="1m")
    d.sin_cal = persona("Interno Sin Calendario", permisos=("calendario.view", "calendario.edit"), alc="nada")
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
            assert (await c.get("/calendario/mis-tareas")).status_code == 403
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
        # Una tarjeta ajena de afuera de su alcance: no existe. Una que pidió
        # él (aunque la campaña quede fuera): sí.
        ajena, _ = await _pedir_banners(d, d.lucia)
        assert (await c.get(f"/calendario/tareas/{ajena}/entregas")).status_code == 404
        assert await _tarjeta(c, ajena) is None
        # No puede pedir piezas en una acción que no ve; en una que ve, sí.
        r = await c.post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-l-{d.sufijo}", "tipo": "totem", "para": "agencia", "agencia": f"Agencia Pampa {d.sufijo}"})
        assert r.status_code == 404
        propia, _ = await _pedir_banners(d, d.limitado, barra=d.ahora)
        assert (await c.get(f"/calendario/tareas/{propia}/entregas")).status_code == 200
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
        # Una tarea común para alguien de Tienda, Lucía no (es de quien lidera).
        r = await Cliente(d.http, d.lucia).post(f"/calendario/barras/{d.ciber.id}/tareas", json={
            "id": f"ta-c-{d.sufijo}", "titulo": "Común", "asignadoA": d.aprob2.id})
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
        propias = [t for t in r["tarjetas"] if t["tareaId"] in ids]
        # 25 archivadas: viajan las primeras 20 y se dice cuántas hay.
        assert len(propias) == 20 and all(t["columna"] == "archivado" for t in propias)
        assert r["archivadas"]["total"] >= 25 and r["archivadas"]["mostradas"] == 20
        # Liviana: ni historia ni marcas.
        assert "fases" not in propias[0] and "marcas" not in str(propias[0])
        mas = (await lucia.get("/calendario/entregas/archivadas", params={"mundo": MUNDO, "desde": 20})).json()
        assert {t["tareaId"] for t in mas["tarjetas"]} | {t["tareaId"] for t in propias} >= set(ids)
    correr(prueba)
