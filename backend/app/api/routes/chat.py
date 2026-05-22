from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.core.deps import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])

_SYSTEM_PROMPT = """Sos el asistente de MKTG Platform, una plataforma de marketing digital que centraliza métricas de Meta Ads, Google Ads, TikTok Ads y DV360.

Tu rol es ayudar a los usuarios a entender y usar la plataforma. Respondé en el mismo idioma que el usuario (español, inglés o portugués según cómo escriba).

Funcionalidades de la plataforma:
- Dashboard: KPIs principales (inversión, clicks, conversiones, ROAS) con filtros 7D/30D/90D y detección de anomalías automática
- Campañas: métricas a nivel de campaña con filtros por plataforma, búsqueda y exportación CSV
- Análisis IA: análisis de campañas con Claude AI y mesa redonda de debate entre modelos de IA
- Cenefas: generador de banners PPTX a partir de un Excel de productos (3 productos por slide)
- Conexiones: integración con Meta Ads, Google Ads, TikTok Ads y DV360 mediante tokens de acceso
- Equipos: sistema de join codes para invitar colaboradores al workspace

Sé conciso y directo. No inventes funcionalidades que no existen en la plataforma."""


class _Msg(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[_Msg] = []


class ChatResponse(BaseModel):
    reply: str


@router.post("/message", response_model=ChatResponse)
async def chat_message(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="Chat AI not configured")

    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.GROQ_API_KEY)

        messages: list = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for msg in body.history[-10:]:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": body.message})

        completion = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=512,
            temperature=0.7,
        )
        reply = completion.choices[0].message.content or "No pude generar una respuesta."
        return ChatResponse(reply=reply)

    except Exception:
        raise HTTPException(status_code=500, detail="Error al contactar el servicio de IA")
