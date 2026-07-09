"""
Genera backend/app/data/ga4_fake_campaigns.json — data ficticia de Google
Analytics 4 con el mismo esquema que usa meta_fake_campaigns.json (ver
generate_meta_fake_data.py), para poder cruzar performance de campañas
(Meta) contra comportamiento real del sitio (GA4) en los informes.

A diferencia de Meta (campañas pagas), GA4 se organiza por canal de
adquisición — Direct, Organic Search, Paid Search, Paid Social, Email,
Referral — que es lo que la API real devuelve como "sessionCampaignName"
o "sessionDefaultChannelGroup" (ver app/connectors/google_analytics.py).

Cada fila incluye el embudo ecommerce completo típico de un retailer
(sessions → view_item → add_to_cart → begin_checkout → purchase) en
raw_data, además de los campos universales del esquema (impressions,
clicks, conversions, revenue, reach) mapeados igual que el conector real:
  sessions        → clicks
  page_views      → impressions
  purchase        → conversions
  purchase_revenue → revenue
  users           → reach
  spend/cpc/cpm   → 0 (GA4 no tiene datos de costo propios)

Uso: python scripts/generate_ga4_fake_data.py
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(7)

OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "ga4_fake_campaigns.json"

# Mismo período que meta_fake_campaigns.json — necesario para poder cruzar
# ambas plataformas en el mismo rango de fechas en los informes.
DATE_TO = date(2026, 7, 6)
DATE_FROM = DATE_TO - timedelta(days=89)  # 90 días ~ 3 meses

PROPERTY_ID = "398654127"

# Rangos de sesiones diarias y AOV por canal — Organic Search y Direct son
# históricamente los canales de mayor volumen para un retailer, Email y
# Referral los de menor volumen pero AOV más alto (tráfico más calificado).
CHANNELS = [
    {"campaign_name": "Organic Search", "sessions_range": (1400, 3800), "aov_range": (30, 70)},
    {"campaign_name": "Direct",         "sessions_range": (700, 2200),  "aov_range": (28, 65)},
    {"campaign_name": "Paid Social",    "sessions_range": (550, 1700),  "aov_range": (32, 75)},
    {"campaign_name": "Paid Search",    "sessions_range": (350, 1100),  "aov_range": (35, 80)},
    {"campaign_name": "Email",          "sessions_range": (150, 650),   "aov_range": (40, 95)},
    {"campaign_name": "Referral",       "sessions_range": (120, 480),   "aov_range": (30, 70)},
]

# Benchmarks típicos de ecommerce retail (no de un solo vertical específico,
# sino rangos razonables para no generar un embudo irreal).
PAGEVIEWS_POR_SESSION   = (3.0, 6.0)
VIEW_ITEM_RATE          = (0.55, 1.30)   # puede superar 1: varios productos vistos por sesión
ADD_TO_CART_RATE        = (0.06, 0.14)   # % de sesiones que agregan algo al carrito
CHECKOUT_RATE_DEL_CART  = (0.45, 0.65)   # % de esos carritos que llegan a checkout
PURCHASE_RATE_DEL_CHECKOUT = (0.55, 0.75)  # % de checkouts que se completan
USERS_RATE_DE_SESSIONS  = (0.75, 0.95)   # usuarios únicos vs. sesiones totales
ENGAGEMENT_RATE         = (0.45, 0.72)
AVG_SESSION_DURATION    = (60, 240)      # segundos


def daterange(d_from: date, d_to: date):
    days = (d_to - d_from).days
    for i in range(days + 1):
        yield d_from + timedelta(days=i)


def gen_row(channel: dict, day: date) -> dict:
    sessions = random.randint(*channel["sessions_range"])
    users = round(sessions * random.uniform(*USERS_RATE_DE_SESSIONS))
    page_views = round(sessions * random.uniform(*PAGEVIEWS_POR_SESSION))
    view_item = round(sessions * random.uniform(*VIEW_ITEM_RATE))
    add_to_cart = round(sessions * random.uniform(*ADD_TO_CART_RATE))
    begin_checkout = round(add_to_cart * random.uniform(*CHECKOUT_RATE_DEL_CART))
    purchase = round(begin_checkout * random.uniform(*PURCHASE_RATE_DEL_CHECKOUT))
    aov = random.uniform(*channel["aov_range"])
    revenue = round(purchase * aov, 2)

    return {
        "platform": "google_analytics",
        "account_id": PROPERTY_ID,
        "campaign_id": f"{channel['campaign_name']}_{day.isoformat()}",
        "campaign_name": channel["campaign_name"],
        "date": day.isoformat(),
        "impressions": page_views,
        "clicks": sessions,
        "spend": 0.0,
        "conversions": purchase,
        "revenue": revenue,
        "reach": users,
        "ctr": 0.0,
        "cpc": 0.0,
        "cpm": 0.0,
        "roas": round(revenue, 4) if revenue else 0.0,
        "raw_data": {
            "channel": channel["campaign_name"],
            "sessions": sessions,
            "users": users,
            "page_views": page_views,
            "view_item": view_item,
            "add_to_cart": add_to_cart,
            "begin_checkout": begin_checkout,
            "purchase": purchase,
            "engagement_rate": round(random.uniform(*ENGAGEMENT_RATE), 4),
            "avg_session_duration_sec": round(random.uniform(*AVG_SESSION_DURATION), 1),
            "aov": round(aov, 2),
        },
    }


def main():
    rows = [gen_row(ch, day) for ch in CHANNELS for day in daterange(DATE_FROM, DATE_TO)]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"Generadas {len(rows)} filas ({len(CHANNELS)} canales x {(DATE_TO - DATE_FROM).days + 1} días)")
    print(f"Guardado en {OUT_PATH}")


if __name__ == "__main__":
    main()
