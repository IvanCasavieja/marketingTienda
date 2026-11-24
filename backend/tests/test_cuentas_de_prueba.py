"""Las cuentas del Equipo nocturno en el entorno de pruebas (24/11/2026).

Ivan: "deberían tener usuarios propios, como superadmins", y ver la
plataforma "como la agencia". Se crean solo con ENTORNO_DE_PRUEBAS=true y con
la contraseña de su variable; en cada arranque se ponen al día.

Las de base necesitan TEST_DATABASE_URL; corren en una transacción que se
deshace al final.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import cuentas_de_prueba as cp

URL = os.environ.get("TEST_DATABASE_URL")
con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: esta prueba necesita una base Postgres")

CLAVES = {
    "CLAVE_EQUIPO_NOCTURNO": "Nocturno-de-prueba-1",
    "CLAVE_AGENCIA_DE_PRUEBA": "Agencia-de-prueba-1",
    "CLAVE_LOCAL_DE_PRUEBA": "Local-de-prueba-1",
}


def test_fuera_del_entorno_de_pruebas_no_hace_nada(monkeypatch):
    # Producción: ENTORNO_DE_PRUEBAS en false (el valor por defecto). No abre
    # ni una sesión.
    from app.core import config, database

    monkeypatch.setattr(config.settings, "ENTORNO_DE_PRUEBAS", False)

    def no_abrir():
        raise AssertionError("abrió la base fuera del entorno de pruebas")

    monkeypatch.setattr(database, "AsyncSessionLocal", no_abrir)
    asyncio.run(cp.al_arrancar())


def test_por_defecto_no_es_el_entorno_de_pruebas():
    from app.core.config import Settings

    assert Settings.model_fields["ENTORNO_DE_PRUEBAS"].default is False


def test_las_claves_salen_de_las_variables():
    ajustes = SimpleNamespace(CLAVE_EQUIPO_NOCTURNO="a", CLAVE_AGENCIA_DE_PRUEBA="", CLAVE_LOCAL_DE_PRUEBA="c")
    assert cp.claves_de(ajustes) == {
        "CLAVE_EQUIPO_NOCTURNO": "a", "CLAVE_AGENCIA_DE_PRUEBA": "", "CLAVE_LOCAL_DE_PRUEBA": "c",
    }


def test_son_de_example_com():
    # Nadie del otro lado: un aviso por mail que se escape no le llega a nadie.
    assert all(c.email.endswith("@example.com") for c in cp.CUENTAS)


def _correr(prueba):
    async def _en_transaccion():
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        engine = create_async_engine(URL, poolclass=NullPool, connect_args={"statement_cache_size": 0})
        conn = await engine.connect()
        trans = await conn.begin()
        Sesion = async_sessionmaker(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            async with Sesion() as s:
                await prueba(s)
        finally:
            await trans.rollback()
            await conn.close()
            await engine.dispose()

    asyncio.run(_en_transaccion())


async def _cuenta(s, email):
    from sqlalchemy import select

    from app.models.user import User

    return (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def _locales_de(s, usuario):
    from sqlalchemy import select

    from app.models.local_asignacion import LocalAsignacion

    return list((await s.execute(
        select(LocalAsignacion.local_nombre).where(LocalAsignacion.user_id == usuario.id)
    )).scalars())


@con_base
def test_crea_las_tres_cuentas_como_la_gente_de_verdad():
    async def prueba(s):
        from app.core.security import verify_password
        from app.models.role import ALL_PERMISSIONS

        lineas = await cp.preparar(s, CLAVES)
        assert [linea.split(":")[1].strip().split(" ")[0] for linea in lineas] == ["creada"] * 3

        equipo = await _cuenta(s, "equipo-nocturno@example.com")
        assert equipo.is_superuser and set(equipo.permissions) == set(ALL_PERMISSIONS)
        assert not equipo.es_externo and "redexpres" in equipo.mundos
        assert verify_password("Nocturno-de-prueba-1", equipo.hashed_password)
        assert not equipo.must_change_password and not equipo.avisos_por_mail

        agencia = await _cuenta(s, "agencia-de-prueba@example.com")
        assert agencia.es_externo and agencia.empresa == cp.AGENCIA_DE_PRUEBA
        assert agencia.permissions == ["calendario.view"] and not agencia.is_superuser
        assert agencia.role_id is None and agencia.mundos == ["tienda_inglesa"]

        local = await _cuenta(s, "local-de-prueba@example.com")
        assert local.mundos == ["redexpres"] and not local.is_superuser
        assert len(await _locales_de(s, local)) == 1

        # Ninguna contraseña en lo que va al log.
        assert not any(c in linea for linea in lineas for c in CLAVES.values())

    _correr(prueba)


@con_base
def test_cada_arranque_las_deja_al_dia():
    async def prueba(s):
        from app.core.security import hash_password, verify_password

        await cp.preparar(s, CLAVES)
        agencia = await _cuenta(s, "agencia-de-prueba@example.com")
        local = await _cuenta(s, "local-de-prueba@example.com")
        local_antes = await _locales_de(s, local)
        # Una noche la bloquearon, le cambiaron la contraseña y le tocaron los permisos.
        agencia.hashed_password = hash_password("Otra-clave-9")
        agencia.failed_login_attempts = 5
        agencia.locked_until = datetime.now(timezone.utc) + timedelta(hours=1)
        agencia.password_changed_at = datetime.now(timezone.utc) - timedelta(days=90)
        agencia.empresa = "Otra"
        await s.flush()

        lineas = await cp.preparar(s, CLAVES)
        assert all("al día" in linea for linea in lineas)
        await s.refresh(agencia)
        assert verify_password("Agencia-de-prueba-1", agencia.hashed_password)
        assert agencia.failed_login_attempts == 0 and agencia.locked_until is None
        assert agencia.empresa == cp.AGENCIA_DE_PRUEBA
        assert agencia.password_changed_at > datetime.now(timezone.utc) - timedelta(minutes=1)
        # El local no se duplica ni cambia.
        assert await _locales_de(s, local) == local_antes

    _correr(prueba)


@con_base
def test_sin_su_contrasena_una_cuenta_no_se_crea():
    async def prueba(s):
        lineas = await cp.preparar(s, {"CLAVE_EQUIPO_NOCTURNO": "Nocturno-de-prueba-1"})
        assert await _cuenta(s, "equipo-nocturno@example.com") is not None
        assert await _cuenta(s, "agencia-de-prueba@example.com") is None
        assert await _cuenta(s, "local-de-prueba@example.com") is None
        assert "sin CLAVE_AGENCIA_DE_PRUEBA" in lineas[1]

    _correr(prueba)


@con_base
def test_el_local_no_pisa_uno_de_verdad():
    async def prueba(s):
        from app.api.routes.redexpres import LOCALES
        from app.core.security import hash_password
        from app.models.local_asignacion import LocalAsignacion
        from app.models.user import User

        sucursal = User(email=f"{LOCALES[0]} (prueba)", full_name=LOCALES[0], hashed_password=hash_password("x"),
                        permissions=["ai.don_tino"], mundos=["redexpres"])
        s.add(sucursal)
        await s.flush()
        s.add(LocalAsignacion(user_id=sucursal.id, local_nombre=LOCALES[0]))
        await s.flush()

        await cp.preparar(s, CLAVES)
        local = await _cuenta(s, "local-de-prueba@example.com")
        assert LOCALES[0] not in await _locales_de(s, local)

    _correr(prueba)
