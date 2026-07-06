"""
Genera backend/app/data/meta_fake_campaigns.json — data ficticia de 5 campañas
de Meta Ads con 3 meses de métricas diarias, con el mismo esquema que usa
la tabla campaign_metrics.

Este fixture reemplaza la data en vivo que antes venía de la conexión real
con Meta (ver notas de reactivación en app/services/metrics_service.py y
app/connectors/__init__.py). Se puede volver a correr este script para
regenerar el fixture con otros valores random.

Uso: python scripts/generate_meta_fake_data.py
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "meta_fake_campaigns.json"

DATE_TO = date(2026, 7, 6)
DATE_FROM = DATE_TO - timedelta(days=89)  # 90 días ~ 3 meses

ACCOUNTS = [
    "120987654321098",
    "120912345678901",
]

CAMPAIGNS = [
    {"campaign_id": "23851000000010001", "campaign_name": "Meta | Awareness Video | Marca",        "account_id": ACCOUNTS[0], "impr_range": (40000, 120000), "ctr_range": (0.8, 1.8), "cpm_range": (25, 55), "cvr_range": (0.5, 1.5), "aov_range": (30, 70)},
    {"campaign_id": "23851000000010002", "campaign_name": "Meta | Remarketing Carrito Abandonado",  "account_id": ACCOUNTS[0], "impr_range": (8000, 25000),  "ctr_range": (2.0, 4.0), "cpm_range": (15, 35), "cvr_range": (3.0, 7.0), "aov_range": (40, 90)},
    {"campaign_id": "23851000000010003", "campaign_name": "Meta | Lanzamiento Categoria Hogar",     "account_id": ACCOUNTS[0], "impr_range": (15000, 45000), "ctr_range": (1.2, 2.5), "cpm_range": (20, 40), "cvr_range": (1.5, 3.5), "aov_range": (35, 80)},
    {"campaign_id": "23851000000010004", "campaign_name": "Meta | Promo Fin de Semana",             "account_id": ACCOUNTS[1], "impr_range": (20000, 60000), "ctr_range": (1.5, 3.2), "cpm_range": (18, 38), "cvr_range": (2.0, 5.0), "aov_range": (25, 60)},
    {"campaign_id": "23851000000010005", "campaign_name": "Meta | Ecommerce Conversiones",          "account_id": ACCOUNTS[1], "impr_range": (25000, 70000), "ctr_range": (1.8, 3.5), "cpm_range": (22, 45), "cvr_range": (2.5, 6.0), "aov_range": (30, 75)},
]


def daterange(d_from: date, d_to: date):
    days = (d_to - d_from).days
    for i in range(days + 1):
        yield d_from + timedelta(days=i)


def safe_divide(a: float, b: float) -> float:
    return a / b if b else 0.0


def gen_row(camp: dict, day: date) -> dict:
    impressions = random.randint(*camp["impr_range"])
    ctr_pct = random.uniform(*camp["ctr_range"])
    clicks = max(1, round(impressions * ctr_pct / 100))
    cpm = random.uniform(*camp["cpm_range"])
    spend = round(impressions / 1000 * cpm, 2)
    cvr_pct = random.uniform(*camp["cvr_range"])
    conversions = round(clicks * cvr_pct / 100)
    aov = random.uniform(*camp["aov_range"])
    revenue = round(conversions * aov, 2)
    reach = round(impressions * random.uniform(0.6, 0.85))

    return {
        "platform": "meta",
        "account_id": camp["account_id"],
        "campaign_id": camp["campaign_id"],
        "campaign_name": camp["campaign_name"],
        "date": day.isoformat(),
        "impressions": impressions,
        "clicks": clicks,
        "spend": spend,
        "conversions": conversions,
        "revenue": revenue,
        "reach": reach,
        "ctr": round(safe_divide(clicks, impressions) * 100, 4),
        "cpc": round(safe_divide(spend, clicks), 4),
        "cpm": round(safe_divide(spend, impressions) * 1000, 4),
        "roas": round(safe_divide(revenue, spend), 4),
    }


def main():
    rows = [gen_row(camp, day) for camp in CAMPAIGNS for day in daterange(DATE_FROM, DATE_TO)]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"Generadas {len(rows)} filas ({len(CAMPAIGNS)} campañas x {(DATE_TO - DATE_FROM).days + 1} días)")
    print(f"Guardado en {OUT_PATH}")


if __name__ == "__main__":
    main()
