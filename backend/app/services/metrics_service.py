from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from typing import List, Dict
from app.models.campaign_metric import CampaignMetric
from app.models.platform_connection import PlatformConnection, Platform
from app.core.security import decrypt_token
from app.core.config import settings
from app.connectors import (
    GoogleAdsConnector, TikTokAdsConnector,
    DV360Connector, SFMCConnector, GoogleAnalyticsConnector,
)
# MetaAdsConnector no se importa — ver nota de reactivación más abajo

# Meta no tiene PlatformConnection real (se borró al pausar la integración,
# ver sync_platform más abajo) pero sí tiene datos fixture en campaign_metrics
# — se habilita explícitamente para análisis aunque no tenga conexión activa.
# GA4 todavía no tiene una conexión OAuth real conectada, pero también tiene
# datos fixture (ver scripts/generate_ga4_fake_data.py) para poder cruzarla
# contra Meta en los informes mientras tanto.
FIXTURE_PLATFORMS: set[Platform] = {Platform.META, Platform.GOOGLE_ANALYTICS}


async def get_connections(db: AsyncSession, platform: Platform) -> list[PlatformConnection]:
    result = await db.execute(
        select(PlatformConnection).where(
            and_(
                PlatformConnection.platform == platform,
                PlatformConnection.is_active == True,
            )
        )
    )
    return result.scalars().all()


async def get_available_platforms(db: AsyncSession) -> set[Platform]:
    """Plataformas que hoy se pueden analizar: con conexión activa, o
    explícitamente habilitadas por fixture (Meta, mientras dure la pausa)."""
    result = await db.execute(
        select(PlatformConnection.platform).where(PlatformConnection.is_active == True).distinct()
    )
    connected = set(result.scalars().all())
    return connected | FIXTURE_PLATFORMS


async def sync_platform(db: AsyncSession, platform: Platform, date_from: date, date_to: date) -> int:
    connections = await get_connections(db, platform)
    if not connections:
        raise ValueError(f"No active connection for platform {platform}")

    # Fetch and normalize ALL data first — only delete existing rows once we
    # know the remote call succeeded. A failure here leaves the DB untouched.
    all_normalized: list[dict] = []
    for conn in connections:
        access_token = decrypt_token(conn.access_token_enc)
        account_id = conn.account_id

        # --- Meta Ads: sync real pausado (2026-07-06) --------------------------
        # Se eliminó la conexión real de Meta (platform_connections) y se reemplazó
        # la data de campaign_metrics por un fixture random (ver
        # app/data/meta_fake_campaigns.json y scripts/generate_meta_fake_data.py)
        # mientras dura la auditoría de la plataforma.
        #
        # Para reactivar la sincronización real de Meta:
        #   1. Descomentar `from app.connectors.meta import MetaAdsConnector` y el
        #      export en app/connectors/__init__.py
        #   2. Descomentar el import de MetaAdsConnector arriba en este archivo
        #   3. Descomentar la rama `if platform == Platform.META` de abajo
        #   4. Volver a crear la conexión real en Settings (o restaurar el backup
        #      de platform_connections/campaign_metrics tomado antes de borrarla)
        # if platform == Platform.META:
        #     connector = MetaAdsConnector(access_token, account_id)
        if platform == Platform.GOOGLE_ADS:
            connector = GoogleAdsConnector(
                access_token, account_id, settings.GOOGLE_DEVELOPER_TOKEN,
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )
        elif platform == Platform.TIKTOK:
            connector = TikTokAdsConnector(access_token, account_id)
        elif platform == Platform.DV360:
            connector = DV360Connector(access_token, account_id)
        elif platform == Platform.GOOGLE_ANALYTICS:
            connector = GoogleAnalyticsConnector(access_token, account_id)
        else:
            raise ValueError(f"Unsupported platform for sync: {platform}")

        raw = await connector.fetch_campaigns(date_from, date_to)
        all_normalized.extend(connector.normalize(raw, date_from, date_to))

    # Safe to replace now that we have fresh data in memory
    await db.execute(
        delete(CampaignMetric).where(
            and_(
                CampaignMetric.platform == platform,
                CampaignMetric.date >= date_from,
                CampaignMetric.date <= date_to,
            )
        )
    )

    for row in all_normalized:
        db.add(CampaignMetric(
            platform=platform,
            account_id=row["account_id"],
            campaign_id=row["campaign_id"],
            campaign_name=row["campaign_name"],
            date=date.fromisoformat(row["date"]) if isinstance(row["date"], str) else row["date"],
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
            raw_data=row["raw_data"],
        ))

    await db.flush()
    return len(all_normalized)


async def get_metrics(
    db: AsyncSession,
    platforms: List[Platform],
    date_from: date,
    date_to: date,
) -> List[Dict]:
    filters = [
        CampaignMetric.date >= date_from,
        CampaignMetric.date <= date_to,
    ]
    if platforms:
        filters.append(CampaignMetric.platform.in_(platforms))

    result = await db.execute(select(CampaignMetric).where(and_(*filters)).order_by(CampaignMetric.date))
    rows = result.scalars().all()

    return [
        {
            "platform": r.platform.value,
            "campaign_id": r.campaign_id,
            "campaign_name": r.campaign_name,
            "date": str(r.date),
            "impressions": r.impressions,
            "clicks": r.clicks,
            "spend": r.spend,
            "conversions": r.conversions,
            "revenue": r.revenue,
            "reach": r.reach,
            "ctr": r.ctr,
            "cpc": r.cpc,
            "cpm": r.cpm,
            "roas": r.roas,
        }
        for r in rows
    ]
