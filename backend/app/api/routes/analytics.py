from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import date
from typing import List
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.ai_analysis import AIAnalysis
from app.models.platform_connection import Platform
from app.services.metrics_service import get_metrics
from app.services.claude_service import ANALYSIS_HANDLERS
from app.connectors.sfmc import SFMCConnector

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalysisRequest(BaseModel):
    platforms: List[Platform]
    date_from: date
    date_to: date
    analysis_type: str = "full_report"


@router.post("/analyze")
async def analyze(
    payload: AnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Join a team before running analysis")

    handler = ANALYSIS_HANDLERS.get(payload.analysis_type)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown analysis type: {payload.analysis_type}")

    metrics = await get_metrics(db, payload.platforms, current_user.team_group_id, payload.date_from, payload.date_to)

    if payload.analysis_type == "full_report":
        email_data, whatsapp_data = [], []
        if settings.SFMC_CLIENT_ID:
            try:
                sfmc = SFMCConnector(
                    client_id=settings.SFMC_CLIENT_ID,
                    client_secret=settings.SFMC_CLIENT_SECRET,
                    subdomain=settings.SFMC_SUBDOMAIN,
                    account_id=settings.SFMC_ACCOUNT_ID,
                )
                raw_email = await sfmc.fetch_email_performance(payload.date_from, payload.date_to)
                email_data = sfmc.normalize_email(raw_email)
                raw_wa = await sfmc.fetch_whatsapp_performance(payload.date_from, payload.date_to)
                whatsapp_data = sfmc.normalize_whatsapp(raw_wa)
            except Exception:
                pass
        result = await handler(metrics, email_data, whatsapp_data, payload.date_from, payload.date_to)
    else:
        result = await handler(metrics, payload.date_from, payload.date_to)

    analysis = AIAnalysis(
        user_id=current_user.id,
        analysis_type=result["analysis_type"],
        platforms=[p.value for p in payload.platforms],
        date_from=payload.date_from,
        date_to=payload.date_to,
        prompt_used=result["analysis_type"],
        result=result["result"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
    )
    db.add(analysis)
    await db.flush()

    return {
        "id": analysis.id,
        "analysis_type": analysis.analysis_type,
        "result": analysis.result,
        "tokens_used": analysis.input_tokens + analysis.output_tokens,
    }


@router.get("/history")
async def get_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AIAnalysis)
        .where(AIAnalysis.user_id == current_user.id)
        .order_by(AIAnalysis.created_at.desc())
        .limit(50)
    )
    analyses = result.scalars().all()
    return [
        {
            "id": a.id,
            "analysis_type": a.analysis_type,
            "platforms": a.platforms,
            "date_from": str(a.date_from),
            "date_to": str(a.date_to),
            "created_at": a.created_at.isoformat(),
        }
        for a in analyses
    ]


@router.get("/history/{analysis_id}")
async def get_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AIAnalysis).where(AIAnalysis.id == analysis_id, AIAnalysis.user_id == current_user.id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return {
        "id": analysis.id,
        "analysis_type": analysis.analysis_type,
        "platforms": analysis.platforms,
        "date_from": str(analysis.date_from),
        "date_to": str(analysis.date_to),
        "result": analysis.result,
        "input_tokens": analysis.input_tokens,
        "output_tokens": analysis.output_tokens,
        "created_at": analysis.created_at.isoformat(),
    }
