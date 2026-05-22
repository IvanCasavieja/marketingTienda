import asyncio
import anthropic
from datetime import date
from typing import List, Dict, AsyncGenerator
from app.core.config import settings


def _call_claude(fn, **kwargs) -> anthropic.types.Message:
    try:
        return fn(**kwargs)
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Claude API unreachable: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected Claude error: {e}") from e

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client

SYSTEM_PROMPT = """Eres un analista experto en marketing digital con profundo conocimiento en Meta Ads,
Google Ads, TikTok Ads, DV360 y Salesforce Marketing Cloud. Tu rol es analizar datos de campañas
y comunicaciones de marketing para generar insights accionables, detectar anomalías y recomendar
optimizaciones concretas. Siempre respondes en español, con datos precisos y recomendaciones
priorizadas por impacto en negocio. Eres directo, específico y evitas generalidades."""


def _build_metrics_context(metrics: List[Dict]) -> str:
    if not metrics:
        return "No hay métricas disponibles para este período."

    lines = []
    for m in metrics:
        lines.append(
            f"- [{m['platform'].upper()}] {m['campaign_name']}: "
            f"Inversión=${m['spend']:.2f} | Impresiones={m['impressions']:,} | "
            f"Clicks={m['clicks']:,} | CTR={m['ctr']:.2f}% | CPC=${m['cpc']:.2f} | "
            f"Conversiones={m['conversions']} | Revenue=${m['revenue']:.2f} | ROAS={m['roas']:.2f}x"
        )
    return "\n".join(lines)


def _build_sfmc_context(email_data: List[Dict], whatsapp_data: List[Dict]) -> str:
    lines = []
    for e in email_data:
        lines.append(
            f"- [EMAIL] {e['name']}: Enviados={e['sent']:,} | Apertura={e['open_rate']}% | "
            f"Clicks={e['click_rate']}% | Bounce={e['bounce_rate']}% | Unsubs={e['unsubscribed']}"
        )
    for w in whatsapp_data:
        lines.append(
            f"- [WHATSAPP] {w['name']}: Enviados={w['sent']:,} | Entregados={w['delivery_rate']}% | "
            f"Leídos={w['read_rate']}%"
        )
    return "\n".join(lines) if lines else "Sin datos de SFMC para este período."


async def generate_full_report(
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
) -> Dict:
    metrics_ctx = _build_metrics_context(metrics)
    sfmc_ctx = _build_sfmc_context(email_data, whatsapp_data)

    prompt = f"""Analiza el rendimiento de marketing del período {date_from} al {date_to}.

## DATOS DE CAMPAÑAS PAGAS (Meta / Google Ads / TikTok / DV360)
{metrics_ctx}

## DATOS DE COMUNICACIONES (Salesforce Marketing Cloud - Email + WhatsApp)
{sfmc_ctx}

Genera un reporte ejecutivo completo con las siguientes secciones:

1. **RESUMEN EJECUTIVO** (3-5 puntos clave del período)
2. **ANÁLISIS POR PLATAFORMA** (rendimiento y estado de cada canal)
3. **ANÁLISIS CROSS-CHANNEL** (cómo se complementan los canales, funnel completo)
4. **TOP 3 OPORTUNIDADES DE OPTIMIZACIÓN** (con acción concreta, plataforma y estimado de impacto)
5. **ALERTAS Y ANOMALÍAS** (si las hay)
6. **PRÓXIMOS PASOS RECOMENDADOS** (ordenados por prioridad)"""

    def _sync():
        return _call_claude(
            _get_client().beta.prompt_caching.messages.create,
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )

    response = await asyncio.to_thread(_sync)
    return {
        "result": response.content[0].text,
        "input_tokens": getattr(response.usage, "input_tokens", 0),
        "output_tokens": getattr(response.usage, "output_tokens", 0),
        "analysis_type": "full_report",
    }


async def generate_anomaly_detection(metrics: List[Dict], date_from: date, date_to: date) -> Dict:
    metrics_ctx = _build_metrics_context(metrics)

    prompt = f"""Analiza estos datos de campañas del {date_from} al {date_to} y detecta anomalías:

{metrics_ctx}

Identifica:
1. **ANOMALÍAS CRÍTICAS** (gasto anormal, CTR muy bajo/alto, ROAS negativo, conversiones en cero)
2. **TENDENCIAS PREOCUPANTES** (degradación de performance progresiva)
3. **OPORTUNIDADES PERDIDAS** (presupuesto mal asignado, campañas con alto ROAS y bajo presupuesto)
4. **ACCIONES INMEDIATAS** necesarias en las próximas 24-48 horas

Para cada anomalía indica: plataforma, campaña afectada, magnitud del problema y acción recomendada."""

    def _sync():
        return _call_claude(
            _get_client().messages.create,
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )

    response = await asyncio.to_thread(_sync)
    return {
        "result": response.content[0].text,
        "input_tokens": getattr(response.usage, "input_tokens", 0),
        "output_tokens": getattr(response.usage, "output_tokens", 0),
        "analysis_type": "anomaly_detection",
    }


async def generate_optimization_recommendations(metrics: List[Dict], date_from: date, date_to: date) -> Dict:
    metrics_ctx = _build_metrics_context(metrics)

    prompt = f"""Con base en estos datos de campañas del {date_from} al {date_to}:

{metrics_ctx}

Genera recomendaciones de optimización específicas y accionables:

1. **REDISTRIBUCIÓN DE PRESUPUESTO** (qué plataformas merecen más/menos inversión y por qué)
2. **OPTIMIZACIÓN DE PUJAS** (campañas con CPC/CPM fuera de benchmark)
3. **AUDIENCIAS Y SEGMENTACIÓN** (recomendaciones basadas en CTR y tasa de conversión)
4. **CREATIVOS Y MENSAJES** (inferencias sobre qué puede estar fallando o funcionando bien)
5. **ESTRATEGIA CROSS-PLATFORM** (cómo combinar mejor los canales para maximizar ROAS)

Para cada recomendación incluye: plataforma, acción específica, métricas que mejoraría y % de mejora estimado."""

    def _sync():
        return _call_claude(
            _get_client().messages.create,
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )

    response = await asyncio.to_thread(_sync)
    return {
        "result": response.content[0].text,
        "input_tokens": getattr(response.usage, "input_tokens", 0),
        "output_tokens": getattr(response.usage, "output_tokens", 0),
        "analysis_type": "optimization",
    }


async def generate_cross_platform_comparison(metrics: List[Dict], date_from: date, date_to: date) -> Dict:
    metrics_ctx = _build_metrics_context(metrics)

    prompt = f"""Compara el rendimiento entre plataformas para el período {date_from} al {date_to}:

{metrics_ctx}

Genera una comparativa detallada:
1. **TABLA COMPARATIVA** de KPIs por plataforma (ROAS, CPC, CTR, CPM, Costo por conversión)
2. **RANKING DE EFICIENCIA** (qué plataforma entrega mejor resultado por dólar invertido)
3. **ANÁLISIS DE AUDIENCIA** (inferencias sobre calidad de tráfico por plataforma)
4. **MIX ÓPTIMO** recomendado de inversión entre plataformas
5. **CONCLUSIÓN ESTRATÉGICA** (qué plataforma priorizar según el objetivo de negocio)"""

    def _sync():
        return _call_claude(
            _get_client().messages.create,
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )

    response = await asyncio.to_thread(_sync)
    return {
        "result": response.content[0].text,
        "input_tokens": getattr(response.usage, "input_tokens", 0),
        "output_tokens": getattr(response.usage, "output_tokens", 0),
        "analysis_type": "cross_platform",
    }


ANALYSIS_HANDLERS = {
    "full_report": generate_full_report,
    "anomaly_detection": generate_anomaly_detection,
    "optimization": generate_optimization_recommendations,
    "cross_platform": generate_cross_platform_comparison,
}

# ── Async streaming ────────────────────────────────────────────────────────────

_async_client: anthropic.AsyncAnthropic | None = None


def _get_async_client() -> anthropic.AsyncAnthropic:
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _async_client


def _build_stream_params(
    analysis_type: str,
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
) -> tuple[str, list, int]:
    """Returns (prompt, system_with_cache, max_tokens) for the given analysis type."""
    metrics_ctx = _build_metrics_context(metrics)
    system_cached = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    if analysis_type == "full_report":
        sfmc_ctx = _build_sfmc_context(email_data, whatsapp_data)
        prompt = (
            f"Analiza el rendimiento de marketing del período {date_from} al {date_to}.\n\n"
            f"## DATOS DE CAMPAÑAS PAGAS\n{metrics_ctx}\n\n"
            f"## DATOS DE COMUNICACIONES (SFMC - Email + WhatsApp)\n{sfmc_ctx}\n\n"
            "Genera un reporte ejecutivo con:\n"
            "1. **RESUMEN EJECUTIVO**\n2. **ANÁLISIS POR PLATAFORMA**\n"
            "3. **ANÁLISIS CROSS-CHANNEL**\n4. **TOP 3 OPORTUNIDADES DE OPTIMIZACIÓN**\n"
            "5. **ALERTAS Y ANOMALÍAS**\n6. **PRÓXIMOS PASOS RECOMENDADOS**"
        )
        return prompt, system_cached, 4096

    if analysis_type == "anomaly_detection":
        prompt = (
            f"Analiza estos datos de campañas del {date_from} al {date_to} y detecta anomalías:\n\n{metrics_ctx}\n\n"
            "Identifica:\n1. **ANOMALÍAS CRÍTICAS**\n2. **TENDENCIAS PREOCUPANTES**\n"
            "3. **OPORTUNIDADES PERDIDAS**\n4. **ACCIONES INMEDIATAS** (próximas 24-48h)"
        )
        return prompt, system_cached, 2048

    if analysis_type == "optimization":
        prompt = (
            f"Con base en estos datos del {date_from} al {date_to}:\n\n{metrics_ctx}\n\n"
            "Genera recomendaciones de optimización:\n1. **REDISTRIBUCIÓN DE PRESUPUESTO**\n"
            "2. **OPTIMIZACIÓN DE PUJAS**\n3. **AUDIENCIAS Y SEGMENTACIÓN**\n"
            "4. **CREATIVOS Y MENSAJES**\n5. **ESTRATEGIA CROSS-PLATFORM**"
        )
        return prompt, system_cached, 2048

    if analysis_type == "cross_platform":
        prompt = (
            f"Compara el rendimiento entre plataformas del {date_from} al {date_to}:\n\n{metrics_ctx}\n\n"
            "Genera:\n1. **TABLA COMPARATIVA** de KPIs\n2. **RANKING DE EFICIENCIA**\n"
            "3. **ANÁLISIS DE AUDIENCIA**\n4. **MIX ÓPTIMO** recomendado\n5. **CONCLUSIÓN ESTRATÉGICA**"
        )
        return prompt, system_cached, 2048

    raise ValueError(f"Unknown streamable analysis type: {analysis_type}")


async def stream_analysis(
    analysis_type: str,
    metrics: List[Dict],
    email_data: List[Dict],
    whatsapp_data: List[Dict],
    date_from: date,
    date_to: date,
) -> AsyncGenerator[dict, None]:
    """Yields dicts: {"type": "text", "text": str} | {"type": "done", "input_tokens": int, "output_tokens": int}"""
    prompt, system_cached, max_tokens = _build_stream_params(
        analysis_type, metrics, email_data, whatsapp_data, date_from, date_to
    )
    try:
        async with _get_async_client().beta.prompt_caching.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system_cached,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield {"type": "text", "text": text}
            final = await stream.get_final_message()
            yield {
                "type": "done",
                "input_tokens": getattr(final.usage, "input_tokens", 0),
                "output_tokens": getattr(final.usage, "output_tokens", 0),
            }
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Claude API unreachable: {e}") from e
