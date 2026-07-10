"""Alertas de anomalías en campañas de "Medios" (dashboard/canales/campaigns) —
mismo patrón estructural que watchlist_service.py (loop asyncio perpetuo, lock
+ "último run" en Redis, arrancado desde el lifespan de main.py).

Formaliza en el backend, persistido y con notificación real, los thresholds
que hasta ahora solo existían de forma efímera y client-side en
dashboard/page.tsx (ROAS bajo, gasto disparado, etc.) — acá se calculan por
campaña individual comparando la última semana contra la anterior.

Las notificaciones solo llegan a usuarios con acceso a "Medios" (permiso
analytics.view, el mismo que gatea /dashboard, /canales y /campaigns en el
sidebar) — nunca a todos los usuarios."""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.campaign_metric import CampaignMetric
from app.models.notificacion import Notificacion
from app.models.user import User

logger = logging.getLogger(__name__)

_REDIS_LAST_RUN = "campaign_alerts_check:last_run"
_REDIS_LOCK = "campaign_alerts_check:lock"
_REDIS_LOCK_TTL = 1_800  # 30 min — evita locks pegados si el proceso muere

_WINDOW_DAYS = 7   # ventana actual vs. anterior, ambas de 7 días
_DEDUP_DAYS = 7    # no repetir la misma alerta si ya se avisó en los últimos N días

_ROAS_DROP_THRESHOLD = 0.30   # ROAS cae 30% o más
_SPEND_SPIKE_THRESHOLD = 0.50  # gasto sube 50% o más
_CONV_DROP_THRESHOLD = 0.30    # conversiones caen 30% o más


def _interval_hours() -> int:
    return settings.CAMPAIGN_ALERTS_CHECK_INTERVAL_HOURS or 24


async def _aggregate(db, date_from: date, date_to: date) -> dict[tuple[str, str], dict]:
    result = await db.execute(
        select(
            CampaignMetric.platform,
            CampaignMetric.campaign_id,
            CampaignMetric.campaign_name,
            func.sum(CampaignMetric.spend).label("spend"),
            func.sum(CampaignMetric.clicks).label("clicks"),
            func.sum(CampaignMetric.conversions).label("conversions"),
            func.sum(CampaignMetric.revenue).label("revenue"),
        )
        .where(CampaignMetric.date >= date_from, CampaignMetric.date <= date_to)
        .group_by(CampaignMetric.platform, CampaignMetric.campaign_id, CampaignMetric.campaign_name)
    )
    out: dict[tuple[str, str], dict] = {}
    for row in result.all():
        spend = row.spend or 0.0
        revenue = row.revenue or 0.0
        out[(row.platform.value, row.campaign_id)] = {
            "campaign_name": row.campaign_name,
            "spend": spend,
            "clicks": row.clicks or 0,
            "conversions": row.conversions or 0,
            "roas": (revenue / spend) if spend > 0 else 0.0,
        }
    return out


async def _usuarios_con_acceso_medios(db) -> list[User]:
    """dashboard/canales/campaigns comparten el permiso analytics.view en el
    sidebar (ver Sidebar.tsx) — mismo criterio acá para decidir destinatarios."""
    result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
    return [u for u in result.scalars().all() if u.is_superuser or "analytics.view" in (u.permissions or [])]


async def _ya_notificado_recientemente(db, origen_ref: str, desde: datetime) -> bool:
    result = await db.execute(
        select(Notificacion.id)
        .where(Notificacion.origen_ref == origen_ref, Notificacion.created_at >= desde)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _detectar_condiciones(nombre: str, platform: str, cur: dict, prev: dict) -> list[tuple[str, str]]:
    """Devuelve [(tipo, mensaje), ...] — formaliza los thresholds que antes
    solo vivían client-side en dashboard/page.tsx, ahora por campaña."""
    condiciones: list[tuple[str, str]] = []

    if prev["roas"] > 0 and cur["roas"] <= prev["roas"] * (1 - _ROAS_DROP_THRESHOLD):
        caida = (1 - cur["roas"] / prev["roas"]) * 100
        condiciones.append((
            "roas_baja",
            f'El ROAS de "{nombre}" ({platform}) cayó {caida:.0f}% en la última semana — de {prev["roas"]:.2f} a {cur["roas"]:.2f}.',
        ))

    if prev["spend"] > 0 and cur["spend"] >= prev["spend"] * (1 + _SPEND_SPIKE_THRESHOLD):
        suba = (cur["spend"] / prev["spend"] - 1) * 100
        condiciones.append((
            "gasto_sube",
            f'El gasto de "{nombre}" ({platform}) subió {suba:.0f}% en la última semana.',
        ))

    if (
        prev["conversions"] > 0
        and cur["conversions"] <= prev["conversions"] * (1 - _CONV_DROP_THRESHOLD)
        and cur["spend"] >= prev["spend"] * 0.8
    ):
        caida = (1 - cur["conversions"] / prev["conversions"]) * 100
        condiciones.append((
            "conversiones_baja",
            f'Las conversiones de "{nombre}" ({platform}) cayeron {caida:.0f}% sin que bajara el gasto en la misma proporción.',
        ))

    if cur["clicks"] > 0 and cur["conversions"] == 0 and prev["conversions"] > 0:
        condiciones.append((
            "sin_conversiones",
            f'"{nombre}" ({platform}) tuvo clicks pero cero conversiones esta semana — la semana pasada sí convertía.',
        ))

    return condiciones


async def detectar_alertas(db) -> int:
    hoy = date.today()
    actual_desde = hoy - timedelta(days=_WINDOW_DAYS)
    anterior_desde = hoy - timedelta(days=2 * _WINDOW_DAYS)
    anterior_hasta = actual_desde - timedelta(days=1)

    actual = await _aggregate(db, actual_desde, hoy)
    anterior = await _aggregate(db, anterior_desde, anterior_hasta)
    if not actual or not anterior:
        return 0

    usuarios = await _usuarios_con_acceso_medios(db)
    if not usuarios:
        return 0

    dedup_desde = datetime.now(timezone.utc) - timedelta(days=_DEDUP_DAYS)
    alertas_creadas = 0

    for key, cur in actual.items():
        prev = anterior.get(key)
        if not prev:
            continue  # campaña sin historial en el período anterior — nada que comparar

        platform, campaign_id = key
        for tipo, mensaje in _detectar_condiciones(cur["campaign_name"], platform, cur, prev):
            origen_ref = f"{platform}:{campaign_id}:{tipo}"
            if await _ya_notificado_recientemente(db, origen_ref, dedup_desde):
                continue
            for u in usuarios:
                db.add(Notificacion(
                    user_id=u.id, tipo=tipo, mensaje=mensaje,
                    origen_tipo="campaign_alert", origen_ref=origen_ref,
                ))
            alertas_creadas += 1

    return alertas_creadas


async def run_campaign_alerts_loop() -> None:
    """Loop perpetuo. Arranca con FastAPI y corre en background."""
    await _wait_initial()

    while True:
        try:
            await _execute_check()
        except Exception as exc:
            logger.error("campaign_alerts_check: error inesperado en el loop: %s", exc, exc_info=True)
        await asyncio.sleep(_interval_hours() * 3_600)


async def _wait_initial() -> None:
    try:
        redis = get_redis()
        raw = await redis.get(_REDIS_LAST_RUN)
        if raw:
            last_dt = datetime.fromisoformat(raw.decode())
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            wait = max(60, _interval_hours() * 3_600 - elapsed)
            logger.info(
                "campaign_alerts_check: último chequeo hace %.0f min — próximo en %.0f min",
                elapsed / 60, wait / 60,
            )
            await asyncio.sleep(wait)
            return
    except Exception:
        pass
    logger.info("campaign_alerts_check: sin historial — primer chequeo en 5 min")
    await asyncio.sleep(300)


async def _execute_check() -> None:
    redis_ok = False
    try:
        redis = get_redis()
        acquired = await redis.set(_REDIS_LOCK, "1", nx=True, ex=_REDIS_LOCK_TTL)
        if not acquired:
            logger.info("campaign_alerts_check: otro worker ya está corriendo, saltando")
            return
        redis_ok = True
    except Exception:
        pass

    try:
        async with AsyncSessionLocal() as db:
            try:
                alertas = await detectar_alertas(db)
                await db.commit()
                logger.info("campaign_alerts_check completado — alertas nuevas=%d", alertas)
            except Exception as exc:
                await db.rollback()
                logger.error("campaign_alerts_check: error detectando alertas — %s", exc, exc_info=True)

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
