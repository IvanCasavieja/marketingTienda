import httpx
from datetime import date
from typing import List, Dict
from app.connectors.base import BaseConnector


class SFMCConnector:
    """Salesforce Marketing Cloud connector (Email + WhatsApp/MobileConnect)."""

    AUTH_URL = "https://{subdomain}.auth.marketingcloudapis.com/v2/token"
    REST_URL = "https://{subdomain}.rest.marketingcloudapis.com"

    def __init__(self, client_id: str, client_secret: str, subdomain: str, account_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.subdomain = subdomain
        self.account_id = account_id
        self._access_token: str | None = None

    async def _authenticate(self) -> str:
        url = self.AUTH_URL.format(subdomain=self.subdomain)
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "account_id": self.account_id,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
        return self._access_token

    async def _get_headers(self) -> dict:
        if not self._access_token:
            await self._authenticate()
        return {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

    async def fetch_email_performance(self, date_from: date, date_to: date) -> List[Dict]:
        base = self.REST_URL.format(subdomain=self.subdomain)
        headers = await self._get_headers()
        params = {
            "$filter": f"SendDate gte {date_from} and SendDate lte {date_to}",
            "$fields": "SendID,EmailName,SendDate,NumberSent,NumberDelivered,NumberOpened,NumberClicked,NumberBounced,NumberUnsubscribed,NumberDeliveredRecipients",
            "$pagesize": 500,
        }
        results = []
        page = 1

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params["$page"] = page
                resp = await client.get(f"{base}/data/v1/analytics/tracking/sends", headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                results.extend(items)
                if len(items) < 500:
                    break
                page += 1

        return results

    async def fetch_whatsapp_performance(self, date_from: date, date_to: date) -> List[Dict]:
        """Fetch WhatsApp/MobileConnect message performance."""
        base = self.REST_URL.format(subdomain=self.subdomain)
        headers = await self._get_headers()
        params = {
            "$filter": f"CreatedDate gte {date_from} and CreatedDate lte {date_to}",
            "$fields": "messageKey,name,status,sent,delivered,read,failed,createdDate",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{base}/messaging/v1/whatsapp/definitions", headers=headers, params=params)
            if resp.status_code == 200:
                return resp.json().get("items", [])
        return []

    def normalize_email(self, raw: List[Dict]) -> List[Dict]:
        normalized = []
        for row in raw:
            sent = int(row.get("NumberSent", 0))
            delivered = int(row.get("NumberDelivered", 0))
            opened = int(row.get("NumberOpened", 0))
            clicked = int(row.get("NumberClicked", 0))
            bounced = int(row.get("NumberBounced", 0))
            unsubs = int(row.get("NumberUnsubscribed", 0))

            normalized.append({
                "channel": "email",
                "send_id": row.get("SendID", ""),
                "name": row.get("EmailName", ""),
                "date": row.get("SendDate", ""),
                "sent": sent,
                "delivered": delivered,
                "opened": opened,
                "clicked": clicked,
                "bounced": bounced,
                "unsubscribed": unsubs,
                "open_rate": round(opened / delivered * 100, 2) if delivered else 0,
                "click_rate": round(clicked / delivered * 100, 2) if delivered else 0,
                "bounce_rate": round(bounced / sent * 100, 2) if sent else 0,
                "raw_data": row,
            })
        return normalized

    def normalize_whatsapp(self, raw: List[Dict]) -> List[Dict]:
        normalized = []
        for row in raw:
            sent = int(row.get("sent", 0))
            delivered = int(row.get("delivered", 0))
            read = int(row.get("read", 0))
            failed = int(row.get("failed", 0))

            normalized.append({
                "channel": "whatsapp",
                "message_key": row.get("messageKey", ""),
                "name": row.get("name", ""),
                "date": row.get("createdDate", ""),
                "sent": sent,
                "delivered": delivered,
                "read": read,
                "failed": failed,
                "delivery_rate": round(delivered / sent * 100, 2) if sent else 0,
                "read_rate": round(read / delivered * 100, 2) if delivered else 0,
                "raw_data": row,
            })
        return normalized
