import httpx
from datetime import date
from typing import List
from app.connectors.base import BaseConnector


class GoogleAdsConnector(BaseConnector):
    BASE_URL = "https://googleads.googleapis.com/v17"

    def __init__(self, refresh_token: str, account_id: str, developer_token: str,
                 client_id: str = "", client_secret: str = ""):
        super().__init__(refresh_token, account_id)
        self.developer_token = developer_token
        self.client_id = client_id
        self.client_secret = client_secret

    async def _get_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.access_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def fetch_campaigns(self, date_from: date, date_to: date) -> List[dict]:
        access_token = await self._get_access_token()
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                segments.date,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
            FROM campaign
            WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
              AND campaign.status != 'REMOVED'
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.developer_token,
            "login-customer-id": self.account_id.replace("-", ""),
        }
        url = f"{self.BASE_URL}/customers/{self.account_id.replace('-', '')}/googleAds:searchStream"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json={"query": query}, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def normalize(self, raw: List[dict], date_from: date, date_to: date) -> List[dict]:
        normalized = []
        for batch in raw:
            for result in batch.get("results", []):
                campaign = result.get("campaign", {})
                metrics = result.get("metrics", {})
                segments = result.get("segments", {})
                spend = int(metrics.get("costMicros", 0)) / 1_000_000
                impressions = int(metrics.get("impressions", 0))
                clicks = int(metrics.get("clicks", 0))
                conversions = float(metrics.get("conversions", 0))
                revenue = float(metrics.get("conversionsValue", 0))
                row_date = segments.get("date", str(date_from))

                normalized.append({
                    "platform": "google_ads",
                    "account_id": self.account_id,
                    "campaign_id": str(campaign.get("id", "")),
                    "campaign_name": campaign.get("name", ""),
                    "date": row_date,
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
