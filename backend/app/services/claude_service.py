from typing import List, Dict


def _build_metrics_context(metrics: List[Dict]) -> str:
    if not metrics:
        return "No hay métricas disponibles para este período."

    lines = []
    for m in metrics:
        reach = m.get("reach") or 0
        cpm   = m.get("cpm")   or 0.0
        lines.append(
            f"- [{m['platform'].upper()}] {m['campaign_name']}: "
            f"Inversión=${m['spend']:.2f} | Impresiones={m['impressions']:,} | "
            f"Alcance={reach:,} | CPM=${cpm:.2f} | "
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
