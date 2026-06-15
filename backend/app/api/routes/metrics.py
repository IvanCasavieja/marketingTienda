import logging

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
    return await get_metrics(db, platform_list, current_user.team_group_id, date_from, date_to)


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
            )
        )
        .group_by(CampaignMetric.platform)
    )

    rows = result.all()
    return [
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


@router.get("/auto-sync/status")
async def auto_sync_status(_: User = Depends(get_current_user)):
    """Estado del auto-sync: último run, próximo run e intervalo configurado."""
    from app.services.auto_sync import get_sync_status
    return await get_sync_status()
