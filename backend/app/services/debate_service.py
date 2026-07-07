"""Multi-AI debate: Claude vs ChatGPT (rounds 1-2) + Llama synthesis (round 3 only)."""
import asyncio
import json
import re
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


def _aggregate_by_platform_day(metrics: List[Dict]) -> Dict[str, List[Tuple[str, Dict]]]:
    """metrics trae una fila por campaña por día (metrics_service.get_metrics no
    pre-agrega) — acá se agrupa por (plataforma, día) sumando todas las campañas
    de esa plataforma en ese día. Es la pieza que faltaba: sin esto, las funciones
    de contexto de más abajo colapsan todo el período en un solo total y ningún
    modelo puede correlacionar un pico o caída con una fecha concreta."""
    by_key: dict = defaultdict(lambda: {
        "spend": 0.0, "impressions": 0, "clicks": 0, "conversions": 0, "revenue": 0.0,
    })
    for m in metrics:
        key = (m["platform"].upper(), m["date"])
        d = by_key[key]
        d["spend"]       += m["spend"]
        d["impressions"] += m["impressions"]
        d["clicks"]      += m["clicks"]
        d["conversions"] += m["conversions"]
        d["revenue"]     += m["revenue"]

    by_platform: dict = defaultdict(list)
    for (platform, day), d in by_key.items():
        by_platform[platform].append((day, d))
    for platform in by_platform:
        by_platform[platform].sort(key=lambda x: x[0])
    return by_platform


def _build_daily_series_context(metrics: List[Dict], max_days: int = 120) -> str:
    """Serie diaria agregada por plataforma (fecha, spend, CTR, ROAS) — para Claude
    y ChatGPT, que tienen contexto grande. Sin esta serie, un evento cultural con
    fecha puntual no tiene con qué cruzarse: el modelo nunca ve qué pasó un día
    específico, solo el total del período completo."""
    if not metrics:
        return ""
    by_platform = _aggregate_by_platform_day(metrics)
    if not by_platform:
        return ""

    lines = ["## SERIE DIARIA POR PLATAFORMA (usar para ubicar picos/caídas en una fecha exacta)"]
    for platform in sorted(by_platform):
        days = by_platform[platform][-max_days:]
        lines.append(f"\n### {platform}")
        for day, d in days:
            ctr  = (d["clicks"] / d["impressions"] * 100) if d["impressions"] > 0 else 0.0
            roas = (d["revenue"] / d["spend"]) if d["spend"] > 0 else 0.0
            lines.append(
                f"- {day}: Spend=${d['spend']:.0f} | Clicks={d['clicks']} | "
                f"CTR={ctr:.2f}% | Conv={d['conversions']} | ROAS={roas:.2f}x"
            )
    return "\n".join(lines)


def _build_daily_highlights(metrics: List[Dict], max_lines: int = 8) -> str:
    """Versión ultra-compacta de la serie diaria: solo los días con mayor desvío
    de spend respecto al promedio de su propia plataforma. Para Llama (Groq tiene
    un límite de 12k TPM y no admite la tabla completa de _build_daily_series_context)."""
    if not metrics:
        return ""
    by_platform = _aggregate_by_platform_day(metrics)

    scored: list = []
    for platform, days in by_platform.items():
        if len(days) < 3:
            continue
        avg_spend = sum(d["spend"] for _, d in days) / len(days)
        if avg_spend <= 0:
            continue
        for day, d in days:
            delta_pct = (d["spend"] - avg_spend) / avg_spend * 100
            if abs(delta_pct) < 25:
                continue
            roas = (d["revenue"] / d["spend"]) if d["spend"] > 0 else 0.0
            scored.append((abs(delta_pct), platform, day, delta_pct, roas))

    if not scored:
        return ""
    scored.sort(key=lambda x: x[0], reverse=True)
    lines = ["## DÍAS ATÍPICOS POR PLATAFORMA (vs. el promedio de esa plataforma en el período)"]
    for _, platform, day, delta_pct, roas in scored[:max_lines]:
        direction = "pico" if delta_pct > 0 else "caída"
        lines.append(f"- [{platform}] {day}: {direction} de spend ({delta_pct:+.0f}% vs. promedio), ROAS ese día={roas:.2f}x")
    return "\n".join(lines)


def _build_comparison_context(
    metrics_1: List[Dict], metrics_2: List[Dict],
    date_from_1: date, date_to_1: date,
    date_from_2: date, date_to_2: date,
) -> str:
    """Period-over-period comparison table injected into the AI prompt."""
    def _agg(metrics: List[Dict]) -> dict:
        by_p: dict = defaultdict(lambda: {"spend": 0.0, "impressions": 0, "clicks": 0,
                                           "conversions": 0, "revenue": 0.0, "reach": 0})
        for m in metrics:
            p = m["platform"].upper()
            by_p[p]["spend"]       += m["spend"]
            by_p[p]["impressions"] += m["impressions"]
            by_p[p]["clicks"]      += m["clicks"]
            by_p[p]["conversions"] += m["conversions"]
            by_p[p]["revenue"]     += m["revenue"]
            by_p[p]["reach"]       += m.get("reach") or 0
        return by_p

    def _roas(d: dict) -> float: return d["revenue"] / d["spend"]   if d["spend"] > 0        else 0.0
    def _cpm(d: dict)  -> float: return d["spend"]   / d["impressions"] * 1000 if d["impressions"] > 0 else 0.0
    def _ctr(d: dict)  -> float: return d["clicks"]  / d["impressions"] * 100  if d["impressions"] > 0 else 0.0
    def _cpa(d: dict)  -> float: return d["spend"]   / d["conversions"]         if d["conversions"] > 0 else 0.0

    def _delta(v1: float, v2: float) -> str:
        if v1 == 0: return "—"
        p = (v2 - v1) / v1 * 100
        return f"{'+'if p>=0 else ''}{p:.1f}%"

    agg1 = _agg(metrics_1)
    agg2 = _agg(metrics_2)
    platforms = sorted(set(agg1) | set(agg2))
    ZERO: dict = {"spend": 0.0, "impressions": 0, "clicks": 0, "conversions": 0, "revenue": 0.0, "reach": 0}

    lines = [
        "## COMPARATIVA DE PERÍODOS",
        f"Período base  : {date_from_1} → {date_to_1}",
        f"Período actual: {date_from_2} → {date_to_2}",
        "",
        "| Plataforma | Spend base | Spend actual | Δ Spend | ROAS base | ROAS actual | Δ ROAS | "
        "CPM base | CPM actual | Δ CPM | CTR base | CTR actual | Δ CTR | CPA base | CPA actual | Δ CPA |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in platforms:
        d1, d2 = agg1.get(p, dict(ZERO)), agg2.get(p, dict(ZERO))
        lines.append(
            f"| **{p}** "
            f"| ${d1['spend']:.0f} | ${d2['spend']:.0f} | {_delta(d1['spend'], d2['spend'])} "
            f"| {_roas(d1):.2f}x | {_roas(d2):.2f}x | {_delta(_roas(d1), _roas(d2))} "
            f"| ${_cpm(d1):.2f} | ${_cpm(d2):.2f} | {_delta(_cpm(d1), _cpm(d2))} "
            f"| {_ctr(d1):.2f}% | {_ctr(d2):.2f}% | {_delta(_ctr(d1), _ctr(d2))} "
            f"| ${_cpa(d1):.2f} | ${_cpa(d2):.2f} | {_delta(_cpa(d1), _cpa(d2))} |"
        )

    # Totals row
    tot1 = {k: sum(d.get(k, 0) for d in agg1.values()) for k in ZERO}
    tot2 = {k: sum(d.get(k, 0) for d in agg2.values()) for k in ZERO}
    lines.append(
        f"| **TOTAL** "
        f"| ${tot1['spend']:.0f} | ${tot2['spend']:.0f} | {_delta(tot1['spend'], tot2['spend'])} "
        f"| {_roas(tot1):.2f}x | {_roas(tot2):.2f}x | {_delta(_roas(tot1), _roas(tot2))} "
        f"| ${_cpm(tot1):.2f} | ${_cpm(tot2):.2f} | {_delta(_cpm(tot1), _cpm(tot2))} "
        f"| {_ctr(tot1):.2f}% | {_ctr(tot2):.2f}% | {_delta(_ctr(tot1), _ctr(tot2))} "
        f"| ${_cpa(tot1):.2f} | ${_cpa(tot2):.2f} | {_delta(_cpa(tot1), _cpa(tot2))} |"
    )
    return "\n".join(lines)


CLAUDE_PERSONA = (
    "Sos Claude, analista cuantitativo de marketing digital. "
    "Estás en una sesión de análisis colaborativo con ChatGPT: el objetivo compartido es llegar a "
    "la mejor recomendación posible para este negocio, no ganar un argumento.\n\n"
    "Tu rol en esa colaboración: anclás el análisis en los datos reales. Calculás ratios derivados "
    "(costo por conversión, ROAS ajustado por volumen, eficiencia CPM vs CTR) y los comparás "
    "contra el comportamiento de las propias campañas: qué está rindiendo mejor o peor dentro "
    "del mismo conjunto de datos, y por qué. No imponés benchmarks externos — dejás que los "
    "datos hablen entre sí.\n\n"
    "Cuando ChatGPT propone algo, evalualo con datos: si tiene razón, reconocelo y construí sobre eso. "
    "Si está equivocado, demostralo con un número concreto. El desacuerdo debe tener evidencia, "
    "no solo una perspectiva diferente.\n\n"
    "Respondés en español rioplatense. Nunca usás frases vacías como 'buen rendimiento'."
)

GPT_PERSONA = (
    "Sos ChatGPT, estratega de crecimiento con foco en marketing de performance en Uruguay y LATAM. "
    "Estás en una sesión de análisis colaborativo con Claude: el objetivo compartido es llegar a "
    "la mejor recomendación posible para este negocio.\n\n"
    "Tu rol en esa colaboración: identificás oportunidades de escala y crecimiento que los datos "
    "sugieren pero que no son obvias. Sabés que en Uruguay TikTok tiene CPMs bajos y audiencia "
    "joven en crecimiento, que Meta es el canal de mayor alcance pero se satura, y que Google Search "
    "captura intención de compra real. Usás eso para proponer movimientos concretos.\n\n"
    "Cuando Claude analiza algo, tu trabajo es: (a) construir sobre lo que encontró si es sólido, "
    "(b) señalar lo que pasó por alto o interpretó mal, y (c) llegar más lejos — de los datos a "
    "una acción específica con número y plataforma. No das una segunda opinión paralela: respondés "
    "directamente a lo que dijo Claude y al usuario, avanzando el análisis.\n\n"
    "Cada respuesta tuya debe dejar el análisis en un estado más avanzado que cuando llegó. "
    "Respondés en español rioplatense."
)

LLAMA_PERSONA = (
    "Sos Llama, árbitro y sintetizador en una sesión de análisis de marketing. "
    "Claude y ChatGPT debatieron para llegar a la mejor recomendación posible — tu trabajo es "
    "cerrar ese proceso con un veredicto claro y accionable.\n\n"
    "No sos un diplomático: tomás partido basado en quién usó los datos mejor y cuyo argumento "
    "resiste más escrutinio. Si un argumento tiene una falla de datos, lo señalás.\n\n"
    "Tu veredicto es la conclusión que este equipo se lleva: cuál es la lectura correcta de los datos, "
    "qué acción tomar esta semana, y por qué. Respondés en español rioplatense."
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


async def _ask_claude_stream(system: str, prompt: str, max_tokens: int = 800) -> AsyncIterator[dict]:
    """Pide a Claude con adaptive thinking sin techo de effort (a pedido: el
    razonamiento no se acota, piensa todo lo que necesite) y consume el stream
    del SDK internamente — no se expone el pensamiento en vivo al frontend,
    solo el evento final {"kind": "done", ...}. Se sigue usando streaming a
    nivel SDK (en vez de messages.create) para evitar timeouts en prompts
    largos, aunque no se reenvíen los deltas.

    IMPORTANTE: el razonamiento consume del mismo presupuesto que max_tokens
    (no es un budget aparte) — al no capar el effort, max_tokens tiene que ser
    generoso (16000 en las llamadas del debate) para que un prompt largo no
    deje al modelo sin espacio para el texto final (stop_reason="max_tokens"
    con contenido vacío, sin ningún error visible). Sigue existiendo un riesgo
    residual: nada impide matemáticamente que el modelo use el presupuesto
    entero pensando, solo lo hace muy improbable con este margen."""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurado")
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    full_text: list[str] = []
    async with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive", "display": "summarized"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for event in stream:
            if event.type != "content_block_delta":
                continue
            delta = event.delta
            if delta.type == "thinking_delta":
                yield {"kind": "thinking", "delta": delta.thinking}
            elif delta.type == "text_delta":
                full_text.append(delta.text)
                yield {"kind": "text", "delta": delta.text}
        final = await stream.get_final_message()
        tokens = final.usage.input_tokens + final.usage.output_tokens
        if not full_text and final.stop_reason == "max_tokens":
            # Se quedó sin presupuesto pensando y no llegó a escribir nada —
            # mejor decirlo explícitamente que devolver una burbuja vacía.
            full_text.append(
                "*(se quedó sin espacio pensando y no llegó a responder — probá de nuevo o con una pregunta más puntual)*"
            )
    yield {"kind": "done", "content": "".join(full_text), "tokens": tokens}


async def _ask_gpt_stream(system: str, prompt: str, max_tokens: int = 800) -> AsyncIterator[dict]:
    """Pide a ChatGPT sobre gpt-5.4 (Responses API) con razonamiento real (no
    gpt-4o, que no tiene reasoning) al máximo effort disponible (a pedido: no
    acotar el razonamiento) y consume el stream internamente — no se expone el
    pensamiento en vivo al frontend, solo el evento final {"kind": "done", ...}.
    gpt-5.4 en vez del flagship gpt-5.5: mismo rango de razonamiento pero más
    barato/rápido, mejor fit para un debate conversacional turno a turno que
    coding extremo. Con effort "high" y sin techo, max_output_tokens tiene que
    ser generoso (16000 en las llamadas del debate) para que el modelo no se
    quede sin espacio para el texto final en prompts largos."""
    try:
        import openai as _openai
    except ImportError:
        raise RuntimeError("Paquete 'openai' no instalado")
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY no configurado")
    client = _openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    full_text: list[str] = []
    tokens = 0
    stream = await client.responses.create(
        model="gpt-5.4",
        instructions=system,
        input=prompt,
        max_output_tokens=max_tokens,
        reasoning={"effort": "high", "summary": "auto"},
        stream=True,
    )
    async for event in stream:
        etype = getattr(event, "type", "") or ""
        # Nombre de evento no 100% confirmado contra la doc pública al momento
        # de escribir esto — chequeo por substring en vez de un string exacto
        # para no romper silenciosamente si el nombre real difiere un poco.
        if "reasoning_summary_text" in etype and etype.endswith(".delta"):
            piece = getattr(event, "delta", "")
            yield {"kind": "thinking", "delta": piece if isinstance(piece, str) else str(piece)}
        elif etype == "response.output_text.delta":
            full_text.append(event.delta)
            yield {"kind": "text", "delta": event.delta}
        elif etype in ("response.completed", "response.incomplete"):
            usage = event.response.usage
            tokens = (usage.input_tokens or 0) + (usage.output_tokens or 0)
            incomplete = getattr(event.response, "incomplete_details", None)
            if not full_text and incomplete and incomplete.reason == "max_output_tokens":
                # Se quedó sin presupuesto razonando y no llegó a escribir nada.
                full_text.append(
                    "*(se quedó sin espacio pensando y no llegó a responder — probá de nuevo o con una pregunta más puntual)*"
                )
    yield {"kind": "done", "content": "".join(full_text), "tokens": tokens}


async def _fetch_web_context(date_from: date, date_to: date) -> Tuple[str, int]:
    """ChatGPT busca contexto real del período vía web search (gpt-4o-search-preview)."""
    try:
        import openai as _openai
    except ImportError:
        raise RuntimeError("Paquete 'openai' no instalado")
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY no configurado")

    prompt = (
        f"Soy analista de marketing digital en Uruguay. Necesito contexto real del período "
        f"{date_from} al {date_to} para interpretar una SERIE DIARIA de métricas de campañas — "
        f"o sea, voy a cruzar cada hallazgo tuyo contra el número exacto de un día puntual dentro "
        f"de ese rango. Un hallazgo sin fecha específica no me sirve para nada.\n\n"
        f"Buscá en portales uruguayos (elpais.com.uy, elobservador.com.uy, ladiaria.com.uy, "
        f"montevideo.com.uy, subrayado.com.uy, 180.com.uy) y resumí en español:\n\n"
        f"1. **Contexto cultural y social Uruguay**: noticias, eventos o tendencias del período "
        f"que hayan captado la atención del público uruguayo — deportes, política, cultura "
        f"popular, redes sociales, fenómenos virales locales — con la fecha exacta en que pasó "
        f"o dominó la conversación.\n"
        f"2. **Eventos comerciales en Uruguay**: feriados, fechas especiales, campañas de "
        f"descuento (Hot Sale, Black Friday, Cyber Monday, vuelta al cole, Día de la Madre, etc.) "
        f"que caigan dentro de {date_from} y {date_to} — con su fecha exacta, no \"a fin de mes\".\n"
        f"3. **Contexto económico Uruguay**: tipo de cambio USD/UYU, inflación, noticias "
        f"económicas puntuales del período que afecten el consumo digital, con fecha.\n"
        f"4. **Novedades de plataformas publicitarias** (Meta Ads, Google Ads, TikTok Ads): "
        f"cambios de algoritmo o políticas del período, con fecha si la tiene.\n\n"
        f"FORMATO OBLIGATORIO: cada hallazgo como '- DD/MM: hallazgo (fuente si aplica)'. Si no "
        f"podés precisar el día exacto, no lo incluyas — preferí 3 hallazgos con fecha certera "
        f"a 10 vagos. Priorizá el punto 1. Máximo 500 palabras."
    )

    client = _openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    resp = await client.chat.completions.create(
        model="gpt-4o-search-preview",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
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
    metrics_2: List[Dict] | None = None,
    date_from_2: date | None = None,
    date_to_2: date | None = None,
) -> AsyncIterator[dict]:
    """Sequential debate: ChatGPT fetches web context and speaks first, Claude responds second
    with the quantitative rebuttal/validation."""
    compact_ctx = _build_compact_context(metrics, email_data, whatsapp_data)
    daily_ctx   = _build_daily_series_context(metrics)
    history_str = _build_history_str(history)
    is_first_turn = not any(m.get("speaker") in ("Claude", "ChatGPT") for m in history)

    data_section = f"Datos del período {date_from} al {date_to}:\n{compact_ctx}"
    if daily_ctx:
        data_section += f"\n\n{daily_ctx}"
    if metrics_2 and date_from_2 and date_to_2:
        compact_ctx_2   = _build_compact_context(metrics_2, [], [])
        comparison_ctx  = _build_comparison_context(
            metrics_2, metrics, date_from_2, date_to_2, date_from, date_to
        )
        data_section = (
            f"Datos período base ({date_from_2} al {date_to_2}):\n{compact_ctx_2}\n\n"
            f"Datos período actual ({date_from} al {date_to}):\n{compact_ctx}\n\n"
            f"{comparison_ctx}"
        )
        if daily_ctx:
            data_section += f"\n\n{daily_ctx}"

    # ── Step 0: ChatGPT busca contexto externo del período ────────────────────
    # Aviso explícito de que arranca la búsqueda: sin esto, el frontend mostraba
    # a Claude como "pensando" desde el primer instante aunque todavía no había
    # arrancado — recién empieza después de este paso.
    yield {"type": "web_search_start", "speaker": "ChatGPT"}
    web_context = ""
    web_ctx_tokens = 0
    try:
        web_context, web_ctx_tokens = await _fetch_web_context(date_from, date_to)
        yield {"type": "web_context", "speaker": "ChatGPT", "content": web_context}
    except Exception:
        pass  # continúa sin contexto web si falla

    web_section = (
        f"\n\n## CONTEXTO EXTERNO DEL PERÍODO (búsqueda web en tiempo real)\n{web_context}"
        if web_context else ""
    )

    base_parts = [
        *(([history_str]) if history_str else []),
        data_section + web_section,
        f"El usuario dice: **{user_message}**",
    ]

    def _extract_progress(buf: str, already: int) -> Tuple[List[str], int]:
        """Extrae los títulos en negrita ("**Calculando X**") que el modelo va
        marcando en su propio resumen de pensamiento, como highlights cortos de
        progreso — sin exponer el razonamiento completo."""
        headers = re.findall(r"\*\*([^*]{3,80})\*\*", buf)
        new = headers[already:]
        return new, len(headers)

    # ── Step 1: ChatGPT — ya tiene el contexto fresco, arranca el análisis ────
    web_ctx_note = (
        "\nUsá tu propia búsqueda de contexto real del período (arriba, en "
        "'## CONTEXTO EXTERNO DEL PERÍODO', con fecha exacta por hallazgo). Cruzala con la "
        "'## SERIE DIARIA POR PLATAFORMA': para cada hallazgo con fecha, fijate qué pasó ese "
        "día puntual en la serie (no en el promedio del período) y decilo explícitamente: "
        "'el DD/MM hubo un pico/caída de spend/CTR de X, coincide con [evento]'. Si un evento "
        "no coincide con ningún movimiento real ese día, decilo también — es información útil "
        "('no explica nada, hay que buscar otra causa').\n"
        if web_context else ""
    )
    if is_first_turn:
        gpt_instructions = (
            "Primer turno — analizá la pregunta del usuario con datos concretos:\n"
            + web_ctx_note +
            "1. Usá números exactos de los datos: ROAS, CTR, CPC, CPM por campaña. Nada de promedios vagos.\n"
            "2. Identificá la campaña con mejor y peor desempeño y una lectura estratégica de por qué "
            "(¿es el creativo, la audiencia, la puja, la plataforma? ¿O algo del contexto externo del período?).\n"
            "3. Identificá una oportunidad de escala o un riesgo concreto que emerja de cruzar el contexto "
            "con los datos.\n"
            "4. Terminá con una conclusión fuerte y específica que Claude pueda validar o desafiar con "
            "números más finos — dejale a él el trabajo cuantitativo de precisión."
        )
    else:
        last_claude = next((m["content"] for m in reversed(history) if m.get("speaker") == "Claude"), None)
        gpt_instructions = (
            "Siguiente turno — avanzá el análisis, no lo repitas:\n"
            + (f"Claude propuso: \"{last_claude[:600]}\"\n\n"
               "Evaluá esa propuesta desde tu rol estratégico. Si tiene razón en algo, reconocelo y "
               "construí sobre eso. Si falta contexto o hay una oportunidad de escala que no vio, mostrala. "
               "Luego avanzá: ¿qué acción concreta emerge de cruzar tu lectura con la de Claude?" if last_claude
               else "Profundizá con evidencia nueva de los datos y avanzá hacia una conclusión accionable.")
        )

    gpt_prompt = "\n\n".join([*base_parts, gpt_instructions])
    gpt_content = ""
    gpt_tokens = 0
    gpt_progress_buf = ""
    gpt_progress_seen = 0
    async for chunk in _ask_gpt_stream(GPT_PERSONA, gpt_prompt, 16000):
        if chunk["kind"] == "thinking":
            gpt_progress_buf += chunk["delta"]
            new_headers, gpt_progress_seen = _extract_progress(gpt_progress_buf, gpt_progress_seen)
            for h in new_headers:
                yield {"type": "thinking_progress", "speaker": "ChatGPT", "text": h.strip()}
        elif chunk["kind"] == "done":
            gpt_content = chunk["content"]
            gpt_tokens = chunk["tokens"]
    yield {"type": "message", "speaker": "ChatGPT", "role": "debate", "content": gpt_content}

    # ── Step 2: Claude — lee la pregunta del usuario Y la lectura de ChatGPT ──
    if is_first_turn:
        claude_instructions = (
            f"ChatGPT ya buscó contexto real del período y concluyó:\n\"{gpt_content}\"\n\n"
            "Tu trabajo es el análisis cuantitativo riguroso que haga avanzar la conversación:\n"
            "1. Usá números exactos de los datos: ROAS, CTR, CPC, CPM por campaña. Nada de promedios vagos.\n"
            "2. Identificá la campaña con mejor y peor desempeño y explicá la CAUSA RAÍZ.\n"
            "3. Validá o corregí con datos concretos los hallazgos de contexto que trajo ChatGPT — "
            "¿el pico o caída que él marcó realmente se ve en la serie diaria, con la magnitud que dice? "
            "Si no coincide, decilo.\n"
            "4. Calculá algo no obvio: costo por conversión real, eficiencia relativa entre plataformas, "
            "o la diferencia de ROAS entre las campañas de mayor y menor inversión.\n"
            "5. Terminá con una conclusión fuerte y específica."
        )
    else:
        claude_instructions = (
            f"ChatGPT acaba de responder:\n\"{gpt_content}\"\n\n"
            "Avanzá el análisis con rigor cuantitativo:\n"
            "1. Tomá el punto más sólido de ChatGPT y validalo o cuestionalo con un número concreto.\n"
            "2. Corregí o matizá donde haga falta, con dato concreto.\n"
            "3. Proponé la próxima acción que resulta de todo lo discutido hasta ahora, con número y plataforma.\n"
            "El análisis debe converger hacia algo accionable, no expandirse indefinidamente."
        )

    claude_prompt = "\n\n".join([*base_parts, claude_instructions])
    claude_content = ""
    claude_tokens = 0
    claude_progress_buf = ""
    claude_progress_seen = 0
    async for chunk in _ask_claude_stream(CLAUDE_PERSONA, claude_prompt, 16000):
        if chunk["kind"] == "thinking":
            claude_progress_buf += chunk["delta"]
            new_headers, claude_progress_seen = _extract_progress(claude_progress_buf, claude_progress_seen)
            for h in new_headers:
                yield {"type": "thinking_progress", "speaker": "Claude", "text": h.strip()}
        elif chunk["kind"] == "done":
            claude_content = chunk["content"]
            claude_tokens = chunk["tokens"]
    yield {"type": "message", "speaker": "Claude", "role": "debate", "content": claude_content}

    tokens_by_model = {"Claude": claude_tokens, "ChatGPT": gpt_tokens + web_ctx_tokens}
    yield {"type": "tokens", "total": sum(tokens_by_model.values()), "by_model": tokens_by_model}


async def stream_llama_verdict(
    history: List[Dict],
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
    metrics_2: List[Dict] | None = None,
    date_from_2: date | None = None,
    date_to_2: date | None = None,
) -> AsyncIterator[dict]:
    """Llama reads the full debate and gives an on-demand verdict."""
    compact_ctx    = _build_compact_context(metrics, email_data, whatsapp_data)
    highlights_ctx = _build_daily_highlights(metrics)
    history_str    = _build_history_str(history, max_items=24)

    data_section = f"Datos de referencia ({date_from} al {date_to}):\n{compact_ctx}"
    if highlights_ctx:
        data_section += f"\n\n{highlights_ctx}"
    if metrics_2 and date_from_2 and date_to_2:
        comparison_ctx = _build_comparison_context(
            metrics_2, metrics, date_from_2, date_to_2, date_from, date_to
        )
        data_section = f"{comparison_ctx}\n\nDetalle período actual:\n{compact_ctx}"
        if highlights_ctx:
            data_section += f"\n\n{highlights_ctx}"

    prompt = (
        f"Sos el árbitro de este debate sobre campañas de marketing ({date_from} al {date_to}).\n\n"
        f"{history_str}\n\n"
        f"{data_section}\n\n"
        "Tu veredicto debe ser analítico y concreto — no diplomático. Estructuralo así:\n\n"
        "**1. Desacuerdo central**\n"
        "En 2-3 oraciones: cuál es la tensión real entre los dos analistas. No resumas todo el debate, "
        "identificá el punto exacto donde difieren y por qué importa.\n\n"
        "**2. Veredicto**\n"
        "¿Quién tiene el argumento más sólido y por qué? Tomá partido claro — no 'ambos tienen razón'. "
        "Justificá con al menos 2 datos concretos de la conversación o de los datos. "
        "Parte de tu criterio para elegir: ¿quién usó evidencia con fecha puntual (un día de "
        "'## DÍAS ATÍPICOS' o un hallazgo del contexto cultural) en vez de hablar del período en "
        "general? Eso pesa más que una afirmación genérica aunque suene razonable. "
        "Si los datos no son concluyentes, decilo y explicá qué información faltaría para decidir.\n"
        "Incluí una tabla markdown comparando las posiciones si ayuda a ilustrar el veredicto.\n\n"
        "**3. Plan de acción**\n"
        "3 acciones ejecutables ordenadas por impacto esperado. Para cada una: qué hacer, en qué plataforma/campaña, "
        "y qué métrica debería mejorar como resultado. Sé específico — nada de 'optimizar el presupuesto'."
    )

    content, tokens = await _ask_llama(LLAMA_PERSONA, prompt, 1400)
    yield {"type": "message", "speaker": "Llama", "role": "synthesis", "content": content}
    yield {"type": "tokens", "total": tokens, "by_model": {"Llama": tokens}}
