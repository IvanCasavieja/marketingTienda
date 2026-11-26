"""La purga de las validaciones de RRSS sin trabar a nadie (26/11/2026).

Las validaciones se borran a las 24 horas y las tablas se compactan con
VACUUM FULL (ver test_rrss_retencion_un_dia.py). Una validación hecha a las
10 de la mañana vence a las 10 del día siguiente: la purga casi siempre
compacta en horario de trabajo, con alguien validando. Lo que se fija acá,
contra Postgres:

- compactar no hace fila: si alguien está usando la tabla (una placa a medio
  validar), no la toca y avisa. Antes VACUUM FULL esperaba su turno y,
  mientras esperaba, trababa a todos los que llegaban después, hasta la
  lista de validaciones;
- lo que no se pudo compactar (en uso, o falló) se intenta en la pasada
  siguiente, y lo recién borrado se compacta enseguida y otra vez en la
  siguiente: con una transacción más vieja abierta, VACUUM FULL se guardaba
  lo recién borrado y el lugar no volvía;
- el lazo arranca con las tres tablas por compactar, por si el proceso
  anterior no llegó;
- una placa no tiene la base tomada mientras CatTi la mira (de cinco a
  noventa segundos): la transacción quedaba abierta todo ese rato, con las
  tablas de RRSS en uso, y la purga no podía compactarlas en todo el día;
- si la validación se borra mientras CatTi mira una placa (venció, o la
  borró quien la creó), la placa dice que ya no está en vez de «Internal
  server error».
"""
import asyncio
import os
import time
import types

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: esta prueba necesita una base Postgres")

MB = 1024 * 1024


async def _que_hizo(coro, segundos: float):
    """Lo que hizo `coro` en `segundos`: su resultado, el nombre de la excepción
    que tiró, o «esperó» si en ese rato no terminó."""
    try:
        return await asyncio.wait_for(coro, timeout=segundos)
    except asyncio.TimeoutError:
        return "esperó"
    except Exception as exc:
        return type(exc).__name__


@con_base
def test_compactar_no_hace_fila_detras_de_una_placa_a_medio_validar(monkeypatch):
    """Una placa a medio validar tiene la tabla en uso mientras CatTi la mira.
    VACUUM FULL esperaba a que terminara y, mientras esperaba, frenaba a
    todos los que llegaban después, hasta un SELECT. Ahora no espera: avisa
    TablaEnUso al instante, nadie queda trabado y, cuando la tabla se libera,
    compacta."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.core.database as database
    from app.services import espacio

    tabla = "rrss_validacion_imagenes"

    async def prueba():
        # Un motor propio: el global puede traer conexiones de otro loop.
        motor = create_async_engine(URL, connect_args={"statement_cache_size": 0})
        monkeypatch.setattr(database, "engine", motor)
        try:
            placa = await motor.connect()
            try:
                # La placa leyó la tabla y su transacción sigue abierta.
                await placa.execute(text(f"SELECT count(*) FROM {tabla}"))
                inicio = time.monotonic()
                assert await _que_hizo(espacio.compactar(tabla), 8) == "TablaEnUso"
                assert time.monotonic() - inicio < 3, "esperó a la placa"
                # Y nadie quedó en la fila detrás: la lista contesta enseguida.
                async with motor.connect() as lista:
                    assert await _que_hizo(lista.execute(text(f"SELECT count(*) FROM {tabla}")), 3) != "esperó"
            finally:
                await placa.rollback()
                await placa.close()
            # CatTi terminó: ahora sí se compacta.
            antes, despues = await asyncio.wait_for(espacio.compactar(tabla), timeout=30)
            assert despues <= antes
        finally:
            await motor.dispose()

    asyncio.run(prueba())


# ---------------------------------------------------------------- lo que queda por compactar

class _Borra:
    """La sesión de la purga, de mentira: cada DELETE «borra» lo que diga la
    lista, en orden."""

    def __init__(self, cuantas):
        self._cuantas = iter(cuantas)

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def execute(self, *_a, **_k):
        return types.SimpleNamespace(rowcount=next(self._cuantas))

    async def commit(self):
        pass


def test_una_tabla_en_uso_o_que_fallo_se_compacta_en_la_pasada_siguiente(monkeypatch):
    """Antes, si compactar fallaba (o, desde ahora, si la tabla estaba en uso),
    nadie lo volvía a intentar hasta que se borrara otra validación: el lugar
    podía quedar tomado días. Ahora queda para la pasada siguiente, y una vez
    compactada no se vuelve a trabar."""
    import app.services.rrss.retencion as retencion
    from app.services.espacio import TablaEnUso

    imagenes, paginas, validaciones = retencion.TABLAS
    tropiezos = {imagenes: TablaEnUso("en uso"), paginas: RuntimeError("se cortó la conexión")}
    intentos = []

    async def compactar(tabla):
        intentos.append(tabla)
        if tabla in tropiezos:
            raise tropiezos.pop(tabla)  # solo la primera vez
        return 10 * MB, MB

    monkeypatch.setattr(retencion, "AsyncSessionLocal", _Borra([0, 0, 0]))
    monkeypatch.setattr(retencion, "compactar", compactar)
    pendientes = set(retencion.TABLAS)

    def pasada():
        intentos.clear()
        return asyncio.run(retencion.purgar_validaciones_vencidas(24, pendientes))

    pasada()
    assert intentos == [imagenes, paginas, validaciones]
    assert pendientes == {imagenes, paginas}, "la que estaba en uso y la que falló quedan para la próxima"
    pasada()
    assert intentos == [imagenes, paginas] and pendientes == set()
    pasada()
    assert intentos == [], "sin nada borrado ni pendiente no se traba ninguna tabla"


def test_lo_recien_borrado_se_compacta_enseguida_y_otra_vez_en_la_pasada_siguiente(monkeypatch):
    """La segunda vez es la que devuelve el lugar si en la primera había una
    transacción más vieja abierta (ver la prueba contra Postgres de abajo)."""
    import app.services.rrss.retencion as retencion

    intentos = []

    async def compactar(tabla):
        intentos.append(tabla)
        return MB, MB

    monkeypatch.setattr(retencion, "AsyncSessionLocal", _Borra([3, 0, 0]))
    monkeypatch.setattr(retencion, "compactar", compactar)
    pendientes: set[str] = set()

    def pasada():
        intentos.clear()
        return asyncio.run(retencion.purgar_validaciones_vencidas(24, pendientes))

    assert pasada() == 3
    assert intentos == list(retencion.TABLAS) and pendientes == set(retencion.TABLAS)
    assert pasada() == 0
    assert intentos == list(retencion.TABLAS) and pendientes == set()
    assert pasada() == 0
    assert intentos == []


def test_el_lazo_arranca_con_las_tres_tablas_por_compactar(monkeypatch):
    """Si el proceso anterior borró y no llegó a compactar (estaban en uso, o
    Render lo reinició en el medio), nadie se acordaba: la primera pasada de
    cada arranque compacta las tres."""
    import app.services.rrss.retencion as retencion

    class _Basta(Exception):
        pass

    vistas = []

    async def purgar(horas, pendientes=None):
        vistas.append(None if pendientes is None else set(pendientes))
        return 0

    async def dormir(_segundos):
        raise _Basta

    monkeypatch.setattr(retencion, "purgar_validaciones_vencidas", purgar)
    monkeypatch.setattr(retencion, "asyncio", types.SimpleNamespace(sleep=dormir))
    with pytest.raises(_Basta):
        asyncio.run(retencion.run_purga_rrss_loop())
    assert vistas == [set(retencion.TABLAS)]


@con_base
def test_el_lugar_vuelve_aunque_hubiera_una_transaccion_abierta_al_borrar(monkeypatch):
    """VACUUM FULL se guarda las filas que todavía podría ver una transacción
    empezada antes del borrado, en cualquier base del servidor: cualquier
    pedido que estuviera guardando algo en ese momento. Con una así abierta,
    la compactación de la misma pasada no devolvía nada, la siguiente ya no
    borraba y nadie volvía a compactar: el lugar no volvía (visto el
    26/11/2026). Ahora la pasada siguiente compacta otra vez y vuelven los 4 MB
    de la validación vieja: lo que mira el freno (pg_database_size) baja."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.core.database as database
    import app.services.rrss.retencion as retencion
    from app.models.rrss_validacion import RrssValidacion, RrssValidacionImagen, RrssValidacionPagina
    from app.services import espacio

    class _Basta(Exception):
        pass

    async def prueba():
        motor = create_async_engine(URL, connect_args={"statement_cache_size": 0})
        sesiones = async_sessionmaker(motor, expire_on_commit=False)
        monkeypatch.setattr(retencion, "AsyncSessionLocal", sesiones)
        monkeypatch.setattr(database, "engine", motor)

        async def tamano():
            async with sesiones() as db:
                return await espacio.tamano_de_la_base(db)

        vid = None
        vieja = None
        try:
            async with sesiones() as db:
                v = RrssValidacion(nombre_mailing="vieja.pdf", estado="completada", config={},
                                   mailing={"productos": []},
                                   created_at=datetime.now(timezone.utc) - timedelta(hours=30))
                db.add(v)
                await db.flush()
                vid = v.id
                # Imágenes de verdad: bytes que no se comprimen.
                db.add(RrssValidacionPagina(validacion_id=vid, numero=0, ancho=10, alto=10,
                                            imagen=os.urandom(2 * MB)))
                db.add(RrssValidacionImagen(validacion_id=vid, orden=0, nombre_archivo="placa.jpg", estado="ok",
                                            resultado={"filas": []}, vista=os.urandom(2 * MB)))
                await db.commit()
            lleno = await tamano()

            # Alguien está guardando algo (su transacción ya tiene número) cuando pasa la purga.
            vieja = await motor.connect()
            await vieja.execute(text("SELECT txid_current()"))

            medidas = []

            async def entre_pasadas(_segundos):
                medidas.append(await tamano())
                if len(medidas) == 2:
                    raise _Basta
                # Esa persona termina. Y se espera a que termine toda transacción
                # más vieja que el borrado: en las pruebas, las de otras bases del
                # mismo servidor; en producción, la pasada siguiente es una hora
                # después.
                await vieja.rollback()
                async with motor.connect() as c:
                    marca = (await c.execute(text("SELECT txid_current()"))).scalar_one()
                    await c.commit()
                for _ in range(300):
                    async with motor.connect() as c:
                        horizonte = (await c.execute(
                            text("SELECT txid_snapshot_xmin(txid_current_snapshot())"))).scalar_one()
                    if horizonte > marca:
                        return
                    await asyncio.sleep(0.2)
                pytest.skip("Otra base de este servidor tiene una transacción abierta hace más de un minuto")

            monkeypatch.setattr(retencion, "asyncio", types.SimpleNamespace(sleep=entre_pasadas))
            with pytest.raises(_Basta):
                await retencion.run_purga_rrss_loop()

            primera, segunda = medidas
            assert lleno - primera < MB, "la premisa: con esa transacción abierta, compactar enseguida no alcanza"
            assert lleno - segunda >= 3 * MB, f"en la pasada siguiente volvieron {(lleno - segunda) / MB:.1f} MB de 4"
        finally:
            if vieja is not None:
                await vieja.close()
            if vid is not None:
                async with sesiones() as db:
                    await db.execute(delete(RrssValidacion).where(RrssValidacion.id == vid))
                    await db.commit()
            await motor.dispose()

    asyncio.run(prueba())


# ---------------------------------------------------------------- la placa, mientras CatTi la mira

def _jpeg() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buf, "JPEG")
    return buf.getvalue()


async def _con_la_app(prueba):
    """La app de verdad contra la base de prueba, con sesiones que confirman de
    verdad (no adentro de una transacción que se deshace al final): lo que se
    prueba es justamente qué tiene tomado cada pedido. Siembra una persona que
    valida y una validación suya en curso, con una página del mailing, y las
    borra al terminar."""
    import uuid
    from datetime import datetime, timezone

    import httpx
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.database import get_db
    from app.core.rate_limit import limiter
    from app.core.security import create_access_token, hash_password
    from app.main import app
    from app.models.ai_usage_log import AIUsageLog
    from app.models.rrss_validacion import RrssValidacion, RrssValidacionPagina
    from app.models.user import User

    motor = create_async_engine(URL, connect_args={"statement_cache_size": 0})
    sesiones = async_sessionmaker(motor, expire_on_commit=False)

    async def get_db_de_prueba():
        async with sesiones() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    uid = vid = None
    app.dependency_overrides[get_db] = get_db_de_prueba
    limite_antes = limiter.enabled
    limiter.enabled = False
    try:
        async with sesiones() as db:
            u = User(email=f"valida.{uuid.uuid4().hex[:8]}@prueba-rrss.test", full_name="Valida Placas",
                     hashed_password=hash_password("Clave-de-prueba-1"),
                     permissions=["rrss.view", "rrss.validate"], is_active=True, is_superuser=False,
                     must_change_password=False, password_changed_at=datetime.now(timezone.utc))
            db.add(u)
            await db.flush()
            uid = u.id
            v = RrssValidacion(nombre_mailing="mailing.pdf", estado="en_proceso", config={},
                               mailing={"productos": []}, creado_por_id=uid)
            db.add(v)
            await db.flush()
            vid = v.id
            db.add(RrssValidacionPagina(validacion_id=vid, numero=0, ancho=20, alto=20, imagen=_jpeg()))
            await db.commit()
        cabeza = {"Authorization": f"Bearer {create_access_token(uid)}"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as http:
            await prueba(http, cabeza, motor, sesiones, vid, uid)
    finally:
        limiter.enabled = limite_antes
        app.dependency_overrides.pop(get_db, None)
        async with sesiones() as db:
            if vid is not None:
                await db.execute(delete(RrssValidacion).where(RrssValidacion.id == vid))
            if uid is not None:
                await db.execute(delete(AIUsageLog).where(AIUsageLog.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))
            await db.commit()
        await motor.dispose()


async def _nadie_tiene_tomadas_las_tablas(motor) -> bool:
    """Si en este momento se podría compactar: nadie tiene en uso ninguna de
    las tres tablas de RRSS (ni para leer)."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    async with motor.connect() as c:
        try:
            await c.execute(text(
                "LOCK TABLE rrss_validaciones, rrss_validacion_paginas, rrss_validacion_imagenes "
                "IN ACCESS EXCLUSIVE MODE NOWAIT"))
            return True
        except DBAPIError:
            return False
        finally:
            await c.rollback()


def _placa_ok():
    from app.services.rrss.validador import ResultadoPlaca

    return ResultadoPlaca(resultado={"filas": [], "tiempos_ms": {}}, vista=None, ancho=20, alto=20,
                          formato="cuadrada", estado="ok", tokens_in=1000, tokens_out=200)


@con_base
def test_mientras_catti_mira_la_placa_la_base_queda_libre(monkeypatch):
    """La ruta de cada placa leía la validación, dejaba la transacción abierta
    y llamaba a CatTi (hasta cinco veces): todo ese rato tenía una conexión
    del pool y las tablas de RRSS en uso, y la purga no podía compactarlas.
    Ahora, mientras CatTi mira la placa (antes y después de traer las páginas
    del mailing), nadie tiene las tablas tomadas; y la placa se guarda igual."""
    from sqlalchemy import func, select

    from app.models.ai_usage_log import AIUsageLog
    from app.models.rrss_validacion import RrssValidacionImagen
    from app.services.rrss import validador

    libres = []

    async def validar_placa(datos, nombre, mailing, cargar_paginas, config):
        motor = estado["motor"]
        libres.append(await _nadie_tiene_tomadas_las_tablas(motor))
        await cargar_paginas()
        libres.append(await _nadie_tiene_tomadas_las_tablas(motor))
        return _placa_ok()

    estado = {}
    monkeypatch.setattr(validador, "validar_placa", validar_placa)

    async def prueba(http, cabeza, motor, sesiones, vid, uid):
        estado["motor"] = motor
        r = await http.post(f"/api/v1/rrss/validaciones/{vid}/imagenes", headers=cabeza,
                            files={"archivo": ("placa.jpg", _jpeg(), "image/jpeg")}, data={"orden": "0"})
        assert r.status_code == 200, r.text
        assert libres == [True, True], "mientras CatTi miraba la placa, las tablas de RRSS seguían tomadas"
        async with sesiones() as db:
            assert await db.scalar(select(func.count()).select_from(RrssValidacionImagen)
                                   .where(RrssValidacionImagen.validacion_id == vid)) == 1
            assert await db.scalar(select(func.sum(AIUsageLog.input_tokens))
                                   .where(AIUsageLog.user_id == uid)) == 1000

    asyncio.run(_con_la_app(prueba))


@con_base
def test_si_la_validacion_se_borra_mientras_catti_mira_la_placa_dice_que_ya_no_esta(monkeypatch):
    """La validación vence (o la borra quien la creó, desde otra pestaña)
    mientras CatTi mira una de sus placas. Al guardarla fallaba la clave
    foránea y la placa quedaba marcada con «Internal server error». Ahora dice
    por qué, con el mismo 404 que al abrirla, no queda nada suelto y los
    tokens que ya se gastaron se anotan igual."""
    from sqlalchemy import delete, func, select

    from app.models.ai_usage_log import AIUsageLog
    from app.models.rrss_validacion import RrssValidacion, RrssValidacionImagen
    from app.services.rrss import validador

    estado = {}

    async def validar_placa(datos, nombre, mailing, cargar_paginas, config):
        # Mientras CatTi mira la placa, pasa la purga.
        async with estado["sesiones"]() as db:
            await db.execute(delete(RrssValidacion).where(RrssValidacion.id == estado["vid"]))
            await db.commit()
        return _placa_ok()

    monkeypatch.setattr(validador, "validar_placa", validar_placa)

    async def prueba(http, cabeza, motor, sesiones, vid, uid):
        estado.update(sesiones=sesiones, vid=vid)
        r = await http.post(f"/api/v1/rrss/validaciones/{vid}/imagenes", headers=cabeza,
                            files={"archivo": ("placa.jpg", _jpeg(), "image/jpeg")}, data={"orden": "0"})
        assert r.status_code == 404, r.text
        assert "ya no está" in r.json()["detail"]
        async with sesiones() as db:
            assert await db.scalar(select(func.count()).select_from(RrssValidacionImagen)
                                   .where(RrssValidacionImagen.validacion_id == vid)) == 0
            assert await db.scalar(select(func.sum(AIUsageLog.input_tokens))
                                   .where(AIUsageLog.user_id == uid)) == 1000, "los tokens gastados no se anotaron"

    asyncio.run(_con_la_app(prueba))
