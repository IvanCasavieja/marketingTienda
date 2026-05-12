from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Dict
from app.models.campaign_metric import CampaignMetric
from app.models.platform_connection import PlatformConnection, Platform
from app.core.security import decrypt_token
from app.core.config import settings
from app.connectors import (
    MetaAdsConnector, GoogleAdsConnector, TikTokAdsConnector, DV360Connector, SFMCConnector
)


async def get_connections(db: AsyncSession, user_id: int, platform: Platform) -> list[PlatformConnection]:
    result = await db.execute(
        select(PlatformConnection).where(
            and_(
                PlatformConnection.user_id == user_id,
                PlatformConnection.platform == platform,
                PlatformConnection.is_active == True,
            )
        )
    )
    return result.scalars().all()


async def sync_platform(db: AsyncSession, user_id: int, platform: Platform, date_from: date, date_to: date) -> int:
    connections = await get_connections(db, user_id, platform)
    if not connections:
        raise ValueError(f"No active connection for platform {platform}")

    saved = 0
    for conn in connections:
        access_token = decrypt_token(conn.access_token_enc)
        account_id = conn.account_id

        if platform == Platform.META:
            connector = MetaAdsConnector(access_token, account_id)
        elif platform == Platform.GOOGLE_ADS:
            connector = GoogleAdsConnector(access_token, account_id, settings.GOOGLE_DEVELOPER_TOKEN)
        elif platform == Platform.TIKTOK:
            connector = TikTokAdsConnector(access_token, account_id)
        elif platform == Platform.DV360:
            connector = DV360Connector(access_token, account_id)
        else:
            raise ValueError(f"Unsupported platform for sync: {platform}")

        raw = await connector.fetch_campaigns(date_from, date_to)
        normalized = connector.normalize(raw, date_from, date_to)

        for row in normalized:
            metric = CampaignMetric(
                user_id=user_id,
                platform=platform,
                account_id=row["account_id"],
                campaign_id=row["campaign_id"],
                campaign_name=row["campaign_name"],
                date=row["date"],
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
            )
            db.add(metric)
            saved += 1

    await db.flush()
    return saved


async def get_metrics(db: AsyncSession, user_id: int, platforms: List[Platform], date_from: date, date_to: date) -> List[Dict]:
    filters = [
        CampaignMetric.user_id == user_id,
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
