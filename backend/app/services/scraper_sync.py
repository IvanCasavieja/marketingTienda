"""
scraper_sync.py — Scheduler nocturno de scraping de precios.

Corre todos los días a las 00:10 UY (America/Montevideo).
Flujo: raspa 4 fuentes → SQLite intermedio → upsert en PostgreSQL.
El scraping corre en ThreadPoolExecutor (no bloquea el event loop).
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import settings

logger = logging.getLogger(__name__)

TZ_UY         = ZoneInfo("America/Montevideo")
_REDIS_LOCK   = "scraper:lock"
_REDIS_TTL    = 7 * 3600   # 7h max — el full scan tarda ~2h
_REDIS_LAST   = "scraper:last_run"
_REDIS_STATUS = "scraper:status"
_REDIS_TOTAL  = "scraper:last_total"

# Lock in-memory — evita scans concurrentes cuando Redis no está disponible
_scan_running: bool = False
_scan_type: str | None = None  # "full" | "gdu" | None


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
# Helpers Redis — silently degradan si Redis no está disponible
# ---------------------------------------------------------------------------

async def _r_get(key: str) -> bytes | None:
    try:
        from app.core.redis_client import get_redis
        return await get_redis().get(key)
    except Exception:
        return None


async def _r_set(key: str, value, **kwargs) -> bool:
    try:
        from app.core.redis_client import get_redis
        return bool(await get_redis().set(key, value, **kwargs))
    except Exception:
        return True  # sin Redis asumimos éxito para no bloquear


async def _r_del(key: str) -> None:
    try:
        from app.core.redis_client import get_redis
        await get_redis().delete(key)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Trigger manual (desde endpoint de admin)
# ---------------------------------------------------------------------------

async def trigger_manual() -> bool:
    """Lanza el scraper ahora si no hay otro corriendo. Retorna True si se lanzó."""
    global _scan_running
    if _scan_running:
        return False
    is_running = await _r_get(_REDIS_STATUS)
    if is_running and is_running.decode() == "running":
        return False
    asyncio.create_task(_execute())
    return True


async def trigger_gdu() -> bool:
    """Lanza un scan de solo GDU (Geant/Disco/Devoto) si no hay otro corriendo."""
    global _scan_running
    if _scan_running:
        return False
    is_running = await _r_get(_REDIS_STATUS)
    if is_running and is_running.decode() == "running":
        return False
    asyncio.create_task(_execute_gdu())
    return True


# ---------------------------------------------------------------------------
# Ejecución real
# ---------------------------------------------------------------------------

async def _execute() -> None:
    global _scan_running, _scan_type
    if _scan_running:
        logger.info("scraper_sync: scan en curso (in-memory), saltando")
        return
    _scan_running = True
    _scan_type = "full"

    acquired = await _r_set(_REDIS_LOCK, "1", nx=True, ex=_REDIS_TTL)

    try:
        await _r_set(_REDIS_STATUS, "running")
        logger.info("scraper_sync: iniciando full scan")

        loop = asyncio.get_event_loop()
        total = await loop.run_in_executor(None, _run_blocking)

        await _sync_to_postgres()
        await _sync_to_historial()

        now = datetime.now(timezone.utc).isoformat()
        await _r_set(_REDIS_LAST, now)
        await _r_set(_REDIS_TOTAL, str(total))
        await _r_set(_REDIS_STATUS, "idle")
        logger.info("scraper_sync: completado — %d productos", total)

    except Exception as exc:
        await _r_set(_REDIS_STATUS, f"error: {str(exc)[:200]}")
        logger.error("scraper_sync: falló: %s", exc, exc_info=True)
        raise
    finally:
        _scan_running = False
        _scan_type = None
        if acquired:
            await _r_del(_REDIS_LOCK)


def _run_blocking() -> int:
    """Corre en ThreadPoolExecutor — no bloquea el event loop."""
    from app.services.scraper.fases import run_full
    return run_full()


async def _execute_gdu() -> None:
    global _scan_running, _scan_type
    if _scan_running:
        logger.info("scraper_sync: scan en curso (in-memory), saltando GDU")
        return
    _scan_running = True
    _scan_type = "gdu"

    acquired = await _r_set(_REDIS_LOCK, "1", nx=True, ex=_REDIS_TTL)

    try:
        await _r_set(_REDIS_STATUS, "running")
        logger.info("scraper_sync: iniciando GDU-only scan (sync incremental por fase)")

        from app.services.scraper import store as sc_store
        loop = asyncio.get_event_loop()

        # Inicio fresco: limpia SQLite y checkpoint
        await loop.run_in_executor(None, sc_store.limpiar)
        _prog = Path(os.environ.get("SCRAPER_DATA_DIR", "/tmp/scraper")) / "progreso_gdu.json"
        if _prog.exists():
            _prog.unlink()

        total_acumulado = 0
        for fase in (1, 2, 3, 4):
            logger.info("scraper_sync: GDU fase %d/4", fase)
            fase_count = await loop.run_in_executor(None, _run_gdu_fase_solo, fase)
            total_acumulado += fase_count

            # Sync a PostgreSQL + historial tras cada fase
            await _sync_to_postgres()
            await _sync_to_historial()
            logger.info("scraper_sync: GDU fase %d synced — %d productos esta fase", fase, fase_count)

            # Limpia SQLite para la siguiente fase (ya persistido en PostgreSQL)
            await loop.run_in_executor(None, sc_store.limpiar)

        now = datetime.now(timezone.utc).isoformat()
        await _r_set(_REDIS_LAST, now)
        await _r_set(_REDIS_TOTAL, str(total_acumulado))
        await _r_set(_REDIS_STATUS, "idle")
        logger.info("scraper_sync: GDU scan completado — %d productos totales", total_acumulado)

    except Exception as exc:
        await _r_set(_REDIS_STATUS, f"error: {str(exc)[:200]}")
        logger.error("scraper_sync: GDU scan falló: %s", exc, exc_info=True)
        raise
    finally:
        _scan_running = False
        _scan_type = None
        if acquired:
            await _r_del(_REDIS_LOCK)


def _run_gdu_fase_solo(fase: int) -> int:
    """Corre una sola fase GDU y retorna cuántos productos quedaron en SQLite."""
    from app.services.scraper.fases import run_gdu_fase
    from app.services.scraper import store
    run_gdu_fase(fase)
    return sum(store.contar().values())


def _run_blocking_gdu() -> int:
    from app.services.scraper.fases import run_gdu_only
    return run_gdu_only()


async def _sync_to_historial() -> None:
    """Guarda snapshot diario en precio_historial (ON CONFLICT DO NOTHING — una fila por url+fecha)."""
    from app.services.scraper import store as sc_store
    from app.core.database import AsyncSessionLocal
    from app.models.precio_historial import PrecioHistorial
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import date

    productos = sc_store.todos()
    if not productos:
        return

    today = date.today()
    logger.info("scraper_sync: guardando historial %s — %d productos", today, len(productos))
    BATCH = 500

    async with AsyncSessionLocal() as db:
        for i in range(0, len(productos), BATCH):
            batch = productos[i:i + BATCH]
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
                    "fecha_scan":    today,
                }
                for p in batch
            ]
            stmt = pg_insert(PrecioHistorial).values(rows)
            stmt = stmt.on_conflict_do_nothing(constraint="uq_historial_url_fecha")
            await db.execute(stmt)
        await db.commit()

    logger.info("scraper_sync: historial %s completado", today)


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


async def get_progress() -> dict:
    """Progreso en tiempo real del scan en curso, leyendo los JSON de checkpoint."""
    _DATA_DIR = Path(os.environ.get("SCRAPER_DATA_DIR", "/tmp/scraper"))
    _PKG_DIR  = Path(__file__).parent / "scraper"

    # Calcular total GDU dinámicamente desde el JSON de categorías
    gdu_total = 831  # fallback: 277 slugs × 3 tiendas
    cats_json = _PKG_DIR / "categorias_gdu.json"
    if cats_json.exists():
        try:
            with open(cats_json, encoding="utf-8") as f:
                mapeo = json.load(f)
            vistos: set = set()
            for slugs in mapeo.values():
                for s in slugs:
                    vistos.add(s)
            gdu_total = len(vistos) * 3
        except Exception:
            pass

    result: dict = {
        "running":   _scan_running,
        "scan_type": _scan_type,
        "gdu": {"completados": 0, "total": gdu_total, "guardados": 0, "pct": 0.0},
    }

    prog_path = _DATA_DIR / "progreso_gdu.json"
    if prog_path.exists():
        try:
            with open(prog_path, encoding="utf-8") as f:
                prog = json.load(f)
            completados = len(prog.get("completados", []))
            guardados   = prog.get("total_guardados", 0)
            result["gdu"]["completados"] = completados
            result["gdu"]["guardados"]   = guardados
            result["gdu"]["pct"] = round(completados / gdu_total * 100, 1) if gdu_total else 0.0
        except Exception:
            pass

    return result
