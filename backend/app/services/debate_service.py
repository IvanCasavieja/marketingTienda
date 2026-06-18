"""Multi-AI debate: Claude vs ChatGPT (rounds 1-2) + Llama synthesis (round 3 only)."""
import asyncio
import json
from collections import defaultdict
from datetime import date
from typing import List, Dict, AsyncIterator, Tuple

import anthropic

from app.core.config import settings
from app.services.claude_service import _build_metrics_context, _build_sfmc_context


def _build_compact_context(metrics: List[Dict], email_data: List[Dict], whatsapp_data: List[Dict]) -> str:
    """Per-platform aggregate for Llama's Round 3 — stays well under Groq's 12k TPM limit."""
    if not metrics:
        return "No hay métricas disponibles."

    by_platform: dict = defaultdict(lambda: {
        "spend": 0.0, "impressions": 0, "clicks": 0,
        "conversions": 0, "revenue": 0.0, "reach": 0, "names": set(),
    })
    for m in metrics:
        p = m["platform"].upper()
        by_platform[p]["spend"]       += m["spend"]
        by_platform[p]["impressions"] += m["impressions"]
        by_platform[p]["clicks"]      += m["clicks"]
        by_platform[p]["conversions"] += m["conversions"]
        by_platform[p]["revenue"]     += m["revenue"]
        by_platform[p]["reach"]       += m.get("reach") or 0
        by_platform[p]["names"].add(m["campaign_name"])

    lines = ["## Resumen por plataforma"]
    for platform, d in sorted(by_platform.items()):
        ctr  = (d["clicks"] / d["impressions"] * 100) if d["impressions"] > 0 else 0
        cpm  = (d["spend"] / d["impressions"] * 1000)  if d["impressions"] > 0 else 0
        roas = (d["revenue"] / d["spend"])              if d["spend"] > 0 else 0
        lines.append(
            f"- [{platform}] {len(d['names'])} campañas | Inversión=${d['spend']:.0f} | "
            f"Alcance={d['reach']:,} | CPM=${cpm:.2f} | CTR={ctr:.2f}% | Conv={d['conversions']} | ROAS={roas:.2f}x"
        )

    top8 = sorted(metrics, key=lambda x: x["spend"], reverse=True)[:8]
    seen: set = set()
    camp_lines = []
    for m in top8:
        key = (m["platform"], m["campaign_name"])
        if key in seen:
            continue
        seen.add(key)
        cpm_val = m.get("cpm") or 0.0
        camp_lines.append(
            f"  · [{m['platform'].upper()}] {m['campaign_name']}: ${m['spend']:.0f} | "
            f"CTR={m['ctr']:.2f}% | CPM=${cpm_val:.2f} | ROAS={m['roas']:.2f}x"
        )
    if camp_lines:
        lines.append("## Top campañas")
        lines.extend(camp_lines)

    for e in email_data[:4]:
        lines.append(f"[EMAIL] {e['name']}: apertura={e['open_rate']}% clicks={e['click_rate']}%")
    for w in whatsapp_data[:4]:
        lines.append(f"[WA] {w['name']}: entrega={w['delivery_rate']}% lectura={w['read_rate']}%")

    return "\n".join(lines)


MARKET_CONTEXT = """
## CONTEXTO DE MERCADO — URUGUAY
- **País:** Uruguay (América del Sur). Población ~3.5M, ~2.4M adultos digitales activos.
- **Mercado digital pequeño:** el pool de audiencia en Meta/Google/TikTok es reducido.
  La saturación de frecuencia ocurre rápido — frecuencias >4 en Meta son señal de alerta.
- **Benchmarks regionales LATAM para Uruguay (rangos típicos):**
  - Meta (FB+IG): CPM $3–$10 USD | CTR 0.6%–1.8% | CPC $0.40–$2.50 | ROAS e-commerce 2x–5x
  - Google Ads Search: CTR 3%–8% | CPC $0.30–$2.00 | Conversion rate 2%–6%
  - Google Display/DV360: CPM $1–$5 | CTR 0.05%–0.2%
  - TikTok Ads: CPM $2–$7 | CTR 0.5%–1.5% | CPC $0.30–$1.50
- **Plataformas clave en Uruguay:** WhatsApp es dominante (>90% penetración) — las campañas
  de Meta que impactan en Instagram/WhatsApp tienen alta atención. TikTok está en explosión
  de adopción, especialmente 18–34. Google Search sigue siendo la señal de intención más fuerte.
- **Estacionalidad local:** picos en Hot Sale (noviembre), Navidad/Año Nuevo, vuelta al cole (febrero/marzo).
- **Moneda:** los datos de inversión están en USD. El tipo de cambio UYU/USD afecta la percepción
  local del precio pero los CPCs/CPMs se negocian en dólares.
- **E-commerce:** en crecimiento pero todavía sub-desarrollado vs. Argentina/Brasil.
  Conversión promedio de tráfico pagado a compra: 1%–3%. ROAS <2x es señal de problema.
- **Consideración crítica de escala:** un ROAS de 4x con $500 de inversión no es lo mismo que 4x con $10.000.
  En Uruguay, escalar sin perder eficiencia es el desafío central — la audiencia se agota.
""".strip()


CLAUDE_PERSONA = (
    "Sos Claude, analista cuantitativo de marketing digital especializado en mercados LATAM, "
    "con foco particular en Uruguay. Conocés los benchmarks del mercado local y usás ese contexto "
    "para juzgar si un número es bueno o malo — no en abstracto, sino contra lo que es esperable "
    "en un mercado de 3.5M personas con alta penetración digital pero audiencia limitada.\n"
    "Tu método: primero los datos, después la interpretación con contexto. Calculás ratios derivados "
    "(costo por conversión, eficiencia de CPM relativa, ROAS ajustado por volumen) y los comparás "
    "contra los benchmarks de Uruguay/LATAM. Cuando ves un número, preguntás: ¿es bueno para Uruguay? "
    "¿cuánto tiempo antes de que esta audiencia se sature? ¿el volumen de conversiones es estadísticamente "
    "significativo o ruido?\n"
    "Contradecís afirmaciones vagas con evidencia específica. Nunca usás frases como 'rendimiento sólido' "
    "sin cuantificar contra qué benchmark. Respondés en español rioplatense."
)

GPT_PERSONA = (
    "Sos ChatGPT, estratega de crecimiento con experiencia en marketing de performance en LATAM, "
    "especialmente en mercados chicos como Uruguay donde la escala es el desafío central.\n"
    "Tu enfoque: identificar qué canales tienen mayor potencial de escala sin perder eficiencia, "
    "considerando el tamaño de audiencia disponible en Uruguay. Buscás oportunidades no obvias — "
    "canales sub-invertidos, segmentos de edad o interés sin explotar, plataformas donde el CPM uruguayo "
    "está por debajo del benchmark regional. Cuando alguien argumenta con promedios, vos buscás los "
    "outliers. Cuando alguien propone cautela, cuantificás el costo de oportunidad.\n"
    "Conocés que en Uruguay, TikTok está en explosión de adopción y suele tener CPMs más baratos, "
    "que Meta es el canal de mayor alcance pero se satura rápido, y que Google Search captura "
    "intención de compra real. Usás ese contexto para dar recomendaciones que tengan sentido "
    "para el mercado local. Siempre terminás con una recomendación específica: plataforma, monto y métrica esperada. "
    "Respondés en español rioplatense."
)

LLAMA_PERSONA = (
    "Sos Llama, árbitro analítico de debates sobre marketing digital en Uruguay y LATAM. "
    "Tu trabajo NO es suavizar ni encontrar el término medio — es determinar quién tiene el argumento "
    "más sólido según los datos y el contexto del mercado uruguayo. Tomás partido.\n"
    "Sabés que Uruguay es un mercado de nicho: 3.5M personas, audiencias digitales que se agotan rápido, "
    "y donde escalar con eficiencia es más difícil que en mercados grandes. Usás ese contexto para "
    "evaluar si los argumentos tienen sentido en la realidad local.\n"
    "Tus veredictos son directos: quién tiene razón, por qué con datos, y qué hacer esta semana. "
    "Respondés en español rioplatense."
)


async def _ask_claude(system: str, prompt: str, max_tokens: int = 800) -> Tuple[str, int]:
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
        tokens = resp.usage.input_tokens + resp.usage.output_tokens
        return resp.content[0].text, tokens
    return await asyncio.to_thread(_sync)


async def _ask_gpt(system: str, prompt: str, max_tokens: int = 800) -> Tuple[str, int]:
    try:
        import openai as _openai
    except ImportError:
        raise RuntimeError("Paquete 'openai' no instalado")
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY no configurado")
    client = _openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    resp = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    tokens = (resp.usage.prompt_tokens or 0) + (resp.usage.completion_tokens or 0)
    return resp.choices[0].message.content, tokens


async def _ask_llama(system: str, prompt: str, max_tokens: int = 900) -> Tuple[str, int]:
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
    tokens = (resp.usage.prompt_tokens or 0) + (resp.usage.completion_tokens or 0)
    return resp.choices[0].message.content, tokens


async def _race(speaker: str, round_n: int, role: str, coro, queue: asyncio.Queue) -> None:
    try:
        content, tokens = await coro
        await queue.put({
            "ok": True, "speaker": speaker, "round": round_n,
            "role": role, "content": content, "tokens": tokens,
        })
    except Exception as exc:
        await queue.put({"ok": False, "speaker": speaker, "error": str(exc)})


def _build_data_context(metrics_ctx: str, sfmc_ctx: str, date_from: date, date_to: date) -> str:
    return (
        f"Período: {date_from} al {date_to}\n\n"
        f"## CAMPAÑAS PAGAS\n{metrics_ctx}\n\n"
        f"## COMUNICACIONES\n{sfmc_ctx}"
    )


def _r1_prompt(data_context: str, focus: str) -> str:
    return (
        f"Analizá estos datos de marketing y tomá una posición clara y defendible.{focus}\n\n"
        f"{data_context}\n\n"
        "Estructurá tu respuesta así:\n"
        "**Posición central:** Una afirmación fuerte sobre el estado real de las campañas (no tibia).\n"
        "**Evidencia:** 2-3 métricas o campañas específicas con números exactos que respaldan tu posición.\n"
        "**Punto ciego:** Qué problema crítico creés que otros analistas van a ignorar o subestimar.\n\n"
        "Nombrá plataformas y campañas específicas. Máximo 4 párrafos."
    )


def _r2_claude_prompt(r1_gpt: str) -> str:
    return (
        f"ChatGPT analizó los mismos datos y argumentó:\n\n\"{r1_gpt}\"\n\n"
        "Rebatí directamente. Tu respuesta debe:\n"
        "1. Identificar el punto más débil o incorrecto de lo que dijo ChatGPT — refutarlo con datos concretos\n"
        "2. Defender tu posición original con algo que ChatGPT pasó por alto o interpretó mal\n"
        "3. Hacerle UNA pregunta directa y específica que ponga en jaque su argumento principal\n\n"
        "No hagas un resumen de tu propio análisis anterior. Ataca el argumento del otro. 3 párrafos."
    )


def _r2_gpt_prompt(r1_claude: str) -> str:
    return (
        f"Claude analizó los mismos datos y argumentó:\n\n\"{r1_claude}\"\n\n"
        "Rebatí directamente. Tu respuesta debe:\n"
        "1. Identificar el punto más débil o incorrecto de lo que dijo Claude — refutarlo con datos concretos\n"
        "2. Defender tu posición original con algo que Claude pasó por alto o interpretó mal\n"
        "3. Hacerle UNA pregunta directa y específica que ponga en jaque su argumento principal\n\n"
        "No hagas un resumen de tu propio análisis anterior. Ataca el argumento del otro. 3 párrafos."
    )


def _r3_prompt(r1: Dict, r2: Dict, compact_ctx: str, date_from: date, date_to: date, focus_line: str) -> str:
    return (
        f"{focus_line}Árbitro del debate entre Claude y ChatGPT sobre datos de marketing ({date_from} al {date_to}).\n\n"
        f"=== DEBATE COMPLETO ===\n\n"
        f"**Claude (Round 1):** {r1['Claude']}\n\n"
        f"**ChatGPT (Round 1):** {r1['ChatGPT']}\n\n"
        f"**Claude (Round 2 — réplica):** {r2['Claude']}\n\n"
        f"**ChatGPT (Round 2 — réplica):** {r2['ChatGPT']}\n\n"
        f"=== DATOS ===\n{compact_ctx}\n\n"
        "Tu veredicto en 3 secciones:\n\n"
        "**1. Desacuerdo central** — ¿Sobre qué exactamente están en desacuerdo real? No resumas todo, "
        "enfocate en LA tensión principal.\n\n"
        "**2. Veredicto** — ¿Quién tiene el argumento más sólido? Tomá partido. Podés usar una tabla "
        "markdown con 2-3 métricas clave si ayuda a ilustrar por qué uno tiene razón.\n\n"
        "**3. Plan de acción** — 3 acciones concretas para esta semana que resuelvan esa tensión, "
        "ordenadas por impacto. Cada acción debe poder ejecutarse mañana."
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

    focus = f"\n\nContexto de la pregunta del equipo: **{user_prompt.strip()}**" if user_prompt.strip() else ""
    focus_line = f"Pregunta del equipo: **{user_prompt.strip()}**\n\n" if user_prompt.strip() else ""

    tokens_by_model: Dict[str, int] = {}

    # ── Round 1 — cada uno toma una posición fuerte con datos ──
    yield {"type": "round_start", "round": 1}
    q1: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(_race("Claude",  1, "analysis", _ask_claude(CLAUDE_PERSONA, _r1_prompt(data_context, focus), 900), q1))
    asyncio.create_task(_race("ChatGPT", 1, "analysis", _ask_gpt(GPT_PERSONA, _r1_prompt(data_context, focus), 900), q1))

    r1: Dict[str, str] = {}
    for _ in range(2):
        item = await q1.get()
        if not item["ok"]:
            raise RuntimeError(f"Round 1 · {item['speaker']}: {item['error']}")
        r1[item["speaker"]] = item["content"]
        tokens_by_model[item["speaker"]] = item["tokens"]
        yield {"type": "message", "speaker": item["speaker"], "round": 1, "role": "analysis", "content": item["content"]}

    # ── Round 2 — réplica cruzada: atacan el argumento del otro y hacen preguntas ──
    yield {"type": "round_start", "round": 2}
    q2: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(_race("Claude",  2, "rebuttal", _ask_claude(CLAUDE_PERSONA, _r2_claude_prompt(r1["ChatGPT"]), 700), q2))
    asyncio.create_task(_race("ChatGPT", 2, "rebuttal", _ask_gpt(GPT_PERSONA, _r2_gpt_prompt(r1["Claude"]), 700), q2))

    r2: Dict[str, str] = {}
    for _ in range(2):
        item = await q2.get()
        if not item["ok"]:
            raise RuntimeError(f"Round 2 · {item['speaker']}: {item['error']}")
        r2[item["speaker"]] = item["content"]
        tokens_by_model[item["speaker"]] = tokens_by_model.get(item["speaker"], 0) + item["tokens"]
        yield {"type": "message", "speaker": item["speaker"], "round": 2, "role": "rebuttal", "content": item["content"]}

    # ── Round 3 — Llama da un veredicto con postura, no solo síntesis ──
    yield {"type": "round_start", "round": 3}
    r3_content, r3_tokens = await _ask_llama(
        LLAMA_PERSONA,
        _r3_prompt(r1, r2, compact_ctx, date_from, date_to, focus_line),
        1000,
    )
    tokens_by_model["Llama"] = r3_tokens
    yield {"type": "message", "speaker": "Llama", "round": 3, "role": "synthesis", "content": r3_content}

    total_tokens = sum(tokens_by_model.values())
    yield {"type": "tokens", "total": total_tokens, "by_model": tokens_by_model}


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

    focus = f"\n\nContexto de la pregunta del equipo: **{user_prompt.strip()}**" if user_prompt.strip() else ""
    focus_line = f"Pregunta del equipo: **{user_prompt.strip()}**\n\n" if user_prompt.strip() else ""

    r1_results = await asyncio.gather(
        _ask_claude(CLAUDE_PERSONA, _r1_prompt(data_context, focus), 900),
        _ask_gpt(GPT_PERSONA, _r1_prompt(data_context, focus), 900),
        return_exceptions=True,
    )
    for r in r1_results:
        if isinstance(r, Exception):
            raise RuntimeError(f"Error en Round 1: {r}") from r
    (r1_claude, t_r1_claude), (r1_gpt, t_r1_gpt) = r1_results

    r2_results = await asyncio.gather(
        _ask_claude(CLAUDE_PERSONA, _r2_claude_prompt(r1_gpt), 700),
        _ask_gpt(GPT_PERSONA, _r2_gpt_prompt(r1_claude), 700),
        return_exceptions=True,
    )
    for r in r2_results:
        if isinstance(r, Exception):
            raise RuntimeError(f"Error en Round 2: {r}") from r
    (r2_claude, t_r2_claude), (r2_gpt, t_r2_gpt) = r2_results

    r1 = {"Claude": r1_claude, "ChatGPT": r1_gpt}
    r2 = {"Claude": r2_claude, "ChatGPT": r2_gpt}
    r3_llama, t_r3 = await _ask_llama(
        LLAMA_PERSONA,
        _r3_prompt(r1, r2, compact_ctx, date_from, date_to, focus_line),
        1000,
    )

    total_tokens = t_r1_claude + t_r1_gpt + t_r2_claude + t_r2_gpt + t_r3
    debate = [
        {"speaker": "Claude",  "round": 1, "role": "analysis",  "content": r1_claude},
        {"speaker": "ChatGPT", "round": 1, "role": "analysis",  "content": r1_gpt},
        {"speaker": "Claude",  "round": 2, "role": "rebuttal",  "content": r2_claude},
        {"speaker": "ChatGPT", "round": 2, "role": "rebuttal",  "content": r2_gpt},
        {"speaker": "Llama",   "round": 3, "role": "synthesis", "content": r3_llama},
    ]

    return {
        "result": json.dumps({"debate": debate}, ensure_ascii=False),
        "input_tokens": total_tokens,
        "output_tokens": 0,
        "analysis_type": "debate",
    }


# ── Conversational mode (new) ─────────────────────────────────────────────────

def _build_history_str(history: List[Dict], max_items: int = 20) -> str:
    """Render conversation history for inclusion in prompts — no truncation per message."""
    if not history:
        return ""
    recent = history[-max_items:]
    lines = ["=== HISTORIAL DE CONVERSACIÓN ==="]
    for msg in recent:
        speaker = msg.get("speaker", "?")
        content = str(msg.get("content", ""))
        lines.append(f"[{speaker}]: {content}")
    return "\n\n".join(lines)


async def stream_debate_turn(
    history: List[Dict],
    user_message: str,
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
) -> AsyncIterator[dict]:
    """Claude + ChatGPT respond to a single user message, with full conversation history."""
    compact_ctx = _build_compact_context(metrics, email_data, whatsapp_data)
    history_str = _build_history_str(history)

    is_first_turn = not any(m.get("speaker") in ("Claude", "ChatGPT") for m in history)
    last_gpt    = next((m["content"][:500] for m in reversed(history) if m.get("speaker") == "ChatGPT"), None)
    last_claude = next((m["content"][:500] for m in reversed(history) if m.get("speaker") == "Claude"), None)

    def _prompt(speaker: str, other_last: str | None) -> str:
        other_name = "ChatGPT" if speaker == "Claude" else "Claude"
        parts: list[str] = []
        parts.append(MARKET_CONTEXT)
        if history_str:
            parts.append(history_str)
        parts.append(f"Datos del período {date_from} al {date_to}:\n{compact_ctx}")
        parts.append(f"Pregunta del usuario: **{user_message}**")

        if is_first_turn:
            parts.append(
                "INSTRUCCIONES — primer turno:\n"
                "1. Tomá una posición analítica fuerte y específica sobre lo que pregunta el usuario.\n"
                "2. Usá números exactos: ROAS, CTR, CPC, CPM, conversiones por campaña — no promedios vagos.\n"
                "3. Identificá la campaña o plataforma con el mejor y peor desempeño y explicá POR QUÉ (causa raíz, no solo el síntoma).\n"
                "4. Calculá al menos una ratio o comparación entre plataformas que sea no obvia: por ejemplo, eficiencia de conversión "
                "ajustada por inversión, o CTR relativo entre canales.\n"
                "5. Terminá con una afirmación provocadora que el otro analista probablemente va a querer rebatir.\n"
                "Sé directo y técnico. No uses lenguaje vago como 'rendimiento sólido' o 'buena tracción'."
            )
        else:
            counter = (
                f"\n\n{other_name} argumentó:\n\"{other_last}\"\n\n"
                "Tu respuesta debe:\n"
                f"1. Señalar el error o la omisión más grave de {other_name} y refutarla con un dato específico de los datos.\n"
                "2. Profundizar en el argumento que planteaste antes con nueva evidencia de los datos — no lo repitas, extendelo.\n"
                "3. Proponer una conclusión accionable concreta: qué haría HOY con el presupuesto o la estrategia, y cuánto impacto esperarías.\n"
                f"4. Hacerle a {other_name} una pregunta técnica específica que no pueda responder sin mirar los datos."
            ) if other_last else (
                "\nProfundizá tu análisis con nueva evidencia y formulá una conclusión accionable concreta."
            )
            parts.append(counter)
        return "\n\n".join(parts)

    q: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(_race("Claude",  0, "debate", _ask_claude(CLAUDE_PERSONA, _prompt("Claude",  last_gpt),    1400), q))
    asyncio.create_task(_race("ChatGPT", 0, "debate", _ask_gpt(GPT_PERSONA,       _prompt("ChatGPT", last_claude), 1400), q))

    tokens_by_model: Dict[str, int] = {}
    for _ in range(2):
        item = await q.get()
        if not item["ok"]:
            raise RuntimeError(f"{item['speaker']}: {item['error']}")
        tokens_by_model[item["speaker"]] = item["tokens"]
        yield {"type": "message", "speaker": item["speaker"], "role": "debate", "content": item["content"]}

    yield {"type": "tokens", "total": sum(tokens_by_model.values()), "by_model": tokens_by_model}


async def stream_llama_verdict(
    history: List[Dict],
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
) -> AsyncIterator[dict]:
    """Llama reads the full debate and gives an on-demand verdict."""
    compact_ctx  = _build_compact_context(metrics, email_data, whatsapp_data)
    history_str  = _build_history_str(history, max_items=24)

    prompt = (
        f"Sos el árbitro de este debate sobre campañas de marketing ({date_from} al {date_to}).\n\n"
        f"{history_str}\n\n"
        f"Datos de referencia:\n{compact_ctx}\n\n"
        "Tu veredicto debe ser analítico y concreto — no diplomático. Estructuralo así:\n\n"
        "**1. Desacuerdo central**\n"
        "En 2-3 oraciones: cuál es la tensión real entre los dos analistas. No resumas todo el debate, "
        "identificá el punto exacto donde difieren y por qué importa.\n\n"
        "**2. Veredicto**\n"
        "¿Quién tiene el argumento más sólido y por qué? Tomá partido claro — no 'ambos tienen razón'. "
        "Justificá con al menos 2 datos concretos de la conversación o de los datos. "
        "Si los datos no son concluyentes, decilo y explicá qué información faltaría para decidir.\n"
        "Incluí una tabla markdown comparando las posiciones si ayuda a ilustrar el veredicto.\n\n"
        "**3. Plan de acción**\n"
        "3 acciones ejecutables ordenadas por impacto esperado. Para cada una: qué hacer, en qué plataforma/campaña, "
        "y qué métrica debería mejorar como resultado. Sé específico — nada de 'optimizar el presupuesto'."
    )

    content, tokens = await _ask_llama(LLAMA_PERSONA, prompt, 1400)
    yield {"type": "message", "speaker": "Llama", "role": "synthesis", "content": content}
    yield {"type": "tokens", "total": tokens, "by_model": {"Llama": tokens}}
