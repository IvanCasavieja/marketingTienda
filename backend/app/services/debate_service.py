"""Multi-AI debate: Claude vs ChatGPT vs Llama (moderator) in 3 rounds."""
import asyncio
import json
from datetime import date
from typing import List, Dict

import anthropic

from app.core.config import settings
from app.services.claude_service import _build_metrics_context, _build_sfmc_context

CLAUDE_PERSONA = (
    "Sos Claude, un analista cuantitativo riguroso especializado en marketing digital. "
    "Tu fortaleza es el análisis estadístico profundo, detectar patrones y anomalías en métricas, "
    "y construir conclusiones basadas en evidencia. Sos preciso, cauteloso con las afirmaciones sin datos, "
    "y priorizás la exactitud sobre el optimismo. Siempre respondés en español."
)

GPT_PERSONA = (
    "Sos ChatGPT, un estratega de marketing creativo y orientado al crecimiento del negocio. "
    "Tu fortaleza es conectar los datos con oportunidades de mercado, proponer estrategias innovadoras "
    "y pensar en el potencial de escala. Sos ambicioso, buscás disrupción y priorizás el impacto en revenue. "
    "Siempre respondés en español."
)

LLAMA_PERSONA = (
    "Sos Llama, un consultor operacional equilibrado y pragmático. "
    "Tu fortaleza es sintetizar perspectivas diversas, identificar el terreno común y proponer acciones "
    "concretas que el equipo pueda ejecutar esta semana. Sos directo, práctico y mediás con imparcialidad. "
    "Siempre respondés en español."
)


async def _ask_claude(system: str, prompt: str) -> str:
    def _sync():
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    return await asyncio.to_thread(_sync)


async def _ask_gpt(system: str, prompt: str) -> str:
    try:
        import openai as _openai
    except ImportError:
        raise RuntimeError("Paquete 'openai' no instalado. Ejecutá: pip install openai")
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY no configurado en las variables de entorno")
    client = _openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


async def _ask_llama(system: str, prompt: str) -> str:
    try:
        from groq import AsyncGroq
    except ImportError:
        raise RuntimeError("Paquete 'groq' no instalado. Ejecutá: pip install groq")
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no configurado en las variables de entorno")
    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


async def run_debate(
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
) -> Dict:
    metrics_ctx = _build_metrics_context(metrics)
    sfmc_ctx = _build_sfmc_context(email_data, whatsapp_data)

    data_context = (
        f"Período: {date_from} al {date_to}\n\n"
        f"## CAMPAÑAS PAGAS\n{metrics_ctx}\n\n"
        f"## COMUNICACIONES (Email / WhatsApp)\n{sfmc_ctx}"
    )

    round1_prompt = (
        f"Analizá estos datos de marketing y dá tu perspectiva inicial en 3-4 párrafos concisos:\n\n"
        f"{data_context}\n\n"
        "Incluí: principales hallazgos, el problema más crítico que detectás y tu recomendación más importante."
    )

    # Round 1 — all three analyze independently in parallel
    r1_results = await asyncio.gather(
        _ask_claude(CLAUDE_PERSONA, round1_prompt),
        _ask_gpt(GPT_PERSONA, round1_prompt),
        _ask_llama(LLAMA_PERSONA, round1_prompt),
        return_exceptions=True,
    )
    for r in r1_results:
        if isinstance(r, Exception):
            raise RuntimeError(f"Error en Round 1: {r}") from r
    r1_claude, r1_gpt, r1_llama = r1_results

    # Round 2 — Claude and GPT reply to each other in parallel
    r2_claude_prompt = (
        f"El análisis inicial de ChatGPT sobre los mismos datos fue:\n\n\"{r1_gpt}\"\n\n"
        "Teniendo en cuenta tu propio análisis, ¿en qué puntos concordás con ChatGPT y en cuáles diferís? "
        "¿Qué perspectiva importante creés que está pasando por alto? Sé directo y específico. Máximo 3 párrafos."
    )
    r2_gpt_prompt = (
        f"El análisis inicial de Claude sobre los mismos datos fue:\n\n\"{r1_claude}\"\n\n"
        "Teniendo en cuenta tu propio análisis, ¿en qué puntos concordás con Claude y en cuáles diferís? "
        "¿Qué perspectiva importante creés que está pasando por alto? Sé directo y específico. Máximo 3 párrafos."
    )

    r2_results = await asyncio.gather(
        _ask_claude(CLAUDE_PERSONA, r2_claude_prompt),
        _ask_gpt(GPT_PERSONA, r2_gpt_prompt),
        return_exceptions=True,
    )
    for r in r2_results:
        if isinstance(r, Exception):
            raise RuntimeError(f"Error en Round 2: {r}") from r
    r2_claude, r2_gpt = r2_results

    # Round 3 — Llama synthesizes the full debate
    r3_prompt = (
        f"Presenciaste el debate completo entre Claude y ChatGPT sobre datos de marketing ({date_from} al {date_to}).\n\n"
        f"**Claude (análisis inicial):** {r1_claude}\n\n"
        f"**ChatGPT (análisis inicial):** {r1_gpt}\n\n"
        f"**Claude (réplica):** {r2_claude}\n\n"
        f"**ChatGPT (réplica):** {r2_gpt}\n\n"
        "Como moderador, sintetizá en estas 3 secciones:\n"
        "1. **Puntos en los que todos coinciden** (alta confianza — ejecutar sin dudar)\n"
        "2. **Principal diferencia de perspectiva** y cuál te parece más válida con una justificación breve\n"
        "3. **Los 3 próximos pasos concretos** que el equipo debería tomar esta semana, ordenados por prioridad"
    )

    r3_llama = await _ask_llama(LLAMA_PERSONA, r3_prompt)

    debate = [
        {"speaker": "Claude",  "round": 1, "role": "analysis",  "content": r1_claude},
        {"speaker": "ChatGPT", "round": 1, "role": "analysis",  "content": r1_gpt},
        {"speaker": "Llama",   "round": 1, "role": "analysis",  "content": r1_llama},
        {"speaker": "Claude",  "round": 2, "role": "rebuttal",  "content": r2_claude},
        {"speaker": "ChatGPT", "round": 2, "role": "rebuttal",  "content": r2_gpt},
        {"speaker": "Llama",   "round": 3, "role": "synthesis", "content": r3_llama},
    ]

    return {
        "result": json.dumps({"debate": debate}, ensure_ascii=False),
        "input_tokens": 0,
        "output_tokens": 0,
        "analysis_type": "debate",
    }
