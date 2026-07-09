"""
Genera backend/app/data/tiktok_fake_campaigns.json — data ficticia de 5 campañas
de TikTok Ads con 3 meses de métricas diarias, con el mismo esquema que usa
la tabla campaign_metrics.

TikTok todavía no tiene una conexión OAuth real conectada (ver TIKTOK_APP_ID/
TIKTOK_APP_SECRET vacíos en .env.example), así que este fixture permite
analizarla y cruzarla contra Meta/GA4 en los informes mientras tanto — mismo
patrón que generate_meta_fake_data.py y generate_ga4_fake_data.py.

Uso: python scripts/generate_tiktok_fake_data.py
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(99)

OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "tiktok_fake_campaigns.json"

DATE_TO = date(2026, 7, 6)
DATE_FROM = DATE_TO - timedelta(days=89)  # 90 días ~ 3 meses, mismo rango que Meta/GA4

ACCOUNTS = [
    "7012345678901234567",
    "7098765432109876543",
]

# TikTok: volúmenes de impresiones mucho más altos y CPMs más bajos que Meta
# (alcance masivo, formato video), CTR con más varianza (contenido nativo vs. ads).
#
# objective: "branding" | "traffic" | "conversion" — clasificación manual del objetivo
# de campaña, guardada en raw_data (ver gen_row). No viene de una conexión real (no hay
# ninguna hoy, ver FIXTURE_PLATFORMS en metrics_service.py) — el día que haya una conexión
# real, el conector debería mapear el objective nativo de la plataforma acá en vez de esto.
# TopView es el formato premium de pantalla completa de TikTok — se vende y se usa
# exclusivamente para objetivos de reach/awareness, aunque el nombre de la campaña
# incluya "Promo" (la mecánica comercial no cambia el objetivo del formato).
CAMPAIGNS = [
    {"campaign_id": "1789000000010001", "campaign_name": "TikTok | Spark Ads Marca",              "account_id": ACCOUNTS[0], "objective": "branding",   "impr_range": (150000, 420000), "ctr_range": (0.6, 1.6), "cpm_range": (8, 20),  "cvr_range": (0.4, 1.2), "aov_range": (28, 65)},
    {"campaign_id": "1789000000010002", "campaign_name": "TikTok | In-Feed Remarketing",           "account_id": ACCOUNTS[0], "objective": "conversion", "impr_range": (30000, 90000),   "ctr_range": (1.8, 3.6), "cpm_range": (6, 16),  "cvr_range": (2.5, 6.0), "aov_range": (35, 80)},
    {"campaign_id": "1789000000010003", "campaign_name": "TikTok | Lanzamiento Categoria Hogar",   "account_id": ACCOUNTS[0], "objective": "traffic",    "impr_range": (60000, 160000),  "ctr_range": (1.0, 2.2), "cpm_range": (7, 18),  "cvr_range": (1.2, 3.0), "aov_range": (32, 70)},
    {"campaign_id": "1789000000010004", "campaign_name": "TikTok | TopView Promo Fin de Semana",   "account_id": ACCOUNTS[1], "objective": "branding",   "impr_range": (90000, 250000),  "ctr_range": (1.3, 2.8), "cpm_range": (10, 24), "cvr_range": (1.8, 4.2), "aov_range": (25, 55)},
    {"campaign_id": "1789000000010005", "campaign_name": "TikTok | Video Shopping Ecommerce",      "account_id": ACCOUNTS[1], "objective": "conversion", "impr_range": (100000, 280000), "ctr_range": (1.5, 3.0), "cpm_range": (9, 22),  "cvr_range": (2.0, 5.0), "aov_range": (30, 68)},
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
    reach = round(impressions * random.uniform(0.7, 0.92))  # TikTok: alcance/impresion mas alto (feed algoritmico)

    return {
        "platform": "tiktok",
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
        "raw_data": {"objective": camp["objective"]},
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
