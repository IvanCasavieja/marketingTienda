"""Auto-sync de métricas — sincroniza todas las plataformas activas cada N horas."""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.campaign_metric import CampaignMetric
from app.models.platform_connection import PlatformConnection
from app.services.metrics_service import sync_platform

from app.core.config import settings

logger = logging.getLogger(__name__)

SYNC_LOOKBACK_DAYS = 7

def _interval_hours() -> int:
    return settings.SYNC_INTERVAL_HOURS or 6

_REDIS_LAST_RUN = "auto_sync:last_run"
_REDIS_LOCK     = "auto_sync:lock"
_REDIS_LOCK_TTL = 1_800  # 30 min — evita locks pegados si el proceso muere


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

async def run_auto_sync_loop() -> None:
    """Loop perpetuo. Arranca con FastAPI y corre en background."""
    await _wait_initial()

    while True:
        try:
            await _execute_sync()
        except Exception as exc:
            logger.error("auto_sync: error inesperado en el loop: %s", exc, exc_info=True)
        await asyncio.sleep(_interval_hours() * 3_600)


async def _wait_initial() -> None:
    """Cuánto esperar antes del primer sync del proceso. Se apoya en
    CampaignMetric.synced_at (Postgres) en vez de Redis -- mismo bug y mismo
    fix que watchlist_service.py (ver su _wait_initial): Redis no está
    provisionado en Render, así que el GET fallaba siempre y esta espera
    caía siempre a la rama de "sin historial, 2 minutos", ignorando cuánto
    hacía del último sync real. En el free tier el proceso se reinicia
    seguido (duerme por inactividad, arranca de nuevo con el próximo
    request) -- sin este chequeo contra un lugar que sobrevive al reinicio,
    SYNC_INTERVAL_HOURS nunca se respetaba de verdad, y un reinicio seguido
    podía disparar syncs de más contra las APIs reales de Meta/Google
    Ads/TikTok/DV360, gastando cuota sin necesidad."""
    try:
        async with AsyncSessionLocal() as db:
            last_dt = (await db.execute(select(func.max(CampaignMetric.synced_at)))).scalar_one_or_none()
        if last_dt:
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            wait = max(60, _interval_hours() * 3_600 - elapsed)
            logger.info(
                "auto_sync: último sync hace %.0f min — próximo en %.0f min",
                elapsed / 60, wait / 60,
            )
            await asyncio.sleep(wait)
            return
    except Exception:
        pass
    # Sin historial: arrancar 2 minutos después del startup
    logger.info("auto_sync: sin historial — primer sync en 2 min")
    await asyncio.sleep(120)


# ---------------------------------------------------------------------------
# Ejecución del sync
# ---------------------------------------------------------------------------

async def _execute_sync() -> None:
    """Sincroniza todas las plataformas activas. Usa lock Redis si está disponible."""
    # Redis es opcional — si no está disponible, corremos igual sin lock distribuido.
    redis_ok = False
    try:
        redis = get_redis()
        acquired = await redis.set(_REDIS_LOCK, "1", nx=True, ex=_REDIS_LOCK_TTL)
        if not acquired:
            logger.info("auto_sync: otro worker ya está corriendo, saltando")
            return
        redis_ok = True
    except Exception:
        pass  # Sin Redis: continuamos sin lock

    try:
        platforms = await _get_active_platforms()
        if not platforms:
            logger.info("auto_sync: no hay plataformas conectadas")
            return

        date_to   = date.today()
        date_from = date_to - timedelta(days=SYNC_LOOKBACK_DAYS)

        synced = errors = 0
        for platform in platforms:
            try:
                async with AsyncSessionLocal() as db:
                    count = await sync_platform(db, platform, date_from, date_to)
                    await db.commit()
                synced += count
                logger.info("auto_sync OK  platform=%-12s rows=%d", platform.value, count)
            except Exception as exc:
                errors += 1
                logger.warning("auto_sync ERR platform=%-12s: %s", platform.value, exc)

        logger.info("auto_sync completado — rows=%d errors=%d", synced, errors)
        if redis_ok:
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                await redis.set(_REDIS_LAST_RUN, now_iso)
            except Exception:
                pass

    finally:
        if redis_ok:
            try:
                await redis.delete(_REDIS_LOCK)
            except Exception:
                pass


async def _get_active_platforms() -> list:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PlatformConnection.platform)
            .where(PlatformConnection.is_active == True)
            .distinct()
        )
        return [row[0] for row in result.all()]


# ---------------------------------------------------------------------------
# Estado (para el endpoint /metrics/auto-sync/status)
# ---------------------------------------------------------------------------

async def get_sync_status() -> dict:
    try:
        redis = get_redis()
        raw   = await redis.get(_REDIS_LAST_RUN)
    except Exception:
        raw = None

    interval = _interval_hours()

    if not raw:
        return {
            "last_run":       None,
            "next_run":       None,
            "interval_hours": interval,
            "active":         interval > 0,
        }

    last_dt = datetime.fromisoformat(raw.decode())
    next_dt = last_dt + timedelta(hours=interval)

    return {
        "last_run":       last_dt.isoformat(),
        "next_run":       next_dt.isoformat(),
        "interval_hours": interval,
        "active":         interval > 0,
    }
