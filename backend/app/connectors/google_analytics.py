"""
google_analytics.py — Conector Google Analytics 4 (GA4 Data API).

Usa OAuth 2.0 con refresh_token (mismo mecanismo que Google Ads).
El account_id corresponde al Property ID numérico de GA4 (ej: "123456789").

Mapeo de métricas GA4 → esquema universal:
  sessions          → clicks
  screenPageViews   → impressions
  conversions       → conversions
  purchaseRevenue   → revenue
  spend/cpc/cpm/roas → 0 (GA4 no tiene datos de costo propios)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List

import httpx

from app.connectors.base import BaseConnector
from app.core.config import settings
from app.core.http_retry import request_with_retry

log = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GA4_URL   = "https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"


class GoogleAnalyticsConnector(BaseConnector):

    def __init__(self, refresh_token: str, property_id: str):
        super().__init__(refresh_token, property_id)

    async def _get_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await request_with_retry(
                client, "POST",
                _TOKEN_URL,
                data={
                    "client_id":     settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": self.access_token,
                    "grant_type":    "refresh_token",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def fetch_campaigns(self, date_from: date, date_to: date) -> List[dict]:
        access_token = await self._get_access_token()
        url = _GA4_URL.format(property_id=self.account_id)
        headers = {"Authorization": f"Bearer {access_token}"}

        payload = {
            "dateRanges": [
                {"startDate": str(date_from), "endDate": str(date_to)}
            ],
            "dimensions": [
                {"name": "date"},
                {"name": "sessionCampaignName"},
                {"name": "sessionDefaultChannelGroup"},
            ],
            "metrics": [
                {"name": "sessions"},
                {"name": "screenPageViews"},
                {"name": "conversions"},
                {"name": "purchaseRevenue"},
                {"name": "totalUsers"},
            ],
            "limit": 10000,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await request_with_retry(client, "POST", url, json=payload, headers=headers)
            if not resp.is_success:
                detail = resp.text[:300]
                raise ValueError(f"GA4 API error {resp.status_code}: {detail}")
            return resp.json().get("rows", [])

    def normalize(self, raw: List[dict], date_from: date, date_to: date) -> List[dict]:
        normalized = []
        dim_headers = None  # GA4 devuelve rows con índices posicionales

        for row in raw:
            dims    = row.get("dimensionValues", [])
            metrics = row.get("metricValues", [])

            if len(dims) < 3 or len(metrics) < 5:
                continue

            row_date      = dims[0].get("value", str(date_from))
            campaign_name = dims[1].get("value", "(not set)")
            channel       = dims[2].get("value", "")

            sessions    = int(metrics[0].get("value", 0) or 0)
            pageviews   = int(metrics[1].get("value", 0) or 0)
            conversions = float(metrics[2].get("value", 0) or 0)
            revenue     = float(metrics[3].get("value", 0) or 0)
            users       = int(metrics[4].get("value", 0) or 0)

            # Normalizar nombre: si es "(not set)", usar canal como nombre
            if campaign_name in ("(not set)", "", "(none)"):
                campaign_name = channel or "Tráfico directo"

            # Formato de fecha GA4: "20260101" → "2026-01-01"
            if len(row_date) == 8 and row_date.isdigit():
                row_date = f"{row_date[:4]}-{row_date[4:6]}-{row_date[6:]}"

            normalized.append({
                "platform":      "google_analytics",
                "account_id":    self.account_id,
                "campaign_id":   f"{campaign_name}_{row_date}",
                "campaign_name": campaign_name,
                "date":          row_date,
                "impressions":   pageviews,
                "clicks":        sessions,
                "spend":         0.0,
                "conversions":   int(conversions),
                "revenue":       revenue,
                "reach":         users,
                "ctr":           0.0,
                "cpc":           0.0,
                "cpm":           0.0,
                "roas":          self.safe_divide(revenue, 1) if revenue else 0.0,
                "raw_data":      row,
            })

        return normalized
