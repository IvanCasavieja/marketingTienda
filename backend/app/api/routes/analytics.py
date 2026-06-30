import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import date
from typing import List, Optional
from app.core.database import get_db, AsyncSessionLocal
from app.core.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.ai_analysis import AIAnalysis
from app.models.platform_connection import Platform
from app.services.metrics_service import get_metrics
from app.services.claude_service import ANALYSIS_HANDLERS, stream_analysis
from app.services.debate_service import run_debate, stream_debate, stream_debate_turn, stream_llama_verdict
from app.connectors.sfmc import SFMCConnector

_ALL_HANDLERS = {**ANALYSIS_HANDLERS, "debate": run_debate}

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalysisRequest(BaseModel):
    platforms: List[Platform]
    date_from: date
    date_to: date
    analysis_type: str = "full_report"
    user_prompt: str = ""


class DebateTurnRequest(BaseModel):
    platforms: List[Platform]
    date_from: date
    date_to: date
    user_message: str
    history: List[dict] = []
    conversation_id: Optional[int] = None
    date_from_2: Optional[date] = None
    date_to_2: Optional[date] = None


class DebateVerdictRequest(BaseModel):
    platforms: List[Platform]
    date_from: date
    date_to: date
    history: List[dict] = []
    conversation_id: Optional[int] = None
    date_from_2: Optional[date] = None
    date_to_2: Optional[date] = None


@router.post("/analyze")
async def analyze(
    payload: AnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    handler = _ALL_HANDLERS.get(payload.analysis_type)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown analysis type: {payload.analysis_type}")

    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)

    try:
        if payload.analysis_type in ("full_report", "debate"):
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
                except Exception as sfmc_err:
                    logger.warning("SFMC data unavailable, proceeding without it: %s", sfmc_err)
            if payload.analysis_type == "debate":
                result = await handler(metrics, email_data, whatsapp_data, payload.date_from, payload.date_to, payload.user_prompt)
            else:
                result = await handler(metrics, email_data, whatsapp_data, payload.date_from, payload.date_to)
        else:
            result = await handler(metrics, payload.date_from, payload.date_to)
    except RuntimeError as e:
        logger.error("Analysis handler failed: %s", e)
        raise HTTPException(status_code=502, detail="Analysis service temporarily unavailable")

    platforms_str = ", ".join(p.value for p in payload.platforms)
    analysis = AIAnalysis(
        user_id=current_user.id,
        analysis_type=result["analysis_type"],
        platforms=[p.value for p in payload.platforms],
        date_from=payload.date_from,
        date_to=payload.date_to,
        prompt_used=f"{result['analysis_type']} | platforms: {platforms_str} | {payload.date_from} to {payload.date_to}",
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


STREAMABLE_TYPES = {"full_report", "anomaly_detection", "optimization", "cross_platform"}


@router.post("/analyze/stream")
async def analyze_stream(
    payload: AnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.analysis_type not in STREAMABLE_TYPES:
        raise HTTPException(status_code=400, detail="Use /analyze for debate analysis")

    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)

    email_data, whatsapp_data = [], []
    if payload.analysis_type == "full_report" and settings.SFMC_CLIENT_ID:
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
        except Exception as sfmc_err:
            logger.warning("SFMC data unavailable for stream, proceeding without it: %s", sfmc_err)

    user_id = current_user.id
    analysis_type = payload.analysis_type
    platforms_list = [p.value for p in payload.platforms]
    platforms_str = ", ".join(platforms_list)
    date_from = payload.date_from
    date_to = payload.date_to

    async def event_stream():
        full_text = ""
        usage: dict = {}
        try:
            async for chunk in stream_analysis(
                analysis_type, metrics, email_data, whatsapp_data, date_from, date_to
            ):
                if chunk["type"] == "text":
                    full_text += chunk["text"]
                    yield f"data: {json.dumps({'text': chunk['text']})}\n\n"
                elif chunk["type"] == "done":
                    usage = chunk
        except RuntimeError as e:
            logger.error("Streaming analysis failed: %s", e)
            yield f"data: {json.dumps({'error': 'Analysis service temporarily unavailable'})}\n\n"
            return

        async with AsyncSessionLocal() as save_db:
            analysis = AIAnalysis(
                user_id=user_id,
                analysis_type=analysis_type,
                platforms=platforms_list,
                date_from=date_from,
                date_to=date_to,
                prompt_used=f"{analysis_type} | platforms: {platforms_str} | {date_from} to {date_to}",
                result=full_text,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
            save_db.add(analysis)
            await save_db.commit()
            await save_db.refresh(analysis)
            yield f"data: {json.dumps({'done': True, 'id': analysis.id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analyze/debate/stream")
async def debate_stream(
    payload: AnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)

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
        except Exception as sfmc_err:
            logger.warning("SFMC unavailable for debate stream: %s", sfmc_err)

    user_id = current_user.id
    platforms_list = [p.value for p in payload.platforms]
    platforms_str = ", ".join(platforms_list)
    date_from = payload.date_from
    date_to = payload.date_to

    user_prompt = payload.user_prompt

    async def event_stream():
        all_messages = []
        total_tokens = 0
        try:
            async for event in stream_debate(metrics, email_data, whatsapp_data, date_from, date_to, user_prompt):
                if event.get("type") == "message":
                    all_messages.append({
                        "speaker": event["speaker"],
                        "round":   event["round"],
                        "role":    event["role"],
                        "content": event["content"],
                    })
                elif event.get("type") == "tokens":
                    total_tokens = event.get("total", 0)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except RuntimeError as exc:
            logger.error("Debate stream failed: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
            return

        async with AsyncSessionLocal() as save_db:
            analysis = AIAnalysis(
                user_id=user_id,
                analysis_type="debate",
                platforms=platforms_list,
                date_from=date_from,
                date_to=date_to,
                prompt_used=f"debate | platforms: {platforms_str} | {date_from} to {date_to}",
                result=json.dumps({"debate": all_messages}, ensure_ascii=False),
                input_tokens=total_tokens,
                output_tokens=0,
            )
            save_db.add(analysis)
            await save_db.commit()
            await save_db.refresh(analysis)
            yield f"data: {json.dumps({'type': 'done', 'id': analysis.id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/debate/turn")
async def debate_turn(
    payload: DebateTurnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Single conversational turn: Claude first, then ChatGPT. Auto-saves after every turn."""
    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)
    metrics_2: list = []
    if payload.date_from_2 and payload.date_to_2:
        metrics_2 = await get_metrics(db, payload.platforms, payload.date_from_2, payload.date_to_2)

    email_data, whatsapp_data = [], []
    if settings.SFMC_CLIENT_ID:
        try:
            sfmc = SFMCConnector(
                client_id=settings.SFMC_CLIENT_ID,
                client_secret=settings.SFMC_CLIENT_SECRET,
                subdomain=settings.SFMC_SUBDOMAIN,
                account_id=settings.SFMC_ACCOUNT_ID,
            )
            email_data    = sfmc.normalize_email(await sfmc.fetch_email_performance(payload.date_from, payload.date_to))
            whatsapp_data = sfmc.normalize_whatsapp(await sfmc.fetch_whatsapp_performance(payload.date_from, payload.date_to))
        except Exception as e:
            logger.warning("SFMC unavailable for debate turn: %s", e)

    user_id        = current_user.id
    platforms_list = [p.value for p in payload.platforms]
    platforms_str  = ", ".join(platforms_list)

    async def event_stream():
        new_messages: list = []
        turn_tokens = 0
        try:
            async for event in stream_debate_turn(
                payload.history, payload.user_message,
                metrics, email_data, whatsapp_data,
                payload.date_from, payload.date_to,
                metrics_2 or None, payload.date_from_2, payload.date_to_2,
            ):
                if event.get("type") == "message":
                    new_messages.append({
                        "speaker": event["speaker"], "content": event["content"],
                        "role": event.get("role", "debate"), "type": "debate",
                    })
                elif event.get("type") == "tokens":
                    turn_tokens = event.get("total", 0)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except RuntimeError as exc:
            logger.error("Debate turn failed: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
            return

        # Build full conversation to save
        prior = [
            {k: m[k] for k in ("speaker", "content", "role", "type") if k in m}
            for m in payload.history if m.get("type") in ("debate", "user")
        ]
        user_msg = {"speaker": "user", "content": payload.user_message, "type": "user", "role": "user"}
        all_messages = prior + [user_msg] + new_messages

        conv_id = payload.conversation_id
        async with AsyncSessionLocal() as save_db:
            if conv_id:
                res = await save_db.execute(
                    select(AIAnalysis).where(AIAnalysis.id == conv_id, AIAnalysis.user_id == user_id)
                )
                existing = res.scalar_one_or_none()
                if existing:
                    existing.result       = json.dumps({"debate": all_messages}, ensure_ascii=False)
                    existing.input_tokens = (existing.input_tokens or 0) + turn_tokens
                    await save_db.commit()
                    await save_db.refresh(existing)
                    conv_id = existing.id
                else:
                    conv_id = None

            if not conv_id:
                analysis = AIAnalysis(
                    user_id=user_id, analysis_type="debate",
                    platforms=platforms_list,
                    date_from=payload.date_from, date_to=payload.date_to,
                    prompt_used=f"debate-chat | {platforms_str} | {payload.date_from} to {payload.date_to}",
                    result=json.dumps({"debate": all_messages}, ensure_ascii=False),
                    input_tokens=turn_tokens, output_tokens=0,
                )
                save_db.add(analysis)
                await save_db.commit()
                await save_db.refresh(analysis)
                conv_id = analysis.id

        yield f"data: {json.dumps({'type': 'session', 'conversation_id': conv_id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/debate/verdict")
async def debate_verdict(
    payload: DebateVerdictRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request Llama verdict on the current conversation, then save full debate to DB."""
    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)
    metrics_2: list = []
    if payload.date_from_2 and payload.date_to_2:
        metrics_2 = await get_metrics(db, payload.platforms, payload.date_from_2, payload.date_to_2)

    email_data, whatsapp_data = [], []
    if settings.SFMC_CLIENT_ID:
        try:
            sfmc = SFMCConnector(
                client_id=settings.SFMC_CLIENT_ID,
                client_secret=settings.SFMC_CLIENT_SECRET,
                subdomain=settings.SFMC_SUBDOMAIN,
                account_id=settings.SFMC_ACCOUNT_ID,
            )
            email_data    = sfmc.normalize_email(await sfmc.fetch_email_performance(payload.date_from, payload.date_to))
            whatsapp_data = sfmc.normalize_whatsapp(await sfmc.fetch_whatsapp_performance(payload.date_from, payload.date_to))
        except Exception as e:
            logger.warning("SFMC unavailable for debate verdict: %s", e)

    user_id        = current_user.id
    platforms_list = [p.value for p in payload.platforms]
    platforms_str  = ", ".join(platforms_list)

    async def event_stream():
        llama_content = ""
        llama_tokens  = 0
        try:
            async for event in stream_llama_verdict(
                payload.history, metrics, email_data, whatsapp_data,
                payload.date_from, payload.date_to,
                metrics_2 or None, payload.date_from_2, payload.date_to_2,
            ):
                if event.get("type") == "message":
                    llama_content = event.get("content", "")
                elif event.get("type") == "tokens":
                    llama_tokens = event.get("total", 0)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except RuntimeError as exc:
            logger.error("Debate verdict failed: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
            return

        prior = [
            {k: m[k] for k in ("speaker", "content", "role", "type") if k in m}
            for m in payload.history if m.get("type") in ("debate", "user")
        ]
        if llama_content:
            prior.append({"speaker": "Llama", "role": "synthesis", "type": "debate", "content": llama_content})

        async with AsyncSessionLocal() as save_db:
            conv_id = payload.conversation_id
            if conv_id:
                res = await save_db.execute(
                    select(AIAnalysis).where(AIAnalysis.id == conv_id, AIAnalysis.user_id == user_id)
                )
                existing = res.scalar_one_or_none()
                if existing:
                    existing.result       = json.dumps({"debate": prior}, ensure_ascii=False)
                    existing.input_tokens = (existing.input_tokens or 0) + llama_tokens
                    await save_db.commit()
                    await save_db.refresh(existing)
                    yield f"data: {json.dumps({'type': 'done', 'id': existing.id})}\n\n"
                    return

            analysis = AIAnalysis(
                user_id=user_id, analysis_type="debate",
                platforms=platforms_list,
                date_from=payload.date_from, date_to=payload.date_to,
                prompt_used=f"debate-chat | {platforms_str} | {payload.date_from} to {payload.date_to}",
                result=json.dumps({"debate": prior}, ensure_ascii=False),
                input_tokens=llama_tokens, output_tokens=0,
            )
            save_db.add(analysis)
            await save_db.commit()
            await save_db.refresh(analysis)
            yield f"data: {json.dumps({'type': 'done', 'id': analysis.id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
