"""
Carga los fixtures de datos falsos (meta_fake_campaigns.json,
ga4_fake_campaigns.json) directo en la tabla campaign_metrics.

No pasa por sync_platform(): esas plataformas no tienen una conexión real
activa (Meta se dio de baja, GA4 todavía no está conectada), así que el
sync normal fallaría con "No active connection". Este loader es la manera
de poblar la tabla con data ficticia para poder analizar/cruzar plataformas
en los informes mientras tanto.

Idempotente — antes de insertar borra las filas existentes de esa plataforma
en el rango de fechas del fixture, así se puede correr de nuevo (por ejemplo
después de regenerar el fixture) sin duplicar filas.

Uso:
  python scripts/load_fake_campaign_data.py           # carga todos los fixtures
  python scripts/load_fake_campaign_data.py meta       # solo Meta
  python scripts/load_fake_campaign_data.py ga4        # solo GA4

Requiere DATABASE_URL apuntando a la base real (mismo .env que usa la app).
"""
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.campaign_metric import CampaignMetric  # noqa: E402
from app.models.platform_connection import Platform  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"

FIXTURES: dict[str, tuple[str, Platform]] = {
    "meta": ("meta_fake_campaigns.json", Platform.META),
    "ga4":  ("ga4_fake_campaigns.json", Platform.GOOGLE_ANALYTICS),
}


async def load_fixture(filename: str, platform: Platform) -> int:
    path = DATA_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    if not rows:
        return 0

    dates = [date.fromisoformat(r["date"]) for r in rows]
    date_from, date_to = min(dates), max(dates)

    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(CampaignMetric).where(
                CampaignMetric.platform == platform,
                CampaignMetric.date >= date_from,
                CampaignMetric.date <= date_to,
            )
        )
        for row in rows:
            db.add(CampaignMetric(
                platform=platform,
                account_id=row["account_id"],
                campaign_id=row["campaign_id"],
                campaign_name=row["campaign_name"],
                date=date.fromisoformat(row["date"]),
                impressions=row["impressions"],
                clicks=row["clicks"],
                spend=row["spend"],
                conversions=row["conversions"],
                revenue=row["revenue"],
                reach=row["reach"],
                ctr=row["ctr"],
                cpc=row["cpc"],
                cpm=row["cpm"],
                roas=row["roas"],
                raw_data=row.get("raw_data"),
            ))
        await db.commit()

    return len(rows)


async def main(which: str) -> None:
    targets = FIXTURES.items() if which == "all" else [(which, FIXTURES[which])]
    for key, (filename, platform) in targets:
        n = await load_fixture(filename, platform)
        print(f"{key}: {n} filas cargadas desde {filename}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which not in ("all", *FIXTURES.keys()):
        print(f"Uso: python {Path(__file__).name} [{'|'.join(FIXTURES.keys())}|all]")
        sys.exit(1)
    asyncio.run(main(which))
