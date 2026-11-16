"""La agencia adentro, de punta a punta: la API con una base de verdad (0068).

Para CADA ruta por donde sale algo del calendario se fija que una cuenta
externa no ve nada fuera de su ventana ni de otros (otra agencia, el equipo).
Si se saca el filtro de una ruta, su prueba falla: los datos de prueba tienen
a propósito, en el mismo mundo, acciones del mes pasado, del que viene y de
dentro de tres meses, tareas suyas fuera de la ventana, tareas del equipo y de
otra agencia, avisos, plantillas, notas internas y pedidos de fotos.

Necesita una base Postgres en la última migración: se le pasa en
TEST_DATABASE_URL (por ejemplo, la copia local de prueba). Sin eso, se saltea
(el CI no tiene base: ver conftest.py). Todo corre adentro de una transacción
que se deshace al final: la base queda como estaba.
"""
import asyncio
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")

if URL:
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.api.routes.calendario_ical import firma_del_link
    from app.core import externos
    from app.core.database import get_db
    from app.core.rate_limit import limiter
    from app.core.security import create_access_token, hash_password
    from app.main import app
    from app.models.calendario import (
        CalendarioAviso, CalendarioBarra, CalendarioPieza, CalendarioPlantilla, CalendarioTarea,
    )
    from app.models.colocacion import ColocacionPedido
    from app.models.entregas import (
        CalendarioDecision, CalendarioEntrega, CalendarioFase, CalendarioMarca, CalendarioVersion,
        CalendarioVersionImagen,
    )
    from app.models.notificacion import Notificacion
    from app.models.role import ALL_PERMISSIONS
    from app.models.user import User
    from app.services import calendario_consultas as cc
    from app.services.calendario_avisos import revisar_avisos

API = "/api/v1"
MUNDO = "tienda_inglesa"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
# Todo lo que una cuenta externa NO tiene que ver lleva una de estas marcas
# en el nombre: si aparece en una respuesta suya, se escapó algo.
PROHIBIDO = ("FUERA", "TRES MESES", "MES PASADO", "INTERNA", "OTRA AGENCIA", "NOTA INTERNA", "PLANTILLA")


# ---------------------------------------------------------------------------
# El escenario
# ---------------------------------------------------------------------------

class Datos:
    pass


_HASH: list[str] = []


def _clave() -> str:
    """El hash de una contraseña cualquiera, calculado una vez: nadie entra
    con contraseña acá (los tokens se arman directo) y bcrypt es lento a
    propósito."""
    if not _HASH:
        _HASH.append(hash_password("Clave-de-prueba-1"))
    return _HASH[0]


async def _sembrar(s) -> Datos:
    d = Datos()
    sufijo = uuid.uuid4().hex[:8]
    d.sufijo = sufijo
    hoy = externos.hoy_en_uruguay()
    v = externos.ventana_de_hoy()
    d.v = v
    ahora = datetime.now(timezone.utc)

    def persona(nombre, *, externo=False, empresa=None, superusuario=False, permisos=("calendario.view",)):
        u = User(
            email=f"{nombre.lower().replace(' ', '.')}.{sufijo}@prueba-externos.test", full_name=nombre,
            hashed_password=_clave(), permissions=list(permisos), mundos=[MUNDO],
            is_active=True, is_superuser=superusuario, es_externo=externo, empresa=empresa,
            must_change_password=False, password_changed_at=ahora,
        )
        s.add(u)
        return u

    d.promo = persona("Promo Jefa", superusuario=True, permisos=tuple(ALL_PERMISSIONS))
    d.aprob = persona("Aprobadora Marca")
    d.otro = persona("Otro INTERNA Persona")
    d.a1 = persona("Ana Pampa", externo=True, empresa="Agencia Pampa")
    d.a2 = persona("Beto Pampa", externo=True, empresa="agencia pampa")
    d.b1 = persona("Bruno OTRA AGENCIA", externo=True, empresa="Estudio Sur")
    await s.flush()

    def barra(clave, nombre, desde, hasta):
        b = CalendarioBarra(
            id=f"br-{clave}-{sufijo}", mundo=MUNDO, seccion="comercial", banda="MEGA EVENTO", carril=0,
            nombre=nombre, desde=desde, hasta=hasta, creado_por_id=d.promo.id,
        )
        s.add(b)
        return b

    un = timedelta(days=1)
    d.dentro = barra("dentro", "Accion DENTRO", v[0] + un, v[0] + 3 * un)
    d.borde = barra("borde", "Accion BORDE", v[1], v[1] + 10 * un)
    d.futuro = barra("futuro", "Accion FUERA FUTURO", v[1] + un, v[1] + 5 * un)
    d.tres = barra("tres", "Accion TRES MESES", hoy + 90 * un, hoy + 95 * un)
    d.pasado = barra("pasado", "Accion MES PASADO", v[0] - 10 * un, v[0] - un)
    await s.flush()

    s.add(CalendarioPieza(id=f"pz-d-{sufijo}", barra_id=d.dentro.id, area="fisico", formato="Cenefa", estado="pendiente"))
    s.add(CalendarioPieza(id=f"pz-f-{sufijo}", barra_id=d.tres.id, area="fisico", formato="Cenefa FUERA", estado="pendiente"))
    s.add(CalendarioAviso(id=f"av-{sufijo}", barra_id=d.dentro.id, dias_antes=3,
                          destinatarios=[d.aprob.id, d.a1.id], creado_por_id=d.promo.id))
    s.add(CalendarioPlantilla(id=f"pl-{sufijo}", mundo=MUNDO, nombre="PLANTILLA interna",
                              tareas=[{"id": "x", "titulo": "Brief"}], creado_por_id=d.promo.id))
    s.add(ColocacionPedido(barra_id=d.dentro.id, tipo_local="supermercado", limite=v[0] + 5 * un,
                           indicacion="Foto INTERNA de la góndola", creado_por_id=d.promo.id))

    def tarea(clave, barra_, titulo, asignado, *, parent=None, vence=None):
        t = CalendarioTarea(id=f"ta-{clave}-{sufijo}", barra_id=barra_.id, parent_id=parent, titulo=titulo,
                            asignado_a_id=asignado.id if asignado else None, vence=vence,
                            creado_por_id=d.promo.id)
        s.add(t)
        return t

    d.t_madre = tarea("madre", d.dentro, "Madre INTERNA de promo", d.aprob)
    await s.flush()
    d.t_mia = tarea("mia", d.dentro, "Afiche Black Friday", d.a1, parent=d.t_madre.id, vence=v[0] + 2 * un)
    d.t_ajena = tarea("ajena", d.dentro, "Tarea INTERNA del equipo", d.otro, vence=v[0] + 2 * un)
    d.t_b1 = tarea("b1", d.dentro, "Pieza de OTRA AGENCIA", d.b1, vence=v[0] + 2 * un)
    d.t_colega = tarea("colega", d.dentro, "Banner de mi colega", d.a2)
    d.t_futura = tarea("futura", d.tres, "Mi tarea de TRES MESES", d.a1, vence=hoy + 89 * un)
    d.t_pasada = tarea("pasada", d.pasado, "Mi tarea del MES PASADO", d.a1, vence=v[0] - 5 * un)
    d.t_fuera = tarea("fuera", d.futuro, "Mi tarea FUERA de la ventana", d.a1, vence=v[1] + 2 * un)
    await s.flush()

    # Entregas: la mía (devuelta con cambios, con nota interna), la de la
    # otra agencia (aprobada: cuenta para el retrabajo de ELLA), una mía fuera
    # de la ventana y una del equipo aprobada.
    async def entrega(t, subida_por, *, momento, estado_version, aprobadores, nota=None, comentario=None):
        s.add(CalendarioEntrega(tarea_id=t.id, tipo_pieza="banner", brief={"detalle": "Brief"},
                                aprobadores=aprobadores, momento=momento, ronda=1, creado_por_id=d.promo.id,
                                fase_actual_id=None if momento == "aprobada" else f"fa-{t.id}"))
        fase = CalendarioFase(id=f"fa-{t.id}", tarea_id=t.id, orden=0, nombre="Boceto",
                              estado="aprobada" if estado_version == "aprobada" else "en-curso",
                              aprobada_at=ahora if estado_version == "aprobada" else None)
        s.add(fase)
        await s.flush()
        version = CalendarioVersion(id=f"ve-{t.id}", fase_id=fase.id, tarea_id=t.id, ronda=1,
                                    subida_por_id=subida_por.id, estado=estado_version,
                                    decidida_at=ahora if estado_version != "revision" else None)
        s.add(version)
        await s.flush()
        imagen = CalendarioVersionImagen(id=f"im-{t.id}", version_id=version.id, orden=0, tipo_mime="image/jpeg",
                                         datos=JPEG, tipo_mime_miniatura="image/jpeg", miniatura=JPEG, tamano=len(JPEG))
        s.add(imagen)
        await s.flush()
        if estado_version != "revision":
            s.add(CalendarioDecision(version_id=version.id, aprobador_id=d.aprob.id, decidido_por_id=d.aprob.id,
                                     orden=0, decision="cambios" if estado_version == "cambios" else "aprobada",
                                     comentario=comentario, nota_interna=nota))
        marca = CalendarioMarca(id=f"mk-{t.id}", version_id=version.id, imagen_id=imagen.id, tarea_id=t.id,
                                numero=1, x=0.5, y=0.5, texto="Subí el logo", tipo="cambio", autor_id=d.aprob.id)
        s.add(marca)
        await s.flush()
        return version, imagen, marca

    d.v_mia, d.im_mia, d.mk_mia = await entrega(
        d.t_mia, d.a1, momento="cambios", estado_version="cambios", aprobadores=[d.aprob.id],
        nota="NOTA INTERNA: comercial no confirmó el precio", comentario="Más grande el logo")
    d.v_b1, d.im_b1, d.mk_b1 = await entrega(
        d.t_b1, d.b1, momento="aprobada", estado_version="aprobada", aprobadores=[d.otro.id])
    d.v_fuera, d.im_fuera, d.mk_fuera = await entrega(
        d.t_fuera, d.a1, momento="cambios", estado_version="cambios", aprobadores=[d.otro.id])
    d.v_ajena, _, _ = await entrega(
        d.t_ajena, d.otro, momento="aprobada", estado_version="aprobada", aprobadores=[d.aprob.id])

    # La campanita de la agencia: lo de su tarea en la ventana sí; lo demás no.
    for tipo, ref, texto in (
        ("calendario_tarea", f"{d.dentro.id}:{d.t_mia.id}", "Te asignaron el afiche"),
        ("calendario_tarea", f"{d.tres.id}:{d.t_futura.id}", "Tarea en Accion TRES MESES"),
        ("calendario_entrega", f"{d.futuro.id}:{d.t_fuera.id}:x:cambios", "Cambios en Accion FUERA FUTURO"),
        ("calendario_aviso", f"{d.dentro.id}:av", "Aviso INTERNA"),
        ("calendario_header", "2026-11:1-2", "Header INTERNA"),
        (None, None, "Precio INTERNA"),
    ):
        s.add(Notificacion(user_id=d.a1.id, tipo=tipo or "precio_baja", mensaje=texto, origen_tipo=tipo,
                           origen_ref=ref))
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
            d.http = http
            d.Sesion = Sesion
            await prueba(d)
    finally:
        limiter.enabled = limite_antes
        app.dependency_overrides.pop(get_db, None)
        await trans.rollback()
        await conn.close()
        await engine.dispose()


def _sin_prohibido(texto: str, ruta: str) -> None:
    for marca in PROHIBIDO:
        assert marca not in texto, f"{ruta}: se escapó «{marca}»: {texto[:600]}"


# ---------------------------------------------------------------------------
# El calendario
# ---------------------------------------------------------------------------

def test_datos_solo_la_ventana_y_sus_tareas():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        r = await a1.get("/calendario/datos", params={"mundo": MUNDO})
        assert r.status_code == 200, r.text
        datos = r.json()
        _sin_prohibido(r.text, "/calendario/datos")
        ids = {b["id"] for b in datos["barras"]}
        assert d.dentro.id in ids and d.borde.id in ids
        assert not ids & {d.futuro.id, d.tres.id, d.pasado.id}
        dentro = next(b for b in datos["barras"] if b["id"] == d.dentro.id)
        assert [t["id"] for t in dentro["tareas"]] == [d.t_mia.id]
        # La madre (del equipo) no viaja: su tarea queda suelta.
        assert dentro["tareas"][0]["parentId"] is None
        assert dentro["avisos"] == [] and "fotos" not in dentro
        assert datos["plantillas"] == []
        assert datos["opaca"] is True

        # Para el equipo, todo sigue igual.
        promo = await Cliente(d.http, d.promo).get("/calendario/datos", params={"mundo": MUNDO})
        ids_promo = {b["id"] for b in promo.json()["barras"]}
        assert {d.futuro.id, d.tres.id, d.pasado.id} <= ids_promo
    correr(prueba)


def test_la_revision_de_la_agencia_no_delata_cambios_fuera_de_su_ventana():
    async def prueba(d):
        a1, promo = Cliente(d.http, d.a1), Cliente(d.http, d.promo)
        primera = (await a1.get("/calendario/datos", params={"mundo": MUNDO})).json()
        rev = primera["rev"]
        global_rev = (await promo.get("/calendario/datos", params={"mundo": MUNDO})).json()["rev"]
        assert rev != global_rev  # no es el contador de todos
        assert (await a1.get("/calendario/datos", params={"mundo": MUNDO, "rev": rev})).json().get("sinCambios")

        # El equipo cambia algo FUERA de su ventana: para ella, sin cambios.
        r = await promo.patch(f"/calendario/barras/{d.tres.id}", json={"nombre": "Accion TRES MESES renombrada"})
        assert r.status_code == 200, r.text
        r = await promo.post(f"/calendario/barras/{d.tres.id}/tareas", json={"id": f"ta-n-{d.sufijo}", "titulo": "Otra"})
        assert r.status_code == 201, r.text
        sigue = (await a1.get("/calendario/datos", params={"mundo": MUNDO, "rev": rev})).json()
        assert sigue == {"rev": rev, "sinCambios": True, "opaca": True}
        # Lo mismo el tablero de entregas.
        tab = (await a1.get("/calendario/entregas", params={"mundo": MUNDO})).json()
        await promo.patch(f"/calendario/barras/{d.futuro.id}", json={"nombre": "Accion FUERA FUTURO 2"})
        assert (await a1.get("/calendario/entregas", params={"mundo": MUNDO, "rev": tab["rev"]})).json().get("sinCambios")

        # Y algo ADENTRO de su ventana sí lo ve.
        await promo.patch(f"/calendario/barras/{d.dentro.id}", json={"nombre": "Accion DENTRO cambiada"})
        nueva = (await a1.get("/calendario/datos", params={"mundo": MUNDO, "rev": rev})).json()
        assert not nueva.get("sinCambios") and nueva["rev"] != rev
        assert any(b["nombre"] == "Accion DENTRO cambiada" for b in nueva["barras"])
    correr(prueba)


def test_personas_solo_su_empresa_y_sus_aprobadores_sin_mail():
    async def prueba(d):
        r = await Cliente(d.http, d.a1).get("/calendario/personas", params={"mundo": MUNDO})
        assert r.status_code == 200, r.text
        ids = {p["id"] for p in r.json()}
        assert ids == {d.a1.id, d.a2.id, d.aprob.id}
        assert "@" not in r.text
        _sin_prohibido(r.text, "/calendario/personas")
        # El equipo ve a todos, y a los externos marcados con su empresa.
        todos = (await Cliente(d.http, d.promo).get("/calendario/personas", params={"mundo": MUNDO})).json()
        por_id = {p["id"]: p for p in todos}
        assert {d.a1.id, d.b1.id, d.otro.id, d.aprob.id} <= set(por_id)
        assert por_id[d.a1.id]["externo"] is True and por_id[d.a1.id]["empresa"] == "Agencia Pampa"
        assert "externo" not in por_id[d.aprob.id]
    correr(prueba)


def test_mis_tareas_solo_las_suyas_de_la_ventana():
    async def prueba(d):
        r = await Cliente(d.http, d.a1).get("/calendario/mis-tareas")
        assert r.status_code == 200, r.text
        assert [t["id"] for t in r.json()] == [d.t_mia.id]
        assert r.json()[0]["parentId"] is None
        _sin_prohibido(r.text, "/calendario/mis-tareas")
    correr(prueba)


def test_ubicar_una_accion_fuera_de_la_ventana_es_404():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        assert (await a1.get(f"/calendario/ubicar/{d.dentro.id}")).status_code == 200
        for b in (d.futuro, d.tres, d.pasado):
            r = await a1.get(f"/calendario/ubicar/{b.id}")
            assert r.status_code == 404
            # El mismo 404 que una acción que no existe.
            assert r.json() == (await a1.get("/calendario/ubicar/br-no-existe")).json()
        assert (await Cliente(d.http, d.promo).get(f"/calendario/ubicar/{d.tres.id}")).status_code == 200
    correr(prueba)


def test_el_link_de_outlook_solo_trae_la_ventana():
    async def prueba(d):
        r = await d.http.get(f"{API}/calendario/ical/{d.a1.id}/{firma_del_link(d.a1.id, 0)}.ics")
        assert r.status_code == 200, r.text
        assert "Accion DENTRO" in r.text and "Afiche Black Friday" in r.text
        _sin_prohibido(r.text, "ical")
        r_promo = await d.http.get(f"{API}/calendario/ical/{d.promo.id}/{firma_del_link(d.promo.id, 0)}.ics")
        assert "Accion TRES MESES" in r_promo.text
    correr(prueba)


def test_cambiar_el_estado_de_su_tarea_si_la_de_otro_o_fuera_no():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        r = await a1.patch(f"/calendario/tareas/{d.t_colega.id}", json={"estado": "en-proceso"})
        assert r.status_code == 403
        r = await a1.patch(f"/calendario/tareas/{d.t_pasada.id}", json={"estado": "en-proceso"})
        assert r.status_code == 404
        # Una suya sin entregas, en la ventana: la puede mover, y no le vuelve el contador.
        async with d.Sesion() as s:
            s.add(CalendarioTarea(id=f"ta-libre-{d.sufijo}", barra_id=d.dentro.id, titulo="Libre",
                                  asignado_a_id=d.a1.id, creado_por_id=d.promo.id))
            await s.commit()
        r = await a1.patch(f"/calendario/tareas/ta-libre-{d.sufijo}", json={"estado": "en-proceso"})
        assert r.status_code == 200, r.text
        assert r.json()["rev"] is None
    correr(prueba)


def test_no_escribe_en_el_calendario():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        assert (await a1.post("/calendario/barras", json={
            "id": f"br-x-{d.sufijo}", "seccion": "comercial", "banda": "X", "nombre": "X",
            "desde": d.v[0].isoformat(), "hasta": d.v[0].isoformat()})).status_code == 403
        assert (await a1.post(f"/calendario/barras/{d.dentro.id}/tareas",
                              json={"id": f"ta-x-{d.sufijo}", "titulo": "X"})).status_code == 403
        assert (await a1.put(f"/calendario/tareas/{d.t_mia.id}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.aprob.id], "fases": [{"nombre": "A"}]})).status_code == 403
        assert (await a1.post(f"/calendario/versiones/{d.v_mia.id}/decision",
                              json={"decision": "aprobada"})).status_code == 403
    correr(prueba)


def test_al_equipo_no_lo_dejan_poner_a_la_agencia_en_avisos_ni_de_aprobadora():
    async def prueba(d):
        promo = Cliente(d.http, d.promo)
        r = await promo.post(f"/calendario/barras/{d.dentro.id}/avisos",
                             json={"id": f"av-n-{d.sufijo}", "diasAntes": 2, "destinatarios": [d.aprob.id, d.a1.id]})
        assert r.status_code == 422 and "externa" in r.json()["detail"]
        r = await promo.put(f"/calendario/tareas/{d.t_colega.id}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.a1.id], "fases": [{"nombre": "Boceto"}]})
        assert r.status_code == 422 and "externa" in r.json()["detail"]
        # Pero sí asignarle una tarea (es para lo que está).
        r = await promo.post(f"/calendario/barras/{d.dentro.id}/tareas",
                             json={"id": f"ta-asig-{d.sufijo}", "titulo": "Para la agencia", "asignadoA": d.a1.id})
        assert r.status_code == 201, r.text
    correr(prueba)


def test_los_avisos_configurados_no_le_llegan():
    async def prueba(d):
        # El aviso sembrado (3 días antes de Accion DENTRO) la nombra: si toca, sale para el equipo y no para ella.
        async with d.Sesion() as s:
            await revisar_avisos(s, hoy=d.dentro.desde - timedelta(days=1), barra_id=d.dentro.id)
            a_ella = (await s.execute(select(Notificacion).where(
                Notificacion.user_id == d.a1.id, Notificacion.origen_tipo == "calendario_aviso",
                Notificacion.origen_ref == f"{d.dentro.id}:av-{d.sufijo}"))).scalars().all()
            al_equipo = (await s.execute(select(Notificacion).where(
                Notificacion.user_id == d.aprob.id, Notificacion.origen_ref == f"{d.dentro.id}:av-{d.sufijo}"
            ))).scalars().all()
        assert a_ella == [] and len(al_equipo) == 1
    correr(prueba)


# ---------------------------------------------------------------------------
# Las entregas
# ---------------------------------------------------------------------------

def test_el_detalle_de_su_entrega_sin_notas_internas_ni_mails():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        r = await a1.get(f"/calendario/tareas/{d.t_mia.id}/entregas")
        assert r.status_code == 200, r.text
        _sin_prohibido(r.text, "detalle de entregas")
        assert "notaInterna" not in r.text and "@" not in r.text
        decision = r.json()["fases"][0]["versiones"][0]["decisiones"][0]
        assert decision["comentario"] == "Más grande el logo"  # lo que es para ella, sí
        assert r.json()["fases"][0]["versiones"][0]["marcas"][0]["texto"] == "Subí el logo"
        personas = r.json()["personas"]
        assert set(personas) <= {str(d.a1.id), str(d.aprob.id)}  # quien creó la tarea (promo) no
        assert r.json()["puedo"]["entregar"] is True and r.json()["puedo"]["decidir"] is False
        # La de otra agencia, la del equipo y la suya fuera de la ventana: no existen.
        for t in (d.t_b1, d.t_ajena, d.t_fuera):
            assert (await a1.get(f"/calendario/tareas/{t.id}/entregas")).status_code == 404
        # El equipo sí ve la nota interna.
        r = await Cliente(d.http, d.promo).get(f"/calendario/tareas/{d.t_mia.id}/entregas")
        assert "NOTA INTERNA" in r.json()["fases"][0]["versiones"][0]["decisiones"][0]["notaInterna"]
    correr(prueba)


def test_las_imagenes_solo_las_de_sus_entregas():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        assert (await a1.get(f"/calendario/entregas/imagenes/{d.im_mia.id}", params={"tam": "mini"})).status_code == 200
        for im in (d.im_b1, d.im_fuera):
            assert (await a1.get(f"/calendario/entregas/imagenes/{im.id}")).status_code == 404
    correr(prueba)


def test_entrega_una_ronda_de_lo_suyo_y_nada_mas():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        archivos = [("imagenes", ("a.jpg", JPEG, "image/jpeg")), ("miniaturas", ("m.jpg", JPEG, "image/jpeg"))]
        r = await a1.post(f"/calendario/tareas/{d.t_mia.id}/versiones",
                          data={"versionId": f"ve-n-{d.sufijo}", "corregidas": json.dumps([d.mk_mia.id])},
                          files=archivos)
        assert r.status_code == 201, r.text
        assert r.json()["ronda"] == 2 and r.json()["rev"] is None
        for t in (d.t_fuera, d.t_b1):
            r = await a1.post(f"/calendario/tareas/{t.id}/versiones",
                              data={"versionId": f"ve-x-{t.id}"}, files=archivos)
            assert r.status_code == 404, r.text
    correr(prueba)


def test_tilda_las_marcas_de_lo_suyo_y_nada_mas():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        assert (await a1.patch(f"/calendario/marcas/{d.mk_mia.id}", json={"corregida": True})).status_code == 200
        for mk in (d.mk_b1, d.mk_fuera):
            assert (await a1.patch(f"/calendario/marcas/{mk.id}", json={"corregida": True})).status_code == 404
    correr(prueba)


def test_el_tablero_solo_lo_suyo_y_su_propio_retrabajo():
    async def prueba(d):
        r = await Cliente(d.http, d.a1).get("/calendario/entregas", params={"mundo": MUNDO, "dias": 90})
        assert r.status_code == 200, r.text
        datos = r.json()
        assert [t["tareaId"] for t in datos["tarjetas"]] == [d.t_mia.id]
        _sin_prohibido(r.text, "/calendario/entregas")
        assert "@" not in r.text
        assert {g["clave"] for g in datos["metricas"]["porResponsable"]} <= {d.a1.id}
        # El equipo ve las de todos y el retrabajo de todos.
        todo = (await Cliente(d.http, d.promo).get("/calendario/entregas", params={"mundo": MUNDO})).json()
        assert {d.t_b1.id, d.t_fuera.id} <= {t["tareaId"] for t in todo["tarjetas"]}
        assert {d.b1.id, d.otro.id} <= {g["clave"] for g in todo["metricas"]["porResponsable"]}
    correr(prueba)


def test_mis_entregas_solo_las_de_la_ventana():
    async def prueba(d):
        r = await Cliente(d.http, d.a1).get("/calendario/mis-entregas")
        assert r.status_code == 200, r.text
        assert r.json()["paraRevisar"] == []
        assert [t["tareaId"] for t in r.json()["conCambios"]] == [d.t_mia.id]
        _sin_prohibido(r.text, "/calendario/mis-entregas")
    correr(prueba)


# ---------------------------------------------------------------------------
# La campanita, Don Tino y lo interno
# ---------------------------------------------------------------------------

def test_la_campanita_solo_lo_suyo_de_la_ventana():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        r = await a1.get("/notificaciones")
        assert r.status_code == 200, r.text
        assert [n["mensaje"] for n in r.json()] == ["Te asignaron el afiche"]
        _sin_prohibido(r.text, "/notificaciones")
        assert (await a1.get("/notificaciones/no-leidas/count")).json() == {"count": 1}
    correr(prueba)


def test_don_tino_con_la_base_tampoco_le_cuenta_nada_de_afuera():
    async def prueba(d):
        async with d.Sesion() as s:
            usuario = await s.get(User, d.a1.id)
            for herramienta, args in (
                ("calendario_acciones", {"desde": (d.v[0] - timedelta(days=60)).isoformat(),
                                         "hasta": (d.v[1] + timedelta(days=120)).isoformat()}),
                ("calendario_tareas", {"responsable": "todos"}),
                ("calendario_piezas", {"desde": d.v[0].isoformat(), "hasta": (d.v[1] + timedelta(days=120)).isoformat()}),
                ("calendario_accion", {"accion_id": d.tres.id}),
            ):
                texto = await cc.ejecutar(herramienta, args, usuario, s)
                _sin_prohibido(texto, herramienta)
        # Y el chat en sí no es para ella.
        r = await Cliente(d.http, d.a1).post("/chat/message", json={"message": "hola", "history": []})
        assert r.status_code == 403
    correr(prueba)


def test_lo_interno_contesta_403_aunque_sepa_la_ruta():
    async def prueba(d):
        a1 = Cliente(d.http, d.a1)
        for ruta in ("/admin/users", "/colocacion/resumen?mundo=tienda_inglesa", "/colocacion/mis-fotos",
                     "/redexpres/meses", "/watchlist", "/facturacion/cuentas", "/admin/permissions"):
            r = await a1.get(ruta)
            assert r.status_code == 403, (ruta, r.status_code, r.text)
        # Su sesión, sí: y le dice qué ventana ve.
        me = (await a1.get("/auth/me")).json()
        assert me["es_externo"] is True and me["empresa"] == "Agencia Pampa"
        assert me["ventana"] == {"desde": d.v[0].isoformat(), "hasta": d.v[1].isoformat()}
        assert me["permissions"] == ["calendario.view"]
    correr(prueba)


# ---------------------------------------------------------------------------
# El panel de usuarios
# ---------------------------------------------------------------------------

def test_el_admin_crea_una_cuenta_externa_y_no_le_puede_dar_mas():
    async def prueba(d):
        promo = Cliente(d.http, d.promo)
        r = await promo.post("/admin/users", json={
            "email": f"nueva.{d.sufijo}@pampa-agencia.uy", "full_name": "Nueva Agencia", "password": "Clave-segura-123",
            "es_externo": True, "empresa": "Agencia Nueva", "mundos": ["tienda_inglesa", "tienda_express"]})
        assert r.status_code == 201, r.text
        nuevo = r.json()["id"]
        lista = {u["id"]: u for u in (await promo.get("/admin/users")).json()}
        assert lista[nuevo]["es_externo"] is True and lista[nuevo]["empresa"] == "Agencia Nueva"
        assert lista[nuevo]["permissions"] == ["calendario.view"]
        assert lista[nuevo]["mundos"] == ["tienda_inglesa", "tienda_express"]
        assert lista[nuevo]["role_id"] is None and lista[nuevo]["is_superuser"] is False

        # Ni el superadmin le puede dar gestión, admin ni un rol.
        for permisos in (["calendario.view", "calendario.tareas"], ["calendario.view", "calendario.edit"],
                         ["platform.admin"], ["calendario.view", "calendario.retail_media"]):
            r = await promo.patch(f"/admin/users/{nuevo}/permissions", json={"permissions": permisos})
            assert r.status_code == 422, (permisos, r.text)
        roles = (await promo.get("/admin/roles")).json()
        for rol in roles:
            r = await promo.patch(f"/admin/users/{nuevo}/role", json={"role_id": rol["id"]})
            assert r.status_code == 422, (rol["name"], r.text)
        # Sin empresa no se crea, y con rol tampoco.
        r = await promo.post("/admin/users", json={
            "email": f"otra.{d.sufijo}@pampa-agencia.uy", "full_name": "X", "password": "Clave-segura-123",
            "es_externo": True, "empresa": "  "})
        assert r.status_code == 422
        r = await promo.post("/admin/users", json={
            "email": f"otra.{d.sufijo}@pampa-agencia.uy", "full_name": "X", "password": "Clave-segura-123",
            "es_externo": True, "empresa": "A", "role_id": roles[0]["id"]})
        assert r.status_code == 422
        # Pasar a alguien del equipo a externo le saca lo que no corresponde.
        r = await promo.patch(f"/admin/users/{d.otro.id}/externo", json={"es_externo": True, "empresa": "Estudio Sur"})
        assert r.status_code == 200, r.text
        assert r.json()["permissions"] == ["calendario.view"]
    correr(prueba)


def test_la_base_misma_no_guarda_un_externo_con_permisos_de_mas():
    async def prueba(d):
        from sqlalchemy.exc import IntegrityError
        async with d.Sesion() as s:
            u = await s.get(User, d.a1.id)
            u.permissions = ["calendario.view", "calendario.tareas"]
            with pytest.raises(IntegrityError):
                await s.commit()
            await s.rollback()
            u = await s.get(User, d.a1.id)
            u.is_superuser = True
            with pytest.raises(IntegrityError):
                await s.commit()
    correr(prueba)
