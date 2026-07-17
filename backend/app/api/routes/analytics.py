import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import date
from typing import List, Optional
from app.core.database import get_db, AsyncSessionLocal
from app.core.deps import require_permission
from app.core.config import settings
from app.core.rate_limit import limiter
from app.models.user import User
from app.models.ai_analysis import AIAnalysis
from app.models.platform_connection import Platform
from app.models.meridian_channel_summary import MeridianChannelSummary
from app.services.metrics_service import get_metrics, get_available_platforms
from app.services.debate_service import run_debate, stream_debate, stream_debate_turn, stream_llama_verdict
from app.services.ai_usage_service import log_ai_usage
from app.connectors.sfmc import SFMCConnector

logger = logging.getLogger(__name__)

# La Triada (debate) es el único análisis de IA "standard" que sigue en pie —
# reporte completo / detección de anomalías / optimización / cross-platform
# se sacaron: estaban construidos pero ningún botón del frontend los llamaba.
_ALL_HANDLERS = {"debate": run_debate}

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _get_meridian_summary(db: AsyncSession) -> List[dict]:
    """Última corrida importada del modelo de Marketing Mix (Meridian), si
    existe — ver scripts/import_meridian_summary.py. debate_service.py
    decide por sí solo si la usa (solo si reliable=True en todas las filas),
    así que acá no hace falta filtrar nada, alcanza con traer lo que haya."""
    result = await db.execute(select(MeridianChannelSummary))
    return [
        {
            "channel": row.channel,
            "spend": row.spend,
            "pct_of_spend": row.pct_of_spend,
            "incremental_outcome": row.incremental_outcome,
            "pct_of_contribution": row.pct_of_contribution,
            "roi": row.roi,
            "mroi": row.mroi,
            "reliable": row.reliable,
        }
        for row in result.scalars().all()
    ]


async def _assert_platforms_available(db: AsyncSession, platforms: List[Platform]) -> None:
    """Corta antes de gastar un solo token de LLM si piden analizar una plataforma
    sin conexión activa (ni fixture habilitado) — sin esto, get_metrics devuelve
    una lista vacía en silencio y el análisis sigue adelante sobre datos que no
    existen."""
    available = await get_available_platforms(db)
    missing = [p.value for p in platforms if p not in available]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Sin conexión activa para: {', '.join(missing)}. "
                "Conectá la plataforma en Conexiones antes de analizarla."
            ),
        )


async def _get_sfmc_data(date_from: date, date_to: date, context: str = "") -> tuple[list, list]:
    if not settings.SFMC_CLIENT_ID:
        return [], []
    try:
        sfmc = SFMCConnector(
            client_id=settings.SFMC_CLIENT_ID,
            client_secret=settings.SFMC_CLIENT_SECRET,
            subdomain=settings.SFMC_SUBDOMAIN,
            account_id=settings.SFMC_ACCOUNT_ID,
        )
        email_data = sfmc.normalize_email(await sfmc.fetch_email_performance(date_from, date_to))
        whatsapp_data = sfmc.normalize_whatsapp(await sfmc.fetch_whatsapp_performance(date_from, date_to))
        return email_data, whatsapp_data
    except Exception as e:
        suffix = f" ({context})" if context else ""
        logger.warning("SFMC data unavailable%s: %s", suffix, e)
        return [], []


class AnalysisRequest(BaseModel):
    platforms: List[Platform]
    date_from: date
    date_to: date
    analysis_type: str = "debate"
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


@router.get("/available-platforms")
async def available_platforms(
    current_user: User = Depends(require_permission("ai.triada")),
    db: AsyncSession = Depends(get_db),
):
    """Plataformas que hoy se pueden analizar (conexión activa o fixture habilitado
    como Meta) — el frontend usa esto para deshabilitar las que no van a andar."""
    available = await get_available_platforms(db)
    return {"platforms": sorted(p.value for p in available)}


@router.post("/analyze")
@limiter.limit("10/minute")
async def analyze(
    request: Request,
    payload: AnalysisRequest,
    current_user: User = Depends(require_permission("ai.triada")),
    db: AsyncSession = Depends(get_db),
):
    handler = _ALL_HANDLERS.get(payload.analysis_type)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown analysis type: {payload.analysis_type}")

    await _assert_platforms_available(db, payload.platforms)
    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)
    meridian_summary = await _get_meridian_summary(db)

    try:
        email_data, whatsapp_data = await _get_sfmc_data(payload.date_from, payload.date_to)
        result = await handler(
            metrics, email_data, whatsapp_data, payload.date_from, payload.date_to, payload.user_prompt,
            meridian_summary=meridian_summary,
        )
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
    for item in result.get("usage_items", []):
        await log_ai_usage(db, current_user.id, "debate", item["provider"], item["model"], item["input_tokens"], item["output_tokens"])
    await db.flush()

    return {
        "id": analysis.id,
        "analysis_type": analysis.analysis_type,
        "result": analysis.result,
        "tokens_used": analysis.input_tokens + analysis.output_tokens,
    }


@router.get("/history")
async def get_history(
    current_user: User = Depends(require_permission("ai.triada")),
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
    current_user: User = Depends(require_permission("ai.triada")),
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




@router.post("/analyze/debate/stream")
@limiter.limit("10/minute")
async def debate_stream(
    request: Request,
    payload: AnalysisRequest,
    current_user: User = Depends(require_permission("ai.triada")),
    db: AsyncSession = Depends(get_db),
):
    await _assert_platforms_available(db, payload.platforms)
    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)
    meridian_summary = await _get_meridian_summary(db)

    email_data, whatsapp_data = await _get_sfmc_data(payload.date_from, payload.date_to, "debate stream")

    user_id = current_user.id
    platforms_list = [p.value for p in payload.platforms]
    platforms_str = ", ".join(platforms_list)
    date_from = payload.date_from
    date_to = payload.date_to

    user_prompt = payload.user_prompt

    async def event_stream():
        all_messages = []
        total_tokens = 0
        usage_items: list = []
        try:
            async for event in stream_debate(
                metrics, email_data, whatsapp_data, date_from, date_to, user_prompt,
                meridian_summary=meridian_summary,
            ):
                if event.get("type") == "message":
                    all_messages.append({
                        "speaker": event["speaker"],
                        "round":   event["round"],
                        "role":    event["role"],
                        "content": event["content"],
                    })
                elif event.get("type") == "tokens":
                    total_tokens = event.get("total", 0)
                elif event.get("type") == "usage_detail":
                    usage_items = event.get("items", [])
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
            for item in usage_items:
                await log_ai_usage(save_db, user_id, "debate", item["provider"], item["model"], item["input_tokens"], item["output_tokens"])
            await save_db.commit()
            await save_db.refresh(analysis)
            yield f"data: {json.dumps({'type': 'done', 'id': analysis.id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/debate/turn")
@limiter.limit("10/minute")
async def debate_turn(
    request: Request,
    payload: DebateTurnRequest,
    current_user: User = Depends(require_permission("ai.triada")),
    db: AsyncSession = Depends(get_db),
):
    """Single conversational turn: ChatGPT first (ya con contexto web fresco), luego Claude
    (rebate/valida con números). Auto-saves after every turn."""
    await _assert_platforms_available(db, payload.platforms)
    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)
    metrics_2: list = []
    if payload.date_from_2 and payload.date_to_2:
        metrics_2 = await get_metrics(db, payload.platforms, payload.date_from_2, payload.date_to_2)
    meridian_summary = await _get_meridian_summary(db)

    email_data, whatsapp_data = await _get_sfmc_data(payload.date_from, payload.date_to, "debate turn")

    user_id        = current_user.id
    platforms_list = [p.value for p in payload.platforms]
    platforms_str  = ", ".join(platforms_list)

    async def event_stream():
        new_messages: list = []
        turn_tokens = 0
        usage_items: list = []
        try:
            async for event in stream_debate_turn(
                payload.history, payload.user_message,
                metrics, email_data, whatsapp_data,
                payload.date_from, payload.date_to,
                metrics_2 or None, payload.date_from_2, payload.date_to_2,
                meridian_summary=meridian_summary,
            ):
                if event.get("type") == "message":
                    new_messages.append({
                        "speaker": event["speaker"], "content": event["content"],
                        "role": event.get("role", "debate"), "type": "debate",
                    })
                elif event.get("type") == "tokens":
                    turn_tokens = event.get("total", 0)
                elif event.get("type") == "usage_detail":
                    usage_items = event.get("items", [])
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

            for item in usage_items:
                await log_ai_usage(save_db, user_id, "debate", item["provider"], item["model"], item["input_tokens"], item["output_tokens"])
            await save_db.commit()

        yield f"data: {json.dumps({'type': 'session', 'conversation_id': conv_id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/debate/verdict")
@limiter.limit("10/minute")
async def debate_verdict(
    request: Request,
    payload: DebateVerdictRequest,
    current_user: User = Depends(require_permission("ai.triada")),
    db: AsyncSession = Depends(get_db),
):
    """Request Llama verdict on the current conversation, then save full debate to DB."""
    await _assert_platforms_available(db, payload.platforms)
    metrics = await get_metrics(db, payload.platforms, payload.date_from, payload.date_to)
    metrics_2: list = []
    if payload.date_from_2 and payload.date_to_2:
        metrics_2 = await get_metrics(db, payload.platforms, payload.date_from_2, payload.date_to_2)
    meridian_summary = await _get_meridian_summary(db)

    email_data, whatsapp_data = await _get_sfmc_data(payload.date_from, payload.date_to, "debate verdict")

    user_id        = current_user.id
    platforms_list = [p.value for p in payload.platforms]
    platforms_str  = ", ".join(platforms_list)

    async def event_stream():
        llama_content = ""
        llama_tokens  = 0
        usage_items: list = []
        try:
            async for event in stream_llama_verdict(
                payload.history, metrics, email_data, whatsapp_data,
                payload.date_from, payload.date_to,
                metrics_2 or None, payload.date_from_2, payload.date_to_2,
                meridian_summary=meridian_summary,
            ):
                if event.get("type") == "message":
                    llama_content = event.get("content", "")
                elif event.get("type") == "tokens":
                    llama_tokens = event.get("total", 0)
                elif event.get("type") == "usage_detail":
                    usage_items = event.get("items", [])
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
                    for item in usage_items:
                        await log_ai_usage(save_db, user_id, "debate", item["provider"], item["model"], item["input_tokens"], item["output_tokens"])
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
            for item in usage_items:
                await log_ai_usage(save_db, user_id, "debate", item["provider"], item["model"], item["input_tokens"], item["output_tokens"])
            await save_db.commit()
            await save_db.refresh(analysis)
            yield f"data: {json.dumps({'type': 'done', 'id': analysis.id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
