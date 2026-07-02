import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import date
from app.core.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.connectors.sfmc import SFMCConnector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sfmc", tags=["salesforce-mc"])


class SFMCRequest(BaseModel):
    date_from: date
    date_to: date


def _get_sfmc_connector() -> SFMCConnector:
    if not settings.SFMC_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Salesforce Marketing Cloud not configured")
    return SFMCConnector(
        client_id=settings.SFMC_CLIENT_ID,
        client_secret=settings.SFMC_CLIENT_SECRET,
        subdomain=settings.SFMC_SUBDOMAIN,
        account_id=settings.SFMC_ACCOUNT_ID,
    )


@router.post("/email")
async def get_email_performance(
    payload: SFMCRequest,
    current_user: User = Depends(get_current_user),
):
    connector = _get_sfmc_connector()
    try:
        raw = await connector.fetch_email_performance(payload.date_from, payload.date_to)
        return connector.normalize_email(raw)
    except Exception as e:
        logger.error("SFMC error: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Error al conectar con Salesforce Marketing Cloud")


@router.post("/whatsapp")
async def get_whatsapp_performance(
    payload: SFMCRequest,
    current_user: User = Depends(get_current_user),
):
    connector = _get_sfmc_connector()
    try:
        raw = await connector.fetch_whatsapp_performance(payload.date_from, payload.date_to)
        return connector.normalize_whatsapp(raw)
    except Exception as e:
        logger.error("SFMC error: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Error al conectar con Salesforce Marketing Cloud")
