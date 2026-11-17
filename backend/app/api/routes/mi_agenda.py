"""Mi agenda: el calendario de cada persona (Outlook, Google) adentro de Core Tienda.

    GET    /calendario/mi-agenda              — mis eventos (y lo relee si pasaron 15 min)
    PUT    /calendario/mi-agenda              — conectar (o cambiar) el link
    POST   /calendario/mi-agenda/actualizar   — releerlo ya
    DELETE /calendario/mi-agenda              — desconectarlo

Pedido de Ivan (17/11/2026), en lugar del link que llevaba las acciones de
Tienda a Outlook: cada persona trae su calendario y lo ve en la fila "Mi
agenda". Todo es de quien pregunta: no hay forma de pedir la agenda de otro.
Las reglas de leer el link están en app/services/agenda_externa.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import alcance
from app.core.alcance import hoy_en_uruguay
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.rate_limit import limiter
from app.core.security import decrypt_token, encrypt_token
from app.models.agenda import AgendaExterna
from app.models.user import User
from app.services import agenda_externa
from app.services.agenda_externa import AgendaInvalida

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendario", tags=["calendario"])

_SIN_AGENDA = {"conectada": False, "leidaEl": None, "error": None, "eventos": []}


async def _duenio(current_user: User = Depends(require_permission("calendario.view"))) -> User:
    """Quien pregunta, si ve el calendario (la fila está adentro del
    calendario: una agencia, que no lo ve, tampoco tiene agenda)."""
    alcance.exigir_calendario(current_user)
    return current_user


def _json(agenda: AgendaExterna) -> dict:
    return {
        "conectada": True,
        "leidaEl": agenda.leida_at.isoformat() if agenda.leida_at else None,
        "error": agenda.error,
        "eventos": list(agenda.eventos or []),
    }


async def _releer(agenda: AgendaExterna) -> None:
    """Vuelve a leer el link. Si no se puede, quedan los eventos de antes y el
    motivo, para mostrarlo."""
    try:
        agenda.eventos = await agenda_externa.traer(decrypt_token(agenda.url_cifrada), hoy_en_uruguay())
        agenda.error = None
    except AgendaInvalida as exc:
        agenda.error = str(exc)
    except Exception:
        logger.exception("mi agenda: no se pudo releer el calendario de %s", agenda.user_id)
        agenda.error = "No se pudo leer el calendario. Se vuelve a intentar en un rato."
    agenda.leida_at = datetime.now(timezone.utc)


@router.get("/mi-agenda")
async def ver_mi_agenda(
    current_user: User = Depends(_duenio),
    db: AsyncSession = Depends(get_db),
):
    agenda = await db.get(AgendaExterna, current_user.id)
    if agenda is None:
        return _SIN_AGENDA
    vieja = agenda.leida_at is None or datetime.now(timezone.utc) - agenda.leida_at > agenda_externa.VIGENCIA
    if vieja:
        await _releer(agenda)
        await db.commit()
    return _json(agenda)


class Conexion(BaseModel):
    url: str = Field(..., max_length=agenda_externa.LARGO_URL)


@router.put("/mi-agenda")
@limiter.limit("10/minute")
async def conectar_mi_agenda(
    payload: Conexion,
    request: Request,
    current_user: User = Depends(_duenio),
    db: AsyncSession = Depends(get_db),
):
    """Se lee una vez antes de guardarlo: un link que no es un calendario se
    avisa ahora, no la próxima vez que se mire."""
    try:
        url = agenda_externa.normalizar_url(payload.url)
        eventos = await agenda_externa.traer(url, hoy_en_uruguay())
    except AgendaInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    agenda = await db.get(AgendaExterna, current_user.id)
    if agenda is None:
        agenda = AgendaExterna(user_id=current_user.id)
        db.add(agenda)
    agenda.url_cifrada = encrypt_token(url)
    agenda.eventos = eventos
    agenda.error = None
    agenda.leida_at = datetime.now(timezone.utc)
    await db.commit()
    return _json(agenda)


@router.post("/mi-agenda/actualizar")
@limiter.limit("10/minute")
async def actualizar_mi_agenda(
    request: Request,
    current_user: User = Depends(_duenio),
    db: AsyncSession = Depends(get_db),
):
    agenda = await db.get(AgendaExterna, current_user.id)
    if agenda is None:
        return _SIN_AGENDA
    await _releer(agenda)
    await db.commit()
    return _json(agenda)


@router.delete("/mi-agenda")
async def desconectar_mi_agenda(
    current_user: User = Depends(_duenio),
    db: AsyncSession = Depends(get_db),
):
    agenda = await db.get(AgendaExterna, current_user.id)
    if agenda is not None:
        await db.delete(agenda)
        await db.commit()
    return _SIN_AGENDA
