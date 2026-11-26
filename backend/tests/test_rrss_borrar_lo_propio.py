"""Validación de RRSS: el tacho de «Las de hoy» va solo donde el servidor deja
borrar (H-016 del cuaderno; Ramiro lo confirmó en el navegador el 26/11/2026).

La lista mostraba el tacho en las validaciones de todas las personas. Al
tocarlo en la de otra, el servidor contestaba 403 (bien) y la pantalla
reemplazaba la lista entera por «No se pudieron cargar las validaciones de
hoy», que encima era falso: la lista había cargado bien. Ahora la lista dice,
fila por fila, si esa persona puede borrarla (`puede_borrar`), con la misma
regla que DELETE: rrss.validate y que sea suya, o superusuario.

Necesita una base Postgres en la última migración (TEST_DATABASE_URL); sin
ella se saltea. Corre adentro de una transacción que se deshace al final.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")

API = "/api/v1"


async def _correr(prueba):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.database import get_db
    from app.core.rate_limit import limiter
    from app.main import app

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
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as http:
            await prueba(http, Sesion)
    finally:
        limiter.enabled = limite_antes
        app.dependency_overrides.pop(get_db, None)
        await trans.rollback()
        await conn.close()
        await engine.dispose()


def test_la_lista_dice_cuales_puede_borrar_cada_persona_y_borrar_cumple():
    from app.core.security import create_access_token, hash_password
    from app.models.rrss_validacion import RrssValidacion
    from app.models.user import User

    async def prueba(http, Sesion):
        sufijo = uuid.uuid4().hex[:8]
        ahora = datetime.now(timezone.utc)
        clave = hash_password("Clave-de-prueba-1")
        async with Sesion() as s:
            def persona(nombre, permisos, superusuario=False):
                u = User(
                    email=f"{nombre}.{sufijo}@prueba-rrss.test", full_name=nombre.capitalize(),
                    hashed_password=clave, permissions=list(permisos), mundos=["tienda_inglesa"],
                    is_active=True, is_superuser=superusuario, es_externo=False,
                    must_change_password=False, password_changed_at=ahora,
                )
                s.add(u)
                return u

            ana = persona("ana", ("rrss.view", "rrss.validate"))
            beto = persona("beto", ("rrss.view", "rrss.validate"))
            mira = persona("mira", ("rrss.view",))           # solo mira: no borra nada
            jefa = persona("jefa", ("rrss.view",), superusuario=True)
            await s.flush()
            validaciones = {
                quien: RrssValidacion(nombre_mailing=f"de-{quien}-{sufijo}.pdf", estado="completada",
                                      config={}, mailing={"productos": []}, creado_por_id=u.id)
                for quien, u in (("ana", ana), ("beto", beto))
            }
            s.add_all(validaciones.values())
            await s.commit()
        ids = {quien: v.id for quien, v in validaciones.items()}

        def cab(u):
            return {"Authorization": f"Bearer {create_access_token(u.id)}"}

        async def tachos(u):
            r = await http.get(f"{API}/rrss/validaciones", headers=cab(u))
            assert r.status_code == 200, r.text
            return {f["id"]: f["puede_borrar"] for f in r.json() if f["id"] in ids.values()}

        # La lista: cada una ve el tacho solo donde el servidor la va a dejar.
        assert await tachos(ana) == {ids["ana"]: True, ids["beto"]: False}
        assert await tachos(beto) == {ids["ana"]: False, ids["beto"]: True}
        assert await tachos(mira) == {ids["ana"]: False, ids["beto"]: False}
        assert await tachos(jefa) == {ids["ana"]: True, ids["beto"]: True}

        # Y DELETE cumple lo mismo que dijo la lista.
        r = await http.delete(f"{API}/rrss/validaciones/{ids['beto']}", headers=cab(ana))
        assert r.status_code == 403, "Ana no puede borrar la de Beto"
        r = await http.delete(f"{API}/rrss/validaciones/{ids['ana']}", headers=cab(mira))
        assert r.status_code == 403, "quien solo mira no borra"
        r = await http.delete(f"{API}/rrss/validaciones/{ids['ana']}", headers=cab(ana))
        assert r.status_code == 200, r.text
        r = await http.delete(f"{API}/rrss/validaciones/{ids['beto']}", headers=cab(jefa))
        assert r.status_code == 200, "la superadmin borra la de cualquiera"
        assert await tachos(beto) == {}

    asyncio.run(_correr(prueba))
