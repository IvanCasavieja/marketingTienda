"""
scraper_sync.py — Scheduler nocturno de scraping de precios.

Corre todos los días a las 00:10 UY (America/Montevideo).
Flujo: raspa 4 fuentes → SQLite intermedio → upsert en PostgreSQL.
El scraping corre en ThreadPoolExecutor (no bloquea el event loop).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings

logger = logging.getLogger(__name__)

TZ_UY         = ZoneInfo("America/Montevideo")
_REDIS_LOCK   = "scraper:lock"
_REDIS_TTL    = 7 * 3600   # 7h max — el full scan tarda ~2h
_REDIS_LAST   = "scraper:last_run"
_REDIS_STATUS = "scraper:status"
_REDIS_TOTAL  = "scraper:last_total"


def _seconds_until_next_run() -> float:
    """Segundos hasta el próximo HH:MM configurado en zona UY."""
    now = datetime.now(TZ_UY)
    target = now.replace(
        hour=settings.SCRAPER_HOUR,
        minute=settings.SCRAPER_MINUTE,
        second=0,
        microsecond=0,
    )
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


# ---------------------------------------------------------------------------
# Loop público — lo inicia main.py
# ---------------------------------------------------------------------------

async def run_scraper_loop() -> None:
    """Loop perpetuo que arranca con FastAPI en lifespan."""
    h, m = settings.SCRAPER_HOUR, settings.SCRAPER_MINUTE
    logger.info("scraper_sync: scheduler iniciado — diario a las %02d:%02d UY", h, m)

    while True:
        wait = _seconds_until_next_run()
        logger.info("scraper_sync: próximo run en %.0f min (%.1f h)", wait / 60, wait / 3600)
        await asyncio.sleep(wait)

        try:
            await _execute()
        except Exception as exc:
            logger.error("scraper_sync: error en loop: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Trigger manual (desde endpoint de admin)
# ---------------------------------------------------------------------------

async def trigger_manual() -> bool:
    """Lanza el scraper ahora si no hay otro corriendo. Retorna True si se lanzó."""
    from app.core.redis_client import get_redis
    redis = get_redis()
    is_running = await redis.get(_REDIS_STATUS)
    if is_running and is_running.decode() == "running":
        return False
    asyncio.create_task(_execute())
    return True


# ---------------------------------------------------------------------------
# Ejecución real
# ---------------------------------------------------------------------------

async def _execute() -> None:
    from app.core.redis_client import get_redis
    redis = get_redis()

    acquired = await redis.set(_REDIS_LOCK, "1", nx=True, ex=_REDIS_TTL)
    if not acquired:
        logger.info("scraper_sync: lock activo, saltando")
        return

    try:
        await redis.set(_REDIS_STATUS, "running")
        logger.info("scraper_sync: iniciando full scan")

        loop = asyncio.get_event_loop()
        total = await loop.run_in_executor(None, _run_blocking)

        await _sync_to_postgres()

        now = datetime.now(timezone.utc).isoformat()
        await redis.set(_REDIS_LAST, now)
        await redis.set(_REDIS_TOTAL, str(total))
        await redis.set(_REDIS_STATUS, "idle")
        logger.info("scraper_sync: completado — %d productos", total)

    except Exception as exc:
        await redis.set(_REDIS_STATUS, f"error: {str(exc)[:200]}")
        logger.error("scraper_sync: falló: %s", exc, exc_info=True)
        raise
    finally:
        await redis.delete(_REDIS_LOCK)


def _run_blocking() -> int:
    """Corre en ThreadPoolExecutor — no bloquea el event loop."""
    from app.services.scraper.fases import run_full
    return run_full()


async def _sync_to_postgres() -> None:
    """Vuelca SQLite intermedio → PostgreSQL usando el modelo existente."""
    from app.services.scraper import store as sc_store
    from app.core.database import AsyncSessionLocal
    from app.models.producto import Producto
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    productos = sc_store.todos()
    if not productos:
        logger.warning("scraper_sync: SQLite vacío — nada que sincronizar")
        return

    logger.info("scraper_sync: sincronizando %d productos a PostgreSQL", len(productos))
    now  = datetime.now(timezone.utc)
    BATCH = 500

    async with AsyncSessionLocal() as db:
        batches = [productos[i:i + BATCH] for i in range(0, len(productos), BATCH)]
        for i, batch in enumerate(batches, 1):
            rows = [
                {
                    "tienda":        p["tienda"],
                    "url":           p["url"],
                    "nombre":        p.get("nombre"),
                    "precio":        p.get("precio"),
                    "precio_lista":  p.get("precio_lista"),
                    "sku":           p.get("sku"),
                    "barcode":       p.get("barcode"),
                    "marca":         p.get("marca"),
                    "categoria":     p.get("categoria"),
                    "actualizado_en": now,
                }
                for p in batch
            ]
            stmt = pg_insert(Producto).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "tienda":        stmt.excluded.tienda,
                    "nombre":        stmt.excluded.nombre,
                    "precio":        stmt.excluded.precio,
                    "precio_lista":  stmt.excluded.precio_lista,
                    "sku":           stmt.excluded.sku,
                    "barcode":       stmt.excluded.barcode,
                    "marca":         stmt.excluded.marca,
                    "categoria":     stmt.excluded.categoria,
                    "actualizado_en": stmt.excluded.actualizado_en,
                },
            )
            await db.execute(stmt)
            if i % 20 == 0:
                logger.info("scraper_sync: sync %d/%d batches", i, len(batches))
        await db.commit()

    logger.info("scraper_sync: sync completado — %d productos en PostgreSQL", len(productos))


# ---------------------------------------------------------------------------
# Estado público (para el endpoint /precios/scraper/status)
# ---------------------------------------------------------------------------

async def get_status() -> dict:
    from app.core.redis_client import get_redis
    try:
        redis  = get_redis()
        last   = await redis.get(_REDIS_LAST)
        status = await redis.get(_REDIS_STATUS)
        total  = await redis.get(_REDIS_TOTAL)
    except Exception:
        last = status = total = None

    wait     = _seconds_until_next_run()
    next_run = (datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat()

    return {
        "enabled":    settings.SCRAPER_ENABLED,
        "status":     status.decode() if status else "idle",
        "last_run":   last.decode()   if last   else None,
        "last_total": int(total.decode()) if total else None,
        "next_run":   next_run,
        "schedule":   f"Diario a las {settings.SCRAPER_HOUR:02d}:{settings.SCRAPER_MINUTE:02d} UY",
    }
