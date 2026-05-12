from pydantic import BaseModel
from datetime import date
from typing import Optional, List
from app.models.platform_connection import Platform


class MetricsSyncRequest(BaseModel):
    platform: Platform
    date_from: date
    date_to: date
    account_id: str


class CampaignMetricOut(BaseModel):
    id: int
    platform: Platform
    campaign_id: str
    campaign_name: str
    date: date
    impressions: int
    clicks: int
    spend: float
    conversions: int
    revenue: float
    reach: int
    ctr: float
    cpc: float
    cpm: float
    roas: float

    class Config:
        from_attributes = True


class CrossPlatformSummary(BaseModel):
    platform: Platform
    total_impressions: int
    total_clicks: int
    total_spend: float
    total_conversions: int
    total_revenue: float
    avg_ctr: float
    avg_roas: float


class AnalysisRequest(BaseModel):
    platforms: List[Platform]
    date_from: date
    date_to: date
    analysis_type: str = "full_report"


class AnalysisResponse(BaseModel):
    id: int
    analysis_type: str
    platforms: List[str]
    date_from: date
    date_to: date
    result: str
    input_tokens: int
    output_tokens: int

    class Config:
        from_attributes = True
