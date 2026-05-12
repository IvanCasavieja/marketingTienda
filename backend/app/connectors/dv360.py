import httpx
from datetime import date
from typing import List
from app.connectors.base import BaseConnector


class DV360Connector(BaseConnector):
    """Display & Video 360 connector via Reporting API v2."""
    BASE_URL = "https://doubleclickbidmanager.googleapis.com/v2"

    async def _create_query(self, client: httpx.AsyncClient, date_from: date, date_to: date) -> str:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        payload = {
            "metadata": {"title": "MKTG Platform Sync", "dataRange": {"customStartDate": {"year": date_from.year, "month": date_from.month, "day": date_from.day}, "customEndDate": {"year": date_to.year, "month": date_to.month, "day": date_to.day}}, "format": "CSV"},
            "params": {
                "type": "TYPE_GENERAL",
                "groupBys": ["FILTER_ADVERTISER_CURRENCY", "FILTER_CAMPAIGN_DAILY_FREQUENCY", "FILTER_DATE", "FILTER_INSERTION_ORDER"],
                "metrics": ["METRIC_IMPRESSIONS", "METRIC_CLICKS", "METRIC_REVENUE_ADVERTISER", "METRIC_TOTAL_CONVERSIONS", "METRIC_REACH_TOTAL"],
                "filters": [{"type": "FILTER_PARTNER", "value": self.account_id}],
            },
        }
        resp = await client.post(f"{self.BASE_URL}/queries", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["queryId"]

    async def fetch_campaigns(self, date_from: date, date_to: date) -> List[dict]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=120) as client:
            query_id = await self._create_query(client, date_from, date_to)
            resp = await client.post(f"{self.BASE_URL}/queries/{query_id}:run", headers=headers)
            resp.raise_for_status()
            report_id = resp.json().get("key", {}).get("reportId")

            # Poll until report is done
            import asyncio
            for _ in range(20):
                r = await client.get(f"{self.BASE_URL}/queries/{query_id}/reports/{report_id}", headers=headers)
                r.raise_for_status()
                status = r.json().get("metadata", {}).get("status", {}).get("state")
                if status == "DONE":
                    download_url = r.json()["metadata"]["googleCloudStoragePath"]
                    csv_resp = await client.get(download_url)
                    return self._parse_csv(csv_resp.text)
                if status == "FAILED":
                    raise ValueError("DV360 report generation failed")
                await asyncio.sleep(5)

        return []

    def _parse_csv(self, csv_text: str) -> List[dict]:
        import csv, io
        reader = csv.DictReader(io.StringIO(csv_text))
        return list(reader)

    def normalize(self, raw: List[dict], date_from: date, date_to: date) -> List[dict]:
        normalized = []
        for row in raw:
            spend = float(row.get("Revenue (Adv Currency)", 0) or 0)
            impressions = int(row.get("Impressions", 0) or 0)
            clicks = int(row.get("Clicks", 0) or 0)
            conversions = int(float(row.get("Total Conversions", 0) or 0))
            reach = int(float(row.get("Reach", 0) or 0))

            normalized.append({
                "platform": "dv360",
                "account_id": self.account_id,
                "campaign_id": row.get("Insertion Order ID", ""),
                "campaign_name": row.get("Insertion Order", ""),
                "date": row.get("Date", str(date_from)),
                "impressions": impressions,
                "clicks": clicks,
                "spend": spend,
                "conversions": conversions,
                "revenue": 0.0,
                "reach": reach,
                "ctr": self.safe_divide(clicks, impressions) * 100,
                "cpc": self.safe_divide(spend, clicks),
                "cpm": self.safe_divide(spend, impressions) * 1000,
                "roas": 0.0,
                "raw_data": row,
            })
        return normalized
