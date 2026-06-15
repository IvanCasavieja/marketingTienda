"""Datos ficticios para presentaciones — activo cuando DEMO_MODE=True en .env."""
from datetime import date, timedelta
import random

_PLATFORMS = ["meta", "google_ads", "tiktok", "dv360"]

# Campañas ficticias por plataforma
_CAMPAIGNS: dict[str, list[dict]] = {
    "meta": [
        {"id": "23840001234560001", "name": "Verano 2025 — Prospecting"},
        {"id": "23840001234560002", "name": "Retargeting — Carrito abandonado"},
        {"id": "23840001234560003", "name": "Brand Awareness — Latam"},
    ],
    "google_ads": [
        {"id": "180000001", "name": "Search — Marca + Competencia"},
        {"id": "180000002", "name": "Shopping — Catálogo completo"},
        {"id": "180000003", "name": "YouTube — Video 15s Awareness"},
    ],
    "tiktok": [
        {"id": "7320001111", "name": "TikTok TopView — Lanzamiento"},
        {"id": "7320001112", "name": "In-Feed Ads — Conversión"},
    ],
    "dv360": [
        {"id": "DV-4400001", "name": "Programática — Display Premium"},
        {"id": "DV-4400002", "name": "Programática — Video pre-roll"},
    ],
}

# Parámetros base de rendimiento por plataforma (diarios, por campaña)
_BASE_METRICS: dict[str, dict] = {
    "meta": {
        "spend_per_day":   580.0,
        "ctr":             1.95,
        "cpm":             7.20,
        "cpc":             0.37,
        "conv_rate":       0.032,
        "roas":            3.85,
    },
    "google_ads": {
        "spend_per_day":   420.0,
        "ctr":             3.10,
        "cpm":             5.80,
        "cpc":             0.19,
        "conv_rate":       0.045,
        "roas":            4.20,
    },
    "tiktok": {
        "spend_per_day":   210.0,
        "ctr":             1.30,
        "cpm":             9.50,
        "cpc":             0.73,
        "conv_rate":       0.018,
        "roas":            2.10,
    },
    "dv360": {
        "spend_per_day":   180.0,
        "ctr":             0.45,
        "cpm":             3.20,
        "cpc":             0.71,
        "conv_rate":       0.009,
        "roas":            1.75,
    },
}

_rng = random.Random(42)  # seed fija para reproducibilidad


def _jitter(value: float, pct: float = 0.18) -> float:
    return value * (1 + _rng.uniform(-pct, pct))


def get_demo_metrics_by_day(
    date_from: date,
    date_to: date,
    platforms: list[str] | None = None,
) -> list[dict]:
    """Devuelve registros diarios por campaña — equivalente a get_metrics()."""
    active_platforms = platforms or _PLATFORMS
    rows: list[dict] = []
    current = date_from
    while current <= date_to:
        for platform in active_platforms:
            if platform not in _BASE_METRICS:
                continue
            base = _BASE_METRICS[platform]
            campaigns = _CAMPAIGNS.get(platform, [])
            for camp in campaigns:
                spend       = round(_jitter(base["spend_per_day"] / len(campaigns)), 2)
                impressions = int(spend / (base["cpm"] / 1000) * _jitter(1.0, 0.12))
                clicks      = int(impressions * (base["ctr"] / 100) * _jitter(1.0, 0.15))
                conversions = int(clicks * base["conv_rate"] * _jitter(1.0, 0.20))
                revenue     = round(spend * base["roas"] * _jitter(1.0, 0.12), 2)
                rows.append({
                    "platform":       platform,
                    "campaign_id":    camp["id"],
                    "campaign_name":  camp["name"],
                    "date":           str(current),
                    "impressions":    max(impressions, 0),
                    "clicks":         max(clicks, 0),
                    "spend":          spend,
                    "conversions":    max(conversions, 0),
                    "revenue":        revenue,
                    "reach":          int(impressions * 0.82),
                    "ctr":            round(base["ctr"] * _jitter(1.0, 0.10), 2),
                    "cpc":            round(base["cpc"] * _jitter(1.0, 0.10), 2),
                    "cpm":            round(base["cpm"] * _jitter(1.0, 0.10), 2),
                    "roas":           round(base["roas"] * _jitter(1.0, 0.10), 2),
                })
        current += timedelta(days=1)
    return rows


def get_demo_summary(date_from: date, date_to: date) -> list[dict]:
    """Devuelve resumen agregado por plataforma — equivalente a get_summary()."""
    rows = get_demo_metrics_by_day(date_from, date_to)
    aggregated: dict[str, dict] = {}
    for row in rows:
        p = row["platform"]
        if p not in aggregated:
            aggregated[p] = {
                "platform":    p,
                "impressions": 0,
                "clicks":      0,
                "spend":       0.0,
                "conversions": 0,
                "revenue":     0.0,
                "ctr_sum":     0.0,
                "roas_sum":    0.0,
                "count":       0,
                "last_date":   None,
            }
        a = aggregated[p]
        a["impressions"] += row["impressions"]
        a["clicks"]      += row["clicks"]
        a["spend"]       += row["spend"]
        a["conversions"] += row["conversions"]
        a["revenue"]     += row["revenue"]
        a["ctr_sum"]     += row["ctr"]
        a["roas_sum"]    += row["roas"]
        a["count"]       += 1
        if a["last_date"] is None or row["date"] > a["last_date"]:
            a["last_date"] = row["date"]

    result = []
    for p, a in aggregated.items():
        n = max(a["count"], 1)
        result.append({
            "platform":    p,
            "impressions": a["impressions"],
            "clicks":      a["clicks"],
            "spend":       round(a["spend"], 2),
            "conversions": a["conversions"],
            "revenue":     round(a["revenue"], 2),
            "avg_ctr":     round(a["ctr_sum"] / n, 2),
            "avg_roas":    round(a["roas_sum"] / n, 2),
            "last_date":   a["last_date"],
        })
    return result
