"""La purga de las validaciones de RRSS sin trabar a nadie (26/11/2026).

Las validaciones se borran a las 24 horas y las tablas se compactan con
VACUUM FULL (ver test_rrss_retencion_un_dia.py). Una validación hecha a las
10 de la mañana vence a las 10 del día siguiente: la purga casi siempre
compacta en horario de trabajo, con alguien validando. Lo que se fija acá,
contra Postgres:

- compactar no hace fila: si alguien está usando la tabla (una placa a medio
  validar), no la toca y avisa. Antes VACUUM FULL esperaba su turno y,
  mientras esperaba, trababa a todos los que llegaban después, hasta la
  lista de validaciones.
"""
import asyncio
import os
import time

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: esta prueba necesita una base Postgres")


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

