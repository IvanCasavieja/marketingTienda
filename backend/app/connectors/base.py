from abc import ABC, abstractmethod
from datetime import date
from typing import List
from app.schemas.metrics import CampaignMetricOut


class BaseConnector(ABC):
    """Base class for all platform ad connectors."""

    def __init__(self, access_token: str, account_id: str):
        self.access_token = access_token
        self.account_id = account_id

    @abstractmethod
    async def fetch_campaigns(self, date_from: date, date_to: date) -> List[dict]:
        """Fetch raw campaign data from the platform."""
        ...

    @abstractmethod
    def normalize(self, raw: List[dict], date_from: date, date_to: date) -> List[dict]:
        """Normalize platform-specific data to the universal schema."""
        ...

    @staticmethod
    def safe_divide(numerator: float, denominator: float) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0
