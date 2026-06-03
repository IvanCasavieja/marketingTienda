import httpx
from datetime import date
from typing import List
from app.connectors.base import BaseConnector

# Códigos de error de Meta que indican token inválido / expirado
_META_TOKEN_ERROR_CODES = {190, 102, 200, 467, 463}


def _parse_meta_error(response: httpx.Response) -> str:
    """Extrae el mensaje de error legible del body de la Graph API."""
    try:
        err = response.json().get("error", {})
        msg  = err.get("message", "")
        code = err.get("code", 0)
        sub  = err.get("error_subcode", 0)
        if code in _META_TOKEN_ERROR_CODES or sub in _META_TOKEN_ERROR_CODES:
            return f"Token de Meta Ads inválido o expirado (code {code}): {msg}"
        if code == 17:
            return "Rate limit de Meta Ads — reintentá en unos minutos"
        if code == 10:
            return "Permisos insuficientes en el token de Meta Ads (ads_read requerido)"
        return f"Meta Ads API error {code}: {msg}" if msg else f"HTTP {response.status_code}"
    except Exception:
        return f"HTTP {response.status_code}"


class MetaAdsConnector(BaseConnector):
    BASE_URL = "https://graph.facebook.com/v20.0"

    async def fetch_campaigns(self, date_from: date, date_to: date) -> List[dict]:
        fields = "campaign_id,campaign_name,impressions,clicks,spend,reach,actions,action_values,date_start"
        params = {
            "fields": fields,
            "time_range": f'{{"since":"{date_from}","until":"{date_to}"}}',
            "time_increment": "1",
            "level": "campaign",
            "access_token": self.access_token,
            "limit": 500,
        }
        results = []
        url = f"{self.BASE_URL}/act_{self.account_id}/insights"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                while url:
                    resp = await client.get(url, params=params)
                    if not resp.is_success:
                        raise ValueError(_parse_meta_error(resp))
                    data = resp.json()
                    # La Graph API puede devolver 200 con un objeto "error" dentro
                    if "error" in data:
                        raise ValueError(_parse_meta_error(resp))
                    results.extend(data.get("data", []))
                    url = data.get("paging", {}).get("next")
                    params = {}
        except httpx.TimeoutException:
            raise ValueError("Timeout conectando a Meta Ads API — reintentá más tarde")
        except httpx.NetworkError as exc:
            raise ValueError(f"Error de red al conectar con Meta Ads: {exc}")

        return results

    def normalize(self, raw: List[dict], date_from: date, date_to: date) -> List[dict]:
        normalized = []
        for row in raw:
            spend = float(row.get("spend", 0))
            impressions = int(row.get("impressions", 0))
            clicks = int(row.get("clicks", 0))
            reach = int(row.get("reach", 0))

            actions = {a["action_type"]: float(a["value"]) for a in row.get("actions", [])}
            action_values = {a["action_type"]: float(a["value"]) for a in row.get("action_values", [])}
            conversions = int(actions.get("purchase", actions.get("offsite_conversion.fb_pixel_purchase", 0)))
            revenue = action_values.get("purchase", action_values.get("offsite_conversion.fb_pixel_purchase", 0.0))

            normalized.append({
                "platform": "meta",
                "account_id": self.account_id,
                "campaign_id": row["campaign_id"],
                "campaign_name": row.get("campaign_name", ""),
                "date": row.get("date_start", str(date_from)),
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
