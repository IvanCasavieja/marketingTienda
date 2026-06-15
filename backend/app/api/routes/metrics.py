import json
import logging
import pathlib

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel
from datetime import date
from typing import List, Optional
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.campaign_metric import CampaignMetric
from app.models.platform_connection import Platform
from app.services.metrics_service import sync_platform, get_metrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Meta estático — activo cuando META_DISABLED=True en .env
#
# Cómo volver a conectar Meta:
#   1. Poner META_DISABLED=False en el .env del backend
#   2. Reiniciar el servidor (el token en DB sigue intacto, no se tocó nada)
#   3. Si el token expiró, reconectar desde /settings en la plataforma
# ---------------------------------------------------------------------------

_META_JSON_PATH = pathlib.Path(__file__).parent.parent.parent / "app" / "data" / "meta_campaigns.json"


def _load_meta_json(date_from: date, date_to: date) -> list[dict]:
    """Lee meta_campaigns.json y filtra por rango de fechas."""
    try:
        raw = json.loads(_META_JSON_PATH.read_text(encoding="utf-8"))
        rows = [r for r in raw if "platform" in r and "date" in r]
        return [
            r for r in rows
            if date_from.isoformat() <= r["date"] <= date_to.isoformat()
        ]
    except Exception as exc:
        logger.warning("META_DISABLED: no se pudo leer meta_campaigns.json — %s", exc)
        return []

router = APIRouter(prefix="/metrics", tags=["metrics"])


class SyncRequest(BaseModel):
    platform: Platform
    date_from: date
    date_to: date


class SyncResponse(BaseModel):
    platform: str
    records_saved: int
    status: str = "success"


@router.post("/sync", response_model=SyncResponse)
async def sync_metrics(
    payload: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if settings.DEMO_MODE:
        return SyncResponse(platform=payload.platform.value, records_saved=0, status="demo")

    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Join a team before syncing metrics")

    # Meta desconectado — no llama a la API live
    if settings.META_DISABLED and payload.platform == Platform.META:
        return SyncResponse(platform="meta", records_saved=0, status="disabled")

    try:
        saved = await sync_platform(db, payload.platform, current_user.team_group_id, payload.date_from, payload.date_to)
        return SyncResponse(platform=payload.platform.value, records_saved=saved)
    except ValueError as e:
        msg = str(e)
        if "No active connection" in msg:
            # Plataforma no configurada — no es error, se omite silenciosamente
            return SyncResponse(platform=payload.platform.value, records_saved=0, status="skipped")
        # Error descriptivo del conector (token expirado, permisos, etc.)
        logger.warning("sync %s error: %s", payload.platform.value, msg)
        raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        logger.exception("sync %s unexpected error", payload.platform.value)
        raise HTTPException(status_code=502, detail=f"Error inesperado al sincronizar {payload.platform.value}: {e}")


@router.get("/")
async def get_campaign_metrics(
    date_from: date,
    date_to: date,
    platforms: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if settings.DEMO_MODE:
        from app.services.demo_data import get_demo_metrics_by_day
        platform_list = [p.strip() for p in platforms.split(",")] if platforms else None
        return get_demo_metrics_by_day(date_from, date_to, platform_list)

    if not current_user.team_group_id:
        return []

    try:
        platform_list = [Platform(p.strip()) for p in platforms.split(",")] if platforms else list(Platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid platform: {e}")

    # Si Meta está desconectado, lo excluimos de la query live y agregamos el JSON estático
    meta_rows: list[dict] = []
    if settings.META_DISABLED:
        platform_list = [p for p in platform_list if p != Platform.META]
        if not platforms or "meta" in platforms:
            meta_rows = _load_meta_json(date_from, date_to)

    live_rows = await get_metrics(db, platform_list, current_user.team_group_id, date_from, date_to)
    return live_rows + meta_rows


@router.get("/summary")
async def get_summary(
    date_from: date,
    date_to: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if settings.DEMO_MODE:
        from app.services.demo_data import get_demo_summary
        return get_demo_summary(date_from, date_to)

    if not current_user.team_group_id:
        return []

    # Plataformas a incluir en la query live
    live_platforms = [p for p in list(Platform) if not (settings.META_DISABLED and p == Platform.META)]

    result = await db.execute(
        select(
            CampaignMetric.platform,
            func.sum(CampaignMetric.impressions).label("impressions"),
            func.sum(CampaignMetric.clicks).label("clicks"),
            func.sum(CampaignMetric.spend).label("spend"),
            func.sum(CampaignMetric.conversions).label("conversions"),
            func.sum(CampaignMetric.revenue).label("revenue"),
            func.avg(CampaignMetric.ctr).label("avg_ctr"),
            func.avg(CampaignMetric.roas).label("avg_roas"),
            func.max(CampaignMetric.date).label("last_date"),
        )
        .where(
            and_(
                CampaignMetric.date >= date_from,
                CampaignMetric.date <= date_to,
                CampaignMetric.team_group_id == current_user.team_group_id,
                CampaignMetric.platform.in_(live_platforms),
            )
        )
        .group_by(CampaignMetric.platform)
    )

    rows = result.all()
    live_summary = [
        {
            "platform":    row.platform.value,
            "impressions": int(row.impressions or 0),
            "clicks":      int(row.clicks or 0),
            "spend":       round(float(row.spend or 0), 2),
            "conversions": int(row.conversions or 0),
            "revenue":     round(float(row.revenue or 0), 2),
            "avg_ctr":     round(float(row.avg_ctr or 0), 2),
            "avg_roas":    round(float(row.avg_roas or 0), 2),
            "last_date":   row.last_date.isoformat() if row.last_date else None,
        }
        for row in rows
    ]

    # Agregar resumen de Meta desde JSON si está desconectado
    if settings.META_DISABLED:
        meta_rows = _load_meta_json(date_from, date_to)
        if meta_rows:
            impr  = sum(r.get("impressions", 0) for r in meta_rows)
            clks  = sum(r.get("clicks", 0) for r in meta_rows)
            spnd  = sum(r.get("spend", 0.0) for r in meta_rows)
            convs = sum(r.get("conversions", 0) for r in meta_rows)
            revn  = sum(r.get("revenue", 0.0) for r in meta_rows)
            n     = max(len(meta_rows), 1)
            live_summary.append({
                "platform":    "meta",
                "impressions": impr,
                "clicks":      clks,
                "spend":       round(spnd, 2),
                "conversions": convs,
                "revenue":     round(revn, 2),
                "avg_ctr":     round(sum(r.get("ctr", 0.0) for r in meta_rows) / n, 2),
                "avg_roas":    round(sum(r.get("roas", 0.0) for r in meta_rows) / n, 2),
                "last_date":   max((r["date"] for r in meta_rows), default=None),
            })

    return live_summary


@router.get("/auto-sync/status")
async def auto_sync_status(_: User = Depends(get_current_user)):
    """Estado del auto-sync: último run, próximo run e intervalo configurado."""
    from app.services.auto_sync import get_sync_status
    return await get_sync_status()
