"""Multi-AI debate: Claude vs ChatGPT (rounds 1-2) + Llama synthesis (round 3 only)."""
import asyncio
import json
from collections import defaultdict
from datetime import date
from typing import List, Dict, AsyncIterator

import anthropic

from app.core.config import settings
from app.services.claude_service import _build_metrics_context, _build_sfmc_context


def _build_compact_context(metrics: List[Dict], email_data: List[Dict], whatsapp_data: List[Dict]) -> str:
    """Per-platform aggregate — keeps Llama's Round 3 prompt well under Groq's 12k TPM limit."""
    if not metrics:
        return "No hay métricas disponibles."

    by_platform: dict = defaultdict(lambda: {
        "spend": 0.0, "impressions": 0, "clicks": 0,
        "conversions": 0, "revenue": 0.0, "names": set(),
    })
    for m in metrics:
        p = m["platform"].upper()
        by_platform[p]["spend"] += m["spend"]
        by_platform[p]["impressions"] += m["impressions"]
        by_platform[p]["clicks"] += m["clicks"]
        by_platform[p]["conversions"] += m["conversions"]
        by_platform[p]["revenue"] += m["revenue"]
        by_platform[p]["names"].add(m["campaign_name"])

    lines = ["## Resumen por plataforma"]
    for platform, d in sorted(by_platform.items()):
        ctr = (d["clicks"] / d["impressions"] * 100) if d["impressions"] > 0 else 0
        roas = (d["revenue"] / d["spend"]) if d["spend"] > 0 else 0
        lines.append(
            f"- [{platform}] {len(d['names'])} campañas | Inversión=${d['spend']:.0f} | "
            f"CTR={ctr:.2f}% | Conv={d['conversions']} | ROAS={roas:.2f}x"
        )

    top8 = sorted(metrics, key=lambda x: x["spend"], reverse=True)[:8]
    seen: set = set()
    camp_lines = []
    for m in top8:
        key = (m["platform"], m["campaign_name"])
        if key in seen:
            continue
        seen.add(key)
        camp_lines.append(
            f"  · [{m['platform'].upper()}] {m['campaign_name']}: ${m['spend']:.0f} | ROAS={m['roas']:.2f}x"
        )
    if camp_lines:
        lines.append("## Top campañas")
        lines.extend(camp_lines)

    for e in email_data[:4]:
        lines.append(f"[EMAIL] {e['name']}: apertura={e['open_rate']}% clicks={e['click_rate']}%")
    for w in whatsapp_data[:4]:
        lines.append(f"[WA] {w['name']}: entrega={w['delivery_rate']}% lectura={w['read_rate']}%")

    return "\n".join(lines)


CLAUDE_PERSONA = (
    "Sos Claude, analista cuantitativo riguroso en marketing digital. "
    "Detectás patrones y anomalías en métricas con base en evidencia. "
    "Sos preciso, cauteloso con afirmaciones sin datos. Respondés en español."
)

GPT_PERSONA = (
    "Sos ChatGPT, estratega de marketing creativo orientado al crecimiento. "
    "Conectás datos con oportunidades de mercado y proponés estrategias de escala. "
    "Sos ambicioso y priorizás el impacto en revenue. Respondés en español."
)

LLAMA_PERSONA = (
    "Sos Llama, consultor operacional equilibrado. Sintetizás perspectivas diversas "
    "y proponés acciones concretas para ejecutar esta semana. "
    "Sos directo, práctico e imparcial. Respondés en español."
)


async def _ask_claude(system: str, prompt: str, max_tokens: int = 800) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurado")
    def _sync():
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    return await asyncio.to_thread(_sync)


async def _ask_gpt(system: str, prompt: str, max_tokens: int = 800) -> str:
    try:
        import openai as _openai
    except ImportError:
        raise RuntimeError("Paquete 'openai' no instalado")
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY no configurado")
    client = _openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content


async def _ask_llama(system: str, prompt: str, max_tokens: int = 900) -> str:
    try:
        from groq import AsyncGroq
    except ImportError:
        raise RuntimeError("Paquete 'groq' no instalado")
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no configurado")
    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    resp = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content


async def _race(speaker: str, round_n: int, role: str, coro, queue: asyncio.Queue) -> None:
    try:
        content = await coro
        await queue.put({"ok": True, "speaker": speaker, "round": round_n, "role": role, "content": content})
    except Exception as exc:
        await queue.put({"ok": False, "speaker": speaker, "error": str(exc)})


def _build_data_context(metrics_ctx: str, sfmc_ctx: str, date_from: date, date_to: date) -> str:
    return (
        f"Período: {date_from} al {date_to}\n\n"
        f"## CAMPAÑAS PAGAS\n{metrics_ctx}\n\n"
        f"## COMUNICACIONES\n{sfmc_ctx}"
    )


async def stream_debate(
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
    user_prompt: str = "",
) -> AsyncIterator[dict]:
    metrics_ctx = _build_metrics_context(metrics)
    sfmc_ctx = _build_sfmc_context(email_data, whatsapp_data)
    data_context = _build_data_context(metrics_ctx, sfmc_ctx, date_from, date_to)
    compact_ctx = _build_compact_context(metrics, email_data, whatsapp_data)

    focus = f"\n\nPregunta del equipo: **{user_prompt.strip()}**" if user_prompt.strip() else ""
    r1_prompt = (
        f"Analizá estos datos de marketing en 3 párrafos concisos.{focus}\n\n"
        f"{data_context}\n\n"
        "Incluí: hallazgos clave, el problema más crítico y tu recomendación principal."
    )

    # ── Round 1 — Claude + ChatGPT analizan en paralelo (Llama ahorra tokens para síntesis) ──
    yield {"type": "round_start", "round": 1}
    q1: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(_race("Claude",  1, "analysis", _ask_claude(CLAUDE_PERSONA, r1_prompt, 800), q1))
    asyncio.create_task(_race("ChatGPT", 1, "analysis", _ask_gpt(GPT_PERSONA, r1_prompt, 800), q1))

    r1: Dict[str, str] = {}
    for _ in range(2):
        item = await q1.get()
        if not item["ok"]:
            raise RuntimeError(f"Round 1 · {item['speaker']}: {item['error']}")
        r1[item["speaker"]] = item["content"]
        yield {"type": "message", "speaker": item["speaker"], "round": 1, "role": "analysis", "content": item["content"]}

    # ── Round 2 — réplica cruzada (sin contexto de datos, solo las respuestas previas) ──
    yield {"type": "round_start", "round": 2}
    r2_claude_prompt = (
        f"ChatGPT analizó los mismos datos y dijo:\n\n\"{r1['ChatGPT']}\"\n\n"
        "¿En qué concordás y qué perspectiva importante le falta? Sé directo. 2-3 párrafos."
    )
    r2_gpt_prompt = (
        f"Claude analizó los mismos datos y dijo:\n\n\"{r1['Claude']}\"\n\n"
        "¿En qué concordás y qué perspectiva importante le falta? Sé directo. 2-3 párrafos."
    )
    q2: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(_race("Claude",  2, "rebuttal", _ask_claude(CLAUDE_PERSONA, r2_claude_prompt, 600), q2))
    asyncio.create_task(_race("ChatGPT", 2, "rebuttal", _ask_gpt(GPT_PERSONA, r2_gpt_prompt, 600), q2))

    r2: Dict[str, str] = {}
    for _ in range(2):
        item = await q2.get()
        if not item["ok"]:
            raise RuntimeError(f"Round 2 · {item['speaker']}: {item['error']}")
        r2[item["speaker"]] = item["content"]
        yield {"type": "message", "speaker": item["speaker"], "round": 2, "role": "rebuttal", "content": item["content"]}

    # ── Round 3 — Llama sintetiza con contexto compacto (≈4k tokens, bien bajo el límite de Groq) ──
    yield {"type": "round_start", "round": 3}
    focus_line = f"La pregunta del equipo fue: **{user_prompt.strip()}**\n\n" if user_prompt.strip() else ""
    r3_prompt = (
        f"{focus_line}Sintetizá el debate entre Claude y ChatGPT ({date_from} al {date_to}).\n\n"
        f"Contexto de datos:\n{compact_ctx}\n\n"
        f"**Claude (análisis):** {r1['Claude']}\n\n"
        f"**ChatGPT (análisis):** {r1['ChatGPT']}\n\n"
        f"**Claude (réplica):** {r2['Claude']}\n\n"
        f"**ChatGPT (réplica):** {r2['ChatGPT']}\n\n"
        "Respondé en 3 secciones:\n"
        "1. **Acuerdo** — qué coinciden (ejecutar sin dudar)\n"
        "2. **Diferencia clave** — cuál perspectiva es más válida y por qué\n"
        "3. **3 próximos pasos** — ordenados por impacto esta semana"
    )
    r3_content = await _ask_llama(LLAMA_PERSONA, r3_prompt, 900)
    yield {"type": "message", "speaker": "Llama", "round": 3, "role": "synthesis", "content": r3_content}


async def run_debate(
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
    user_prompt: str = "",
) -> Dict:
    metrics_ctx = _build_metrics_context(metrics)
    sfmc_ctx = _build_sfmc_context(email_data, whatsapp_data)
    data_context = _build_data_context(metrics_ctx, sfmc_ctx, date_from, date_to)
    compact_ctx = _build_compact_context(metrics, email_data, whatsapp_data)

    focus = f"\n\nPregunta del equipo: **{user_prompt.strip()}**" if user_prompt.strip() else ""
    r1_prompt = (
        f"Analizá estos datos de marketing en 3 párrafos concisos.{focus}\n\n"
        f"{data_context}\n\n"
        "Incluí: hallazgos clave, el problema más crítico y tu recomendación principal."
    )

    r1_results = await asyncio.gather(
        _ask_claude(CLAUDE_PERSONA, r1_prompt, 800),
        _ask_gpt(GPT_PERSONA, r1_prompt, 800),
        return_exceptions=True,
    )
    for r in r1_results:
        if isinstance(r, Exception):
            raise RuntimeError(f"Error en Round 1: {r}") from r
    r1_claude, r1_gpt = r1_results

    r2_claude_prompt = (
        f"ChatGPT analizó los mismos datos y dijo:\n\n\"{r1_gpt}\"\n\n"
        "¿En qué concordás y qué perspectiva importante le falta? Sé directo. 2-3 párrafos."
    )
    r2_gpt_prompt = (
        f"Claude analizó los mismos datos y dijo:\n\n\"{r1_claude}\"\n\n"
        "¿En qué concordás y qué perspectiva importante le falta? Sé directo. 2-3 párrafos."
    )
    r2_results = await asyncio.gather(
        _ask_claude(CLAUDE_PERSONA, r2_claude_prompt, 600),
        _ask_gpt(GPT_PERSONA, r2_gpt_prompt, 600),
        return_exceptions=True,
    )
    for r in r2_results:
        if isinstance(r, Exception):
            raise RuntimeError(f"Error en Round 2: {r}") from r
    r2_claude, r2_gpt = r2_results

    focus_line = f"La pregunta del equipo fue: **{user_prompt.strip()}**\n\n" if user_prompt.strip() else ""
    r3_prompt = (
        f"{focus_line}Sintetizá el debate entre Claude y ChatGPT ({date_from} al {date_to}).\n\n"
        f"Contexto de datos:\n{compact_ctx}\n\n"
        f"**Claude (análisis):** {r1_claude}\n\n"
        f"**ChatGPT (análisis):** {r1_gpt}\n\n"
        f"**Claude (réplica):** {r2_claude}\n\n"
        f"**ChatGPT (réplica):** {r2_gpt}\n\n"
        "Respondé en 3 secciones:\n"
        "1. **Acuerdo** — qué coinciden (ejecutar sin dudar)\n"
        "2. **Diferencia clave** — cuál perspectiva es más válida y por qué\n"
        "3. **3 próximos pasos** — ordenados por impacto esta semana"
    )
    r3_llama = await _ask_llama(LLAMA_PERSONA, r3_prompt, 900)

    debate = [
        {"speaker": "Claude",  "round": 1, "role": "analysis",  "content": r1_claude},
        {"speaker": "ChatGPT", "round": 1, "role": "analysis",  "content": r1_gpt},
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
