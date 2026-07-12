"""
Exporta campaign_metrics agregado a semanal, en formato wide, para alimentar
el pipeline de Marketing Mix Modeling con Google Meridian (ver meridian_mmm/).

No importa si las filas de campaign_metrics son fixture o datos reales
sincronizados — el query es el mismo en los dos casos, así que este script
no necesita cambios cuando las conexiones reales reemplacen a los fixtures.

KPI: revenue semanal de Google Analytics (el funnel de ecommerce real del
negocio), no la revenue auto-reportada por cada plataforma de ads — así se
mide impacto incremental real en vez de la atribución que cada plataforma
ya se adjudica.

Canales de media: cualquier plataforma (excepto Google Analytics, que es
medición, no canal pago) con spend > 0 en algún momento del rango.

Uso:
  python scripts/export_metrics_for_meridian.py

Requiere DATABASE_URL apuntando a la base real (mismo .env que usa la app).
"""
import asyncio
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
import app.models  # noqa: E402,F401
from app.models.role import Role  # noqa: E402,F401
from app.models.campaign_metric import CampaignMetric  # noqa: E402
from app.models.platform_connection import Platform  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "meridian_mmm" / "data" / "weekly_metrics.csv"


async def fetch_rows() -> pd.DataFrame:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                CampaignMetric.date,
                CampaignMetric.platform,
                CampaignMetric.spend,
                CampaignMetric.impressions,
                CampaignMetric.revenue,
            )
        )
        rows = result.all()
    return pd.DataFrame(rows, columns=["date", "platform", "spend", "impressions", "revenue"])


def to_weekly_wide(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["platform"] = df["platform"].map(lambda p: p.value if isinstance(p, Platform) else p)
    df["date"] = pd.to_datetime(df["date"])
    # Semana ISO, lunes como fecha representativa
    df["time"] = (df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")).dt.date

    ga4 = df[df["platform"] == Platform.GOOGLE_ANALYTICS.value]
    kpi = ga4.groupby("time")["revenue"].sum().rename("kpi")

    media = df[df["platform"] != Platform.GOOGLE_ANALYTICS.value]
    spend_by_platform = media.groupby("platform")["spend"].sum()
    channels = sorted(spend_by_platform[spend_by_platform > 0].index.tolist())
    if not channels:
        raise ValueError(
            "Ninguna plataforma tiene spend > 0 en campaign_metrics — no hay "
            "nada que modelar. ¿Corriste load_fake_campaign_data.py o "
            "sincronizaste alguna conexión real?"
        )

    media = media[media["platform"].isin(channels)]
    weekly = media.groupby(["time", "platform"])[["spend", "impressions"]].sum()
    wide = weekly.unstack("platform")
    wide.columns = [f"{platform}_{metric}" for metric, platform in wide.columns]
    wide = wide.reindex(sorted(set(wide.index) | set(kpi.index))).fillna(0.0)

    out = wide.join(kpi, how="left").fillna({"kpi": 0.0})
    out.index.name = "time"
    return out.reset_index(), channels


async def main() -> None:
    df = await fetch_rows()
    if df.empty:
        raise SystemExit("campaign_metrics está vacía — no hay nada que exportar.")

    weekly, channels = to_weekly_wide(df)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(OUT_PATH, index=False)

    print(f"{len(weekly)} semanas exportadas -> {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"Canales de media: {', '.join(channels)}")
    print(f"Rango: {weekly['time'].min()} a {weekly['time'].max()}")
    print(f"KPI total (revenue GA4) en el rango: {weekly['kpi'].sum():,.2f}")


if __name__ == "__main__":
    asyncio.run(main())
