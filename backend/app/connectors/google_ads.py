import httpx
from datetime import date
from typing import List
from app.connectors.base import BaseConnector


class GoogleAdsConnector(BaseConnector):
    BASE_URL = "https://googleads.googleapis.com/v17"

    def __init__(self, access_token: str, account_id: str, developer_token: str):
        super().__init__(access_token, account_id)
        self.developer_token = developer_token

    async def fetch_campaigns(self, date_from: date, date_to: date) -> List[dict]:
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.view_through_conversions
            FROM campaign
            WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
              AND campaign.status != 'REMOVED'
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "developer-token": self.developer_token,
            "login-customer-id": self.account_id,
        }
        payload = {"query": query}
        url = f"{self.BASE_URL}/customers/{self.account_id}/googleAds:searchStream"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def normalize(self, raw: List[dict], date_from: date, date_to: date) -> List[dict]:
        normalized = []
        for batch in raw:
            for result in batch.get("results", []):
                campaign = result.get("campaign", {})
                metrics = result.get("metrics", {})
                spend = int(metrics.get("costMicros", 0)) / 1_000_000
                impressions = int(metrics.get("impressions", 0))
                clicks = int(metrics.get("clicks", 0))
                conversions = int(metrics.get("conversions", 0))
                revenue = float(metrics.get("conversionsValue", 0))

                normalized.append({
                    "platform": "google_ads",
                    "account_id": self.account_id,
                    "campaign_id": campaign.get("id", ""),
                    "campaign_name": campaign.get("name", ""),
                    "date": str(date_from),
                    "impressions": impressions,
                    "clicks": clicks,
                    "spend": spend,
                    "conversions": conversions,
                    "revenue": revenue,
                    "reach": 0,
                    "ctr": self.safe_divide(clicks, impressions) * 100,
                    "cpc": self.safe_divide(spend, clicks),
                    "cpm": self.safe_divide(spend, impressions) * 1000,
                    "roas": self.safe_divide(revenue, spend),
                    "raw_data": result,
                })
        return normalized
