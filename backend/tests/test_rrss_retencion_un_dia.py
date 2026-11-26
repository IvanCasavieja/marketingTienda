"""Validación de RRSS sin historial (26/11/2026): una validación dura 24 horas,
terminada o no; después se borra entera (las páginas del mailing, cada placa
con su vista chica y los recortes de cada diferencia) y las tres tablas se
compactan para que el lugar vuelva. Ivan: «no tiene sentido que mantengamos
historial de validaciones». Mismo molde que test_cenefas_retencion_un_dia.py."""
import asyncio
import os
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: esta prueba necesita una base Postgres")


@con_base
def test_la_de_hace_30_horas_se_borra_entera_y_la_de_hace_2_queda(monkeypatch):
    from sqlalchemy import delete, func, select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.core.database as database
    import app.services.rrss.retencion as retencion
    from app.models.rrss_validacion import RrssValidacion, RrssValidacionImagen, RrssValidacionPagina

    async def prueba():
        # Un motor propio: el global puede traer conexiones de otro loop.
        motor = create_async_engine(URL, connect_args={"statement_cache_size": 0})
        sesiones = async_sessionmaker(motor, expire_on_commit=False)
        monkeypatch.setattr(retencion, "AsyncSessionLocal", sesiones)
        monkeypatch.setattr(database, "engine", motor)
        compactadas = {}
        compactar_de_verdad = retencion.compactar

        async def compactar_y_anotar(tabla):
            # Se anota DESPUÉS del VACUUM: si falla, la purga lo deja en el log
            # y sigue, y esta prueba tiene que enterarse.
            antes, despues = await compactar_de_verdad(tabla)
            compactadas[tabla] = (antes, despues)
            return antes, despues

        monkeypatch.setattr(retencion, "compactar", compactar_y_anotar)

        ahora = datetime.now(timezone.utc)
        casos = {
            "vieja_terminada": ("completada", ahora - timedelta(hours=30)),
            "vieja_sin_terminar": ("en_proceso", ahora - timedelta(hours=30)),
            "sin_fecha": ("completada", ahora),
            "de_hoy": ("en_proceso", ahora - timedelta(hours=2)),
        }
        ids = {}
        try:
            async with sesiones() as db:
                for nombre, (estado, cuando) in casos.items():
                    v = RrssValidacion(nombre_mailing=f"{nombre}.pdf", estado=estado, config={},
                                       mailing={"productos": []}, created_at=cuando)
                    db.add(v)
                    await db.flush()
                    ids[nombre] = v.id
                    db.add(RrssValidacionPagina(validacion_id=v.id, numero=0, ancho=10, alto=10,
                                                imagen=b"jpg" * 2000))
                    db.add(RrssValidacionImagen(validacion_id=v.id, orden=0, nombre_archivo="placa.jpg",
                                                estado="ok", resultado={"filas": []}, vista=b"jpg" * 2000))
                # La app no puede dejarla sin fecha (el ORM deja que la base
                # ponga now()), pero la columna admite NULL: una cargada a mano.
                await db.execute(update(RrssValidacion).where(RrssValidacion.id == ids["sin_fecha"])
                                 .values(created_at=None))
                await db.commit()

            borradas = await retencion.purgar_validaciones_vencidas(24)
            assert borradas >= 3

            async with sesiones() as db:
                quedan = set((await db.execute(
                    select(RrssValidacion.id).where(RrssValidacion.id.in_(ids.values()))
                )).scalars())
                paginas = dict((await db.execute(
                    select(RrssValidacionPagina.validacion_id, func.count())
                    .where(RrssValidacionPagina.validacion_id.in_(ids.values()))
                    .group_by(RrssValidacionPagina.validacion_id)
                )).all())
                placas = dict((await db.execute(
                    select(RrssValidacionImagen.validacion_id, func.count())
                    .where(RrssValidacionImagen.validacion_id.in_(ids.values()))
                    .group_by(RrssValidacionImagen.validacion_id)
                )).all())
            assert quedan == {ids["de_hoy"]}, "las viejas se van, terminadas o no; la de hace 2 horas queda"
            assert paginas == {ids["de_hoy"]: 1}, "las páginas del mailing se van con su validación"
            assert placas == {ids["de_hoy"]: 1}, "y las placas, con su vista y sus recortes, también"
            assert set(compactadas) == set(retencion.TABLAS), "borró algo: se compactan las tres tablas"
            for tabla, (antes, despues) in compactadas.items():
                assert despues <= antes, f"{tabla} creció al compactarla"
        finally:
            async with sesiones() as db:
                await db.execute(delete(RrssValidacion).where(RrssValidacion.id.in_(ids.values())))
                await db.commit()
            await motor.dispose()

    asyncio.run(prueba())


def test_si_no_hay_nada_vencido_no_traba_ninguna_tabla(monkeypatch):
    """La pasada corre cada hora y VACUUM FULL traba la tabla mientras dura:
    sin nada que borrar, no se compacta."""
    import app.services.rrss.retencion as retencion

    class _SinNada:
        rowcount = 0

    class _Sesion:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, *_a, **_k):
            return _SinNada()

        async def commit(self):
            pass

    compactadas = []

    async def compactar(tabla):
        compactadas.append(tabla)
        return 0, 0

    monkeypatch.setattr(retencion, "AsyncSessionLocal", _Sesion)
    monkeypatch.setattr(retencion, "compactar", compactar)
    assert asyncio.run(retencion.purgar_validaciones_vencidas(24)) == 0
    assert compactadas == []


@pytest.mark.parametrize("horas", [0, -1])
def test_con_cero_horas_no_borra_nada(monkeypatch, horas):
    """0 es la llave para apagarla (como en config.py). Sin este freno, un corte
    en «ahora» se llevaba también las validaciones que se están revisando."""
    import app.services.rrss.retencion as retencion

    def _no_tiene_que_abrir_la_base():
        raise AssertionError("con 0 horas no se toca la base")

    monkeypatch.setattr(retencion, "AsyncSessionLocal", _no_tiene_que_abrir_la_base)
    assert asyncio.run(retencion.purgar_validaciones_vencidas(horas)) == 0


def test_solo_se_pueden_compactar_las_tablas_permitidas():
    """Las tres de RRSS se suman a las de cenefas y de Clientes VIP (0094), y
    ninguna más: VACUUM FULL traba la tabla, y el nombre va pegado en la orden."""
    from app.services import espacio
    from app.services.rrss import retencion

    assert set(retencion.TABLAS) == {"rrss_validaciones", "rrss_validacion_paginas", "rrss_validacion_imagenes"}
    assert espacio.TABLAS_COMPACTABLES == {
        "cenefa_jobs", "cenefa_templates_v2", *retencion.TABLAS,
        "vip_cliente_mes", "vip_clientes", "vip_mes_dimension", "vip_detalle",
    }
    for tabla in ("users", "entrega_imagenes", 'rrss_validaciones"; DROP TABLE users; --'):
        with pytest.raises(ValueError):
            asyncio.run(espacio.compactar(tabla))


def test_las_validaciones_duran_24_horas_por_defecto():
    from app.core.config import Settings

    assert Settings.model_fields["RRSS_RETENCION_HORAS"].default == 24


def test_la_purga_arranca_adentro_de_las_migraciones():
    """Como la de cenefas y la de colocación: hace una pasada apenas arranca
    (la que se lleva el historial viejo), y en una base nueva las tablas
    todavía no existen. Y solo en el servidor desplegado, con su llave."""
    fuente = (pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py").read_text(encoding="utf-8")
    lanzar = "asyncio.create_task(run_purga_rrss_loop())"
    assert fuente.count(lanzar) == 1, "la purga se lanza en más de un lugar, o en ninguno"
    inicio = fuente.index("async def _run_migrations():")
    fin = fuente.index("if mantenimiento:\n        asyncio.create_task(_run_migrations())")
    donde = fuente.index(lanzar)
    assert inicio < donde < fin, "la purga tiene que arrancar adentro de _run_migrations"
    assert fuente.rindex("if settings.RRSS_RETENCION_HORAS > 0:", 0, donde) > inicio


def test_abrir_una_que_ya_se_borro_dice_por_que(monkeypatch):
    """Abrir (o bajar el Excel de) una validación que ya se borró sola daba
    «No se encontró esa validación»: parecía una falla. Ahora dice por qué no
    está. Y con la purga apagada no promete algo que no pasa."""
    from fastapi import HTTPException

    from app.api.routes import rrss

    class _SinNada:
        async def get(self, *_a, **_k):
            return None

    monkeypatch.setattr(rrss.settings, "RRSS_RETENCION_HORAS", 24)
    with pytest.raises(HTTPException) as e:
        asyncio.run(rrss._get_validacion_or_404(_SinNada(), 123))
    assert e.value.status_code == 404
    assert "ya no está" in e.value.detail and "24 horas" in e.value.detail

    monkeypatch.setattr(rrss.settings, "RRSS_RETENCION_HORAS", 0)
    assert "24 horas" not in rrss._ya_no_esta()
