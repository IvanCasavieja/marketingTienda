import httpx
from datetime import date
from typing import List
from app.connectors.base import BaseConnector


class TikTokAdsConnector(BaseConnector):
    BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"

    async def fetch_campaigns(self, date_from: date, date_to: date) -> List[dict]:
        headers = {
            "Access-Token": self.access_token,
            "Content-Type": "application/json",
        }
        params = {
            "advertiser_id": self.account_id,
            "report_type": "BASIC",
            "data_level": "AUCTION_CAMPAIGN",
            "dimensions": '["campaign_id","stat_time_day"]',
            "metrics": '["campaign_name","impressions","clicks","spend","reach","conversion","total_purchase_value"]',
            "start_date": str(date_from),
            "end_date": str(date_to),
            "page_size": 100,
        }
        results = []
        page = 1

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params["page"] = page
                resp = await client.get(f"{self.BASE_URL}/report/integrated/get/", headers=headers, params=params)
                resp.raise_for_status()
                body = resp.json()

                if body.get("code") != 0:
                    raise ValueError(f"TikTok API error: {body.get('message')}")

                data = body.get("data", {})
                results.extend(data.get("list", []))

                page_info = data.get("page_info", {})
                if page >= page_info.get("total_page", 1):
                    break
                page += 1

        return results

    def normalize(self, raw: List[dict], date_from: date, date_to: date) -> List[dict]:
        normalized = []
        for row in raw:
            dims = row.get("dimensions", {})
            metrics = row.get("metrics", {})
            spend = float(metrics.get("spend", 0))
            impressions = int(metrics.get("impressions", 0))
            clicks = int(metrics.get("clicks", 0))
            conversions = int(metrics.get("conversion", 0))
            revenue = float(metrics.get("total_purchase_value", 0))
            reach = int(metrics.get("reach", 0))

            normalized.append({
                "platform": "tiktok",
                "account_id": self.account_id,
                "campaign_id": dims.get("campaign_id", ""),
                "campaign_name": metrics.get("campaign_name", ""),
                "date": dims.get("stat_time_day", str(date_from)),
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
