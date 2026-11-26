"""El espacio de la base: el freno antes de guardar archivos.

La base es Supabase gratis: 500 MB para TODA la plataforma (calendario,
cenefas, usuarios, avisos...) y no se va a pagar más (15/11/2026). Las
imágenes son lo único que puede llenarla rápido. Antes de guardar cualquiera
(las de las entregas, las fotos de colocación) se pregunta cuánto ocupa la
base: si con lo nuevo pasa de `BASE_TOPE_MB` (400 por defecto), no se guarda,
se le dice a la persona qué hacer y queda un error en el log para que lo vea
quien administra. Mejor una foto rechazada que el calendario sin lugar.

Uso:

    from app.services.espacio import exigir_lugar
    await exigir_lugar(db, len(datos))      # 507 con el mensaje si no entra

o, si se prefiere decidir a mano, `await hay_lugar(db, bytes_nuevos)`.

El ZIP original de una ronda (19/11/2026) tiene además su propio tope,
ZIP_TOPE_MB, que se cuenta con `entra` sobre lo que ya ocupan los ZIP
guardados (ver `entregar` en app/api/routes/entregas.py): un ZIP de 40 MB no
puede dejar sin lugar a las imágenes, que son las que hacen falta para ver la
pieza. Si no entra, no se guarda y la entrega sigue (no es un 507). Nunca se
borra nada para hacer lugar.

Ojo quien reintenta solo ante un 5xx (como la cola del calendario): un 507
no se arregla reintentando.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

MB = 1024 * 1024
MENSAJE_SIN_LUGAR = (
    "La base está casi llena: avisale a quien administra Core Tienda. La imagen no se guardó."
)


def entra(tamano_actual: int, bytes_nuevos: int, tope_mb: int) -> bool:
    """Si con `bytes_nuevos` la base (o lo que se cuente, como los ZIP
    guardados) sigue por debajo del tope. Pura, para probarla sin base. Un
    tope de 0 (o menos) es "sin freno"."""
    if tope_mb <= 0:
        return True
    return tamano_actual + max(0, bytes_nuevos) <= tope_mb * MB


async def tamano_de_la_base(db: AsyncSession) -> int:
    """Lo que ocupa la base entera en disco (tablas, índices, TOAST), en bytes:
    lo mismo que cuenta Supabase para la cuota."""
    return int((await db.execute(text("SELECT pg_database_size(current_database())"))).scalar_one())


# Las tablas que se pueden compactar: solo las que la plataforma vacía sola
# (la purga de cenefas y la de las validaciones de RRSS). Por nombre fijo,
# nunca algo que venga de afuera.
TABLAS_COMPACTABLES = frozenset({
    "cenefa_jobs",
    "rrss_validaciones", "rrss_validacion_paginas", "rrss_validacion_imagenes",
})


class TablaEnUso(Exception):
    """La tabla se estaba usando y `compactar` no la tocó (ver su docstring)."""


async def compactar(tabla: str) -> tuple[int, int]:
    """Devuelve a la base el lugar que dejaron los archivos borrados de
    `tabla` (VACUUM FULL) y dice cuánto ocupaba antes y después, en bytes.

    Postgres no achica una tabla al borrar: se guarda el lugar para sí, y
    pg_database_size (lo que mira el freno y lo que cuenta Supabase) sigue
    igual. VACUUM FULL la reescribe solo con lo vivo: necesita lugar libre del
    tamaño de lo vivo (chico, si se borraron los archivos) y traba la tabla
    el rato que tarda (segundos). No puede ir dentro de una transacción: va
    en AUTOCOMMIT.

    Nunca espera su turno (SKIP_LOCKED): si alguien está usando la tabla, no
    la toca y avisa con TablaEnUso, para que quien llama lo intente en otra
    pasada. Sin esto, VACUUM FULL esperaba a que terminara, por ejemplo, una
    placa a medio validar, y mientras esperaba frenaba a TODOS los que
    llegaban después, hasta un SELECT: la lista de validaciones y las demás
    placas quedaban trabadas (visto el 26/11/2026 contra Postgres). Un
    lock_timeout no sirve: VACUUM no puede ir en una transacción (SET LOCAL)
    y un SET suelto, con el pooler de Supabase en modo transacción, puede
    caer en otra conexión de la base y quedarle puesto a otro pedido.
    Postgres no dice si la salteó, pero VACUUM FULL siempre deja la tabla en
    un archivo nuevo (pg_relation_filenode): si sigue el mismo, no la tocó."""
    if tabla not in TABLAS_COMPACTABLES:
        raise ValueError(f"No se compacta {tabla!r}")
    from app.core.database import engine  # acá: evita importar la base al cargar el módulo
    estado = text(
        "SELECT pg_total_relation_size(CAST(:t AS regclass)), pg_relation_filenode(CAST(:t AS regclass))"
    )
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        antes, archivo = (await conn.execute(estado, {"t": tabla})).one()
        await conn.execute(text(f'VACUUM (FULL, SKIP_LOCKED) "{tabla}"'))
        despues, archivo_despues = (await conn.execute(estado, {"t": tabla})).one()
    if archivo_despues == archivo:
        raise TablaEnUso(f"{tabla} se estaba usando: no se compactó, para no trabar a quien la usa")
    return int(antes), int(despues)


async def hay_lugar(db: AsyncSession, bytes_nuevos: int) -> bool:
    """Si se pueden guardar `bytes_nuevos` sin pasar el tope. Si no, deja un
    error en el log (con cuánto ocupa) y devuelve False."""
    tope = settings.BASE_TOPE_MB
    if tope <= 0:
        return True
    tamano = await tamano_de_la_base(db)
    if entra(tamano, bytes_nuevos, tope):
        return True
    logger.error(
        "espacio: la base ocupa %.1f MB y el tope es %d MB (BASE_TOPE_MB): se rechazó guardar %.0f KB. "
        "Hay que liberar lugar o subir el tope.",
        tamano / MB, tope, bytes_nuevos / 1024,
    )
    return False


async def exigir_lugar(db: AsyncSession, bytes_nuevos: int) -> None:
    """Como `hay_lugar`, pero corta el pedido con un 507 y el mensaje para la
    persona."""
    if not await hay_lugar(db, bytes_nuevos):
        raise HTTPException(status_code=507, detail=MENSAJE_SIN_LUGAR)
