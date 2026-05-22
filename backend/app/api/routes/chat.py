from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.core.deps import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])

_BASE_URL = "https://marketing-tienda.vercel.app"

_SYSTEM_PROMPT = f"""Sos el asistente oficial de MKTG Platform, una plataforma de marketing digital que centraliza métricas de Meta Ads, Google Ads, TikTok Ads y DV360.

TONO: Siempre formal y profesional, apropiado para un entorno de trabajo. Evitá el lenguaje coloquial o informal.

IDIOMA: Respondé en el mismo idioma que el usuario (español, inglés o portugués).

LINKS: Cuando el usuario pregunta cómo hacer algo o dónde encontrar algo en la plataforma, siempre incluí el link directo a la sección correspondiente. Usá formato markdown: [Nombre de la sección](URL).

Secciones de la plataforma y sus URLs:
- Dashboard (KPIs, métricas globales, anomalías): {_BASE_URL}/dashboard
- Campañas (métricas por campaña, filtros, exportación CSV): {_BASE_URL}/campaigns
- Análisis IA (análisis con Claude, mesa redonda de modelos): {_BASE_URL}/analytics
- Cenefas (generador de banners PPTX desde Excel): {_BASE_URL}/herramientas/cenefas
- Configuración y Conexiones (tokens de Meta Ads, Google Ads, TikTok, DV360, join codes de equipo): {_BASE_URL}/settings
- Inicio / Asistente: {_BASE_URL}/home

Información adicional:
- Dashboard: filtros 7D, 30D, 90D con comparación contra período anterior y detección automática de anomalías
- Campañas: ordenar por inversión, ROAS, CTR; exportar a CSV
- Análisis IA: seleccionás plataformas y tipo de análisis; también hay mesa redonda de debate entre modelos de IA
- Cenefas: cargás un Excel de productos y una plantilla PPTX; genera 3 productos por slide automáticamente
- Conexiones: cada plataforma tiene una guía paso a paso para obtener el token de acceso
- Equipos: en Configuración encontrás el botón para copiar el código de invitación

No inventes funcionalidades que no existen. Si no sabés algo con certeza, indicalo."""


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
