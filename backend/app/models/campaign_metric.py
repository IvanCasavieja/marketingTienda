from sqlalchemy import String, Integer, Float, Date, DateTime, Enum, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from app.core.database import Base
from app.models.platform_connection import Platform


class CampaignMetric(Base):
    __tablename__ = "campaign_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_name: Mapped[str] = mapped_column(String(500), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    spend: Mapped[float] = mapped_column(Float, default=0.0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    reach: Mapped[int] = mapped_column(Integer, default=0)

    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    cpc: Mapped[float] = mapped_column(Float, default=0.0)
    cpm: Mapped[float] = mapped_column(Float, default=0.0)
    roas: Mapped[float] = mapped_column(Float, default=0.0)

    raw_data: Mapped[dict] = mapped_column(JSON, nullable=True)

    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
