"""Retención de cenefas (26/11/2026): el archivo de TODA corrida, verificada o
no, se borra a las 24 horas; la corrida queda (con su número y si se verificó)
y la tabla se compacta para que el lugar vuelva. Ivan: «que quede guardado a lo
sumo un día y nada más»."""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: esta prueba necesita una base Postgres")


def test_el_archivo_de_toda_corrida_se_va_al_dia_y_la_corrida_queda(monkeypatch):
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.core.database as database
    import app.services.cenefas.jobs as jobs
    from app.models.cenefa_job import CenefaJob

    async def prueba():
        # Un motor propio: el global puede traer conexiones de otro loop.
        motor = create_async_engine(URL, connect_args={"statement_cache_size": 0})
        sesiones = async_sessionmaker(motor, expire_on_commit=False)
        monkeypatch.setattr(jobs, "AsyncSessionLocal", sesiones)
        monkeypatch.setattr(database, "engine", motor)
        ahora = datetime.now(timezone.utc)
        casos = {
            "vieja_verificada": (True, ahora - timedelta(hours=30)),
            "vieja_sin_verificar": (False, ahora - timedelta(hours=30)),
            "nueva_verificada": (True, ahora - timedelta(hours=2)),
        }
        ids = {}
        try:
            async with sesiones() as db:
                for nombre, (verificado, cuando) in casos.items():
                    j = CenefaJob(format="rompe-precios", export_type="pptx", status="done", verificado=verificado,
                                  row_count=5, result_bytes=b"pptx" * 2000, created_at=cuando, completed_at=cuando)
                    db.add(j)
                    await db.flush()
                    ids[nombre] = j.id
                await db.commit()

            purgados, _ = await jobs.purgar_archivos_vencidos(24)
            assert purgados >= 2

            async with sesiones() as db:
                filas = {j.id: j for j in (await db.execute(select(CenefaJob).where(CenefaJob.id.in_(ids.values())))).scalars()}
            vieja = filas[ids["vieja_verificada"]]
            assert vieja.result_bytes is None, "la verificada vieja también pierde el archivo"
            assert vieja.verificado is True and vieja.row_count == 5, "pero la corrida queda, con su número"
            assert filas[ids["vieja_sin_verificar"]].result_bytes is None
            assert filas[ids["nueva_verificada"]].result_bytes is not None, "la de hace 2 horas sigue para bajarla"
        finally:
            async with sesiones() as db:
                await db.execute(delete(CenefaJob).where(CenefaJob.id.in_(ids.values())))
                await db.commit()
            await motor.dispose()

    asyncio.run(prueba())


def test_solo_se_compactan_las_tablas_que_la_plataforma_vacia_sola():
    from app.services import espacio

    with pytest.raises(ValueError):
        asyncio.run(espacio.compactar("users"))
