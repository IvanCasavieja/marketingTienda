"""El lugar de las plantillas de cenefa borradas vuelve a la base (26/11/2026).

La 0094 borra las plantillas que no son de Redexpres (en producción, 35 de 41:
unos 33 MB) y compacta la tabla al publicarse. Pero si justo hay una corrida
generándose —la tiene tomada mientras lee el Excel— no la puede compactar y la
deja «para la próxima». La próxima es la purga de cenefas, cada hora: si la
tabla ocupa bastante más que sus plantillas, la compacta.

Necesita una base Postgres en la última migración (TEST_DATABASE_URL).
"""
import asyncio
import os
import uuid

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: esta prueba necesita una base Postgres")

MB = 1024 * 1024


def test_la_purga_compacta_las_plantillas_que_la_migracion_no_pudo(monkeypatch):
    from sqlalchemy import delete, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import app.core.database as database
    import app.services.cenefas.jobs as jobs
    from app.models.cenefa_template_v2 import CenefaTemplateV2
    from app.services import espacio

    async def prueba():
        motor = create_async_engine(URL, poolclass=NullPool, connect_args={"statement_cache_size": 0})
        sesiones = async_sessionmaker(motor, expire_on_commit=False)
        monkeypatch.setattr(jobs, "AsyncSessionLocal", sesiones)
        monkeypatch.setattr(database, "engine", motor)
        s = uuid.uuid4().hex[:6]
        ids = []

        async def medir() -> int:
            async with motor.connect() as c:
                return (await c.execute(text("SELECT pg_total_relation_size('cenefa_templates_v2')"))).scalar_one()

        try:
            # Seis plantillas de 1 MB (al azar, como un PPTX: no se comprime).
            async with sesiones() as db:
                for k in range(6):
                    t = CenefaTemplateV2(name=f"Lugar {s} {k}", definition={"components": []}, formats=["a4"],
                                         category=f"lugar_{s}", source_pptx=os.urandom(MB))
                    db.add(t)
                    await db.flush()
                    ids.append(t.id)
                await db.commit()
            # Se borran cinco, como la 0094 a las de Tienda Inglesa.
            async with sesiones() as db:
                await db.execute(delete(CenefaTemplateV2).where(CenefaTemplateV2.id.in_(ids[1:])))
                xid = await espacio.transaccion_actual(db)
                await db.commit()
            async with motor.connect() as c:
                queda = (await c.execute(text("SELECT md5(source_pptx) FROM cenefa_templates_v2 WHERE id = :i"),
                                         {"i": ids[0]})).scalar_one()
            if not await espacio.esperar_que_nadie_vea_lo_viejo(xid, 60):
                pytest.skip("Otra transacción de esta base sigue abierta desde antes de borrar: "
                            "VACUUM FULL no puede devolver el lugar todavía")
            con_lugar_muerto = await medir()

            await jobs.purgar_archivos_vencidos(24)

            compactada = await medir()
            assert compactada < con_lugar_muerto - 4 * MB, (con_lugar_muerto, compactada)
            async with motor.connect() as c:
                assert (await c.execute(text("SELECT md5(source_pptx) FROM cenefa_templates_v2 WHERE id = :i"),
                                        {"i": ids[0]})).scalar_one() == queda, "la que queda, intacta"

            # Sin lugar de sobra, la purga no la vuelve a trabar.
            llamadas = []

            async def anotar(tablas, xid=None):
                llamadas.append(tablas)

            monkeypatch.setattr(jobs, "compactar_en_segundo_plano", anotar)
            await jobs.purgar_archivos_vencidos(24)
            assert ["cenefa_templates_v2"] not in llamadas
        finally:
            async with sesiones() as db:
                await db.execute(delete(CenefaTemplateV2).where(CenefaTemplateV2.id.in_(ids)))
                await db.commit()
            await motor.dispose()

    asyncio.run(prueba())
