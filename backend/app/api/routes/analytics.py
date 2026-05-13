from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import date
from typing import List
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.ai_analysis import AIAnalysis
from app.models.platform_connection import Platform
from app.services.metrics_service import get_metrics
from app.services.claude_service import ANALYSIS_HANDLERS

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
    handler = ANALYSIS_HANDLERS.get(payload.analysis_type)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown analysis type: {payload.analysis_type}")

    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)

    if payload.analysis_type == "full_report":
        result = await handler(metrics, [], [], payload.date_from, payload.date_to)
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
