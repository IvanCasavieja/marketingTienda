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

import asyncio
import logging
import time

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


# Las tablas que se pueden compactar: las que la plataforma vacía sola (la
# purga de cenefas) y las de Clientes VIP, que cada carga reemplaza (26/11/2026:
# recargar 2025 y enero-octubre 2026 dejó 22 MB de filas viejas). Por nombre
# fijo, nunca algo que venga de afuera.
TABLAS_COMPACTABLES = frozenset({
    "cenefa_jobs", "vip_cliente_mes", "vip_clientes", "vip_mes_dimension", "vip_detalle",
})


class TablaEnUso(RuntimeError):
    """La tabla estaba en uso y no se compactó: queda para la próxima."""


async def compactar(tabla: str) -> tuple[int, int]:
    """Devuelve a la base el lugar que dejaron las filas borradas o
    reemplazadas de `tabla` (VACUUM FULL) y dice cuánto ocupaba antes y
    después, en bytes.

    Postgres no achica una tabla al borrar: se guarda el lugar para sí, y
    pg_database_size (lo que mira el freno y lo que cuenta Supabase) sigue
    igual. VACUUM FULL la reescribe solo con lo vivo: necesita lugar libre del
    tamaño de lo vivo y traba la tabla (hasta las lecturas) el rato que tarda,
    segundos. No puede ir dentro de una transacción: va en AUTOCOMMIT.

    Va con SKIP_LOCKED: si alguien está usando la tabla no espera, porque
    mientras esperara su turno todos los que llegaran detrás (una pantalla
    abriéndose) quedarían colgados. Es un lock_timeout de cero que no depende
    de la sesión: con el pooler de Supabase en modo transacción un `SET
    lock_timeout` puede ir a una conexión y el VACUUM a otra, y SET LOCAL
    necesita una transacción. En ese caso levanta TablaEnUso. Se sabe porque
    el archivo de la tabla (pg_relation_filenode) sigue siendo el mismo:
    VACUUM FULL siempre escribe uno nuevo."""
    if tabla not in TABLAS_COMPACTABLES:
        raise ValueError(f"No se compacta {tabla!r}")
    from app.core.database import engine  # acá: evita importar la base al cargar el módulo
    medir = text("SELECT pg_total_relation_size(CAST(:t AS regclass)), pg_relation_filenode(CAST(:t AS regclass))")
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        antes, archivo = (await conn.execute(medir, {"t": tabla})).one()
        await conn.execute(text(f'VACUUM (FULL, SKIP_LOCKED) "{tabla}"'))
        despues, archivo_nuevo = (await conn.execute(medir, {"t": tabla})).one()
    if archivo_nuevo == archivo:
        raise TablaEnUso(f"{tabla} estaba en uso: se compacta la próxima vez")
    return int(antes), int(despues)


# Cuántas veces y cada cuánto se reintenta una tabla que estaba en uso. Un
# pedido común la suelta en milisegundos; a los 15 segundos se deja.
INTENTOS_AL_COMPACTAR = 4
PAUSA_AL_COMPACTAR = 5.0
# Hasta cuánto se espera a que terminen las transacciones de antes del cambio.
ESPERA_ANTES_DE_COMPACTAR = 30.0

# Si ya terminó toda transacción que podía ver las filas viejas de la
# transacción :xid. VACUUM FULL no saca una fila que alguien todavía puede ver:
# la copia igual, y la tabla queda del mismo tamaño. La puede ver una lectura
# que empezó antes del cambio y sigue abierta (un pedido a mitad de camino), y
# también cualquier escritura de antes, aunque sea de otra base del servidor,
# porque la foto que toma el VACUUM arranca en la más vieja que sigue abierta.
# El vacuum automático no cuenta (Postgres lo ignora para esto).
_NADIE_VE_LO_VIEJO = text("""
    SELECT txid_snapshot_xmin(txid_current_snapshot()) > CAST(:xid AS bigint)
       AND NOT EXISTS (
            SELECT 1 FROM pg_stat_activity
             WHERE datname = current_database() AND pid <> pg_backend_pid()
               AND backend_type <> 'autovacuum worker' AND backend_xmin IS NOT NULL
               AND age(backend_xmin) >= age(CAST(CAST(CAST(:xid AS bigint) % 4294967296 AS text) AS xid)))
""")


async def transaccion_actual(db: AsyncSession) -> int:
    """El número de la transacción en curso: el que se le pasa a
    `compactar_en_segundo_plano` después de borrar o reemplazar filas."""
    return int((await db.execute(text("SELECT txid_current()"))).scalar_one())


async def esperar_que_nadie_vea_lo_viejo(xid: int, segundos: float = ESPERA_ANTES_DE_COMPACTAR) -> bool:
    """Espera a que terminen las transacciones que podían ver lo que cambió
    la transacción `xid` (ver _NADIE_VE_LO_VIEJO). False si a los `segundos`
    sigue alguna abierta. Un pedido común termina en milisegundos."""
    from app.core.database import engine
    hasta = time.monotonic() + segundos
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        while not (await conn.execute(_NADIE_VE_LO_VIEJO, {"xid": xid})).scalar_one():
            if time.monotonic() >= hasta:
                return False
            await asyncio.sleep(0.5)
    return True


async def compactar_en_segundo_plano(tablas: list[str], desde_xid: int | None = None) -> dict[str, tuple[int, int] | None]:
    """Compacta cada tabla de `tablas`, una por una, para usar después de
    responder (BackgroundTasks): nadie espera por esto y nada falla por esto.
    `desde_xid` es la transacción que borró o reemplazó filas
    (`transaccion_actual`): primero se espera a que nadie pueda verlas, porque
    si no la compactación no devuelve nada. Si una tabla está en uso, la
    reintenta unas veces; si sigue en uso o algo falla, queda anotado en el log
    y sigue con la próxima. Devuelve, de cada una, (antes, después) en bytes, o
    None si no se pudo."""
    resultado: dict[str, tuple[int, int] | None] = {}
    if desde_xid is not None:
        try:
            if not await esperar_que_nadie_vea_lo_viejo(desde_xid):
                logger.warning("espacio: sigue abierta una transacción de antes del cambio: "
                               "se compacta igual y puede quedar lugar sin devolver")
        except Exception as exc:
            logger.error("espacio: no se pudo esperar antes de compactar -- %s", exc)
    for tabla in tablas:
        resultado[tabla] = None
        for intento in range(INTENTOS_AL_COMPACTAR):
            if intento:
                await asyncio.sleep(PAUSA_AL_COMPACTAR)
            try:
                antes, despues = await compactar(tabla)
            except TablaEnUso:
                continue
            except Exception as exc:
                logger.error("espacio: no se pudo compactar %s -- %s", tabla, exc)
                break
            resultado[tabla] = (antes, despues)
            logger.info("espacio: %s compactada de %.1f a %.1f MB", tabla, antes / MB, despues / MB)
            break
        else:
            logger.warning("espacio: %s estuvo en uso y no se compactó: queda para la próxima", tabla)
    return resultado


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
