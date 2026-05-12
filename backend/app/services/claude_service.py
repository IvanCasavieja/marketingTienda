import anthropic
from datetime import date
from typing import List, Dict
from app.core.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "result": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "result": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "result": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "result": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "analysis_type": "cross_platform",
    }


ANALYSIS_HANDLERS = {
    "full_report": generate_full_report,
    "anomaly_detection": generate_anomaly_detection,
    "optimization": generate_optimization_recommendations,
    "cross_platform": generate_cross_platform_comparison,
}
