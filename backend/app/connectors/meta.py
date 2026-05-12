import httpx
from datetime import date
from typing import List
from app.connectors.base import BaseConnector


class MetaAdsConnector(BaseConnector):
    BASE_URL = "https://graph.facebook.com/v20.0"

    async def fetch_campaigns(self, date_from: date, date_to: date) -> List[dict]:
        fields = "campaign_id,campaign_name,impressions,clicks,spend,reach,actions,action_values"
        params = {
            "fields": fields,
            "time_range": f'{{"since":"{date_from}","until":"{date_to}"}}',
            "level": "campaign",
            "access_token": self.access_token,
            "limit": 500,
        }
        results = []
        url = f"{self.BASE_URL}/act_{self.account_id}/insights"

        async with httpx.AsyncClient(timeout=30) as client:
            while url:
                resp = client.get(url, params=params)
                resp = await resp if hasattr(resp, "__await__") else resp
                resp.raise_for_status()
                data = resp.json()
                results.extend(data.get("data", []))
                url = data.get("paging", {}).get("next")
                params = {}  # next URL already has all params embedded

        return results

    def normalize(self, raw: List[dict], date_from: date, date_to: date) -> List[dict]:
        normalized = []
        for row in raw:
            spend = float(row.get("spend", 0))
            impressions = int(row.get("impressions", 0))
            clicks = int(row.get("clicks", 0))
            reach = int(row.get("reach", 0))

            # Extract conversions and revenue from actions
            actions = {a["action_type"]: float(a["value"]) for a in row.get("actions", [])}
            action_values = {a["action_type"]: float(a["value"]) for a in row.get("action_values", [])}
            conversions = int(actions.get("purchase", actions.get("offsite_conversion.fb_pixel_purchase", 0)))
            revenue = action_values.get("purchase", action_values.get("offsite_conversion.fb_pixel_purchase", 0.0))

            normalized.append({
                "platform": "meta",
                "account_id": self.account_id,
                "campaign_id": row["campaign_id"],
                "campaign_name": row.get("campaign_name", ""),
                "date": str(date_from),
                "impressions": impressions,
                "clicks": clicks,
                "spend": spend,
                "conversions": conversions,
                "revenue": revenue,
                "reach": reach,
                "ctr": self.safe_divide(clicks, impressions) * 100,
                "cpc": self.safe_divide(spend, clicks),
                "cpm": self.safe_divide(spend, impressions) * 1000,
                "roas": self.safe_divide(revenue, spend),
                "raw_data": row,
            })
        return normalized
