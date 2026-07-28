"""Chequeo diario de precios de las listas de monitoreo — mismo patrón
estructural que auto_sync.py (loop asyncio perpetuo, lock + "último run" en
Redis, arrancado desde el lifespan de main.py). No hay APScheduler/Celery ni
un servicio de cron separado en Render: un solo proceso, un loop en background.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.watchlist import Watchlist
from app.models.watchlist_item import WatchlistItem
from app.models.watchlist_precio_historial import WatchlistPrecioHistorial
from app.models.watchlist_share import WatchlistShare
from app.models.notificacion import Notificacion
from app.services.scraper.live_search import (
    buscar_tata, buscar_eldorado, buscar_gdu,
    buscar_farmashop, buscar_botiga, buscar_pigalle,
    buscar_blackdog, buscar_electrohogar, buscar_covercompany,
    buscar_dimm, buscar_stienda, buscar_fama,
)
from app.services.scraper.adapters import ProductRecord

logger = logging.getLogger(__name__)

# Mismo dispatch por cadena que ya arma buscar_todas en live_search.py — acá se
# usa para re-invocar SOLO el adapter de la cadena de un item puntual, en vez
# de correr las 13 cadenas por cada producto seguido.
_BUSCAR_POR_CADENA = {
    "Ta-Ta": buscar_tata,
    "ElDorado": buscar_eldorado,
    "Disco": buscar_gdu, "Devoto": buscar_gdu, "Geant": buscar_gdu,
    "FarmaShop": buscar_farmashop,
    "Botiga": buscar_botiga,
    "Pigalle": buscar_pigalle,
    "BlackDog": buscar_blackdog,
    "Electrohogar": buscar_electrohogar,
    "CoverCompany": buscar_covercompany,
    "DIMM": buscar_dimm,
    "Stienda": buscar_stienda,
    "Fama": buscar_fama,
}

_REDIS_LAST_RUN = "watchlist_check:last_run"
_REDIS_LOCK = "watchlist_check:lock"
_REDIS_LOCK_TTL = 1_800  # 30 min — evita locks pegados si el proceso muere


def _interval_hours() -> int:
    return settings.WATCHLIST_CHECK_INTERVAL_HOURS or 24


async def chequear_item(item: WatchlistItem) -> ProductRecord | None:
    """Re-busca el producto de un item guardado invocando el adapter de su
    propia cadena con el término de búsqueda original. Match por sku si el
    item lo tiene; si no (DIMM/Stienda, únicas 2 de 13 cadenas sin sku en el
    scraper), por nombre exacto (case-insensitive). None si ya no aparece
    (descontinuado o renombrado).

    Ta-Ta/ElDorado/GDU devuelven una fila por (producto × sucursal) — el mismo
    sku puede aparecer ~15-17 veces con precios distintos. Si el item tiene
    sucursal_id guardado (chains multi-sucursal), se filtra primero por esa
    sucursal exacta antes de matchear por sku/nombre — de lo contrario el
    chequeo terminaría comparando sucursales distintas entre corridas y
    generando falsos "cambios de precio". Si la sucursal seguida ya no
    aparece en absoluto, se trata igual que "producto no encontrado" (no se
    cae a otra sucursal)."""
    buscar_fn = _BUSCAR_POR_CADENA.get(item.tienda)
    if not buscar_fn:
        logger.warning("watchlist: cadena desconocida '%s' para item %s", item.tienda, item.id)
        return None

    try:
        resultados = await asyncio.to_thread(buscar_fn, item.termino_busqueda)
    except Exception as exc:
        logger.warning("watchlist: error re-buscando item %s (%s) — %s", item.id, item.tienda, exc)
        return None

    candidatos = resultados
    if item.sucursal_id:
        candidatos = [r for r in candidatos if r.sucursal_id == item.sucursal_id]
        if not candidatos:
            return None

    if item.sku:
        for r in candidatos:
            if r.sku == item.sku:
                return r
        return None

    nombre_lower = item.nombre.strip().lower()
    for r in candidatos:
        if (r.nombre or "").strip().lower() == nombre_lower:
            return r
    return None


async def _procesar_item(db, item: WatchlistItem) -> None:
    encontrado = await chequear_item(item)
    item.ultimo_chequeo = datetime.now(timezone.utc)

    if encontrado is None or encontrado.precio is None:
        return  # no se encontró más — no se notifica, se deja el último precio conocido

    precio_anterior = item.precio_actual
    moneda_anterior = item.moneda

    if encontrado.precio == precio_anterior and encontrado.moneda == moneda_anterior:
        return  # sin cambios

    if encontrado.moneda == moneda_anterior:
        tipo = "precio_sube" if encontrado.precio > precio_anterior else "precio_baja"
    else:
        tipo = "precio_cambio"  # cambió la moneda — no comparable numéricamente

    db.add(WatchlistPrecioHistorial(
        watchlist_item_id=item.id,
        precio=encontrado.precio,
        moneda=encontrado.moneda,
    ))

    item.precio_actual = encontrado.precio
    item.moneda = encontrado.moneda

    # user_id vive en Watchlist, no en WatchlistItem — se resuelve antes de
    # pedirle la explicación a la IA para poder loguear el uso a nombre del dueño.
    wl_result = await db.execute(select(Watchlist).where(Watchlist.id == item.watchlist_id))
    wl = wl_result.scalar_one_or_none()
    if not wl:
        return

    try:
        from app.services.don_tino_precios import explicar_cambio_precio
        mensaje = await explicar_cambio_precio(
            item.tienda, item.nombre, precio_anterior, encontrado.precio, encontrado.moneda,
            db=db, user_id=wl.user_id,
        )
    except Exception as exc:
        logger.warning("watchlist: fallo generando explicación IA para item %s — %s", item.id, exc)
        simbolo = "U$S" if encontrado.moneda == "USD" else "$"
        mensaje = (
            f"{item.nombre} ({item.tienda}) cambió de {simbolo}{precio_anterior:.2f} "
            f"a {simbolo}{encontrado.precio:.2f}."
        )

    # Notifica al dueño y a todos los usuarios con los que la lista está
    # compartida — mismo patrón de fan-out que campaign_alerts_service.py,
    # cada colaborador recibe "como si fuera suya" (mismo watchlist_item_id).
    shares_result = await db.execute(select(WatchlistShare.user_id).where(WatchlistShare.watchlist_id == wl.id))
    destinatarios = {wl.user_id, *shares_result.scalars().all()}

    for user_id in destinatarios:
        db.add(Notificacion(
            user_id=user_id,
            tipo=tipo,
            mensaje=mensaje,
            watchlist_item_id=item.id,
        ))


async def run_watchlist_check_loop() -> None:
    """Loop perpetuo. Arranca con FastAPI y corre en background."""
    await _wait_initial()

    while True:
        try:
            await _execute_check()
        except Exception as exc:
            logger.error("watchlist_check: error inesperado en el loop: %s", exc, exc_info=True)
        await asyncio.sleep(_interval_hours() * 3_600)


async def _wait_initial() -> None:
    """Cuánto esperar antes del primer chequeo del proceso. Se apoya en
    WatchlistItem.ultimo_chequeo (Postgres) en vez de Redis — Redis no está
    provisionado en Render, así que un GET ahí siempre fallaba y esta espera
    caía siempre a la rama de "sin historial, 5 minutos", ignorando cuánto
    hacía del último chequeo real. En el free tier el proceso se reinicia
    seguido (duerme por inactividad y arranca de nuevo con el próximo
    request) — sin este chequeo contra un lugar que sobrevive al reinicio,
    el intervalo configurado (WATCHLIST_CHECK_INTERVAL_HOURS, 24hs por
    default) nunca se respetaba de verdad."""
    try:
        async with AsyncSessionLocal() as db:
            last_dt = (await db.execute(select(func.max(WatchlistItem.ultimo_chequeo)))).scalar_one_or_none()
        if last_dt:
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            wait = max(60, _interval_hours() * 3_600 - elapsed)
            logger.info(
                "watchlist_check: último chequeo hace %.0f min — próximo en %.0f min",
                elapsed / 60, wait / 60,
            )
            await asyncio.sleep(wait)
            return
    except Exception:
        pass
    logger.info("watchlist_check: sin historial — primer chequeo en 5 min")
    await asyncio.sleep(300)


async def _execute_check() -> None:
    redis_ok = False
    try:
        redis = get_redis()
        acquired = await redis.set(_REDIS_LOCK, "1", nx=True, ex=_REDIS_LOCK_TTL)
        if not acquired:
            logger.info("watchlist_check: otro worker ya está corriendo, saltando")
            return
        redis_ok = True
    except Exception:
        pass

    try:
        async with AsyncSessionLocal() as db:
            hoy = datetime.now(timezone.utc).date()
            finalizadas = await db.execute(
                update(Watchlist)
                .where(Watchlist.estado == "activa", Watchlist.fecha_fin.is_not(None), Watchlist.fecha_fin < hoy)
                .values(estado="finalizada")
            )
            await db.commit()
            if finalizadas.rowcount:
                logger.info("watchlist_check: %d lista(s) pasaron a finalizada por vencimiento", finalizadas.rowcount)

            # Listas finalizadas dejan de scrapear/notificar — ver el estado
            # como un pausar, no un borrar (el historial de precios sigue
            # intacto para el Excel de la sección "Finalizadas").
            result = await db.execute(
                select(WatchlistItem)
                .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
                .where(Watchlist.estado == "activa")
            )
            items = result.scalars().all()

            chequeados = cambios = errores = 0
            for item in items:
                try:
                    antes = item.precio_actual
                    await _procesar_item(db, item)
                    await db.commit()
                    chequeados += 1
                    if item.precio_actual != antes:
                        cambios += 1
                except Exception as exc:
                    errores += 1
                    await db.rollback()
                    logger.warning("watchlist_check: error procesando item %s — %s", item.id, exc)

            logger.info(
                "watchlist_check completado — chequeados=%d cambios=%d errores=%d",
                chequeados, cambios, errores,
            )

        if redis_ok:
            try:
                await redis.set(_REDIS_LAST_RUN, datetime.now(timezone.utc).isoformat())
            except Exception:
                pass
    finally:
        if redis_ok:
            try:
                await redis.delete(_REDIS_LOCK)
            except Exception:
                pass
