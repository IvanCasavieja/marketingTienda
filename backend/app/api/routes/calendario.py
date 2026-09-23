"""calendario.py — el calendario comercial, el de Retail Media y los headers.

  GET  /calendario/meses            — todos los meses guardados
  GET  /calendario/meses/{clave}    — uno solo ('YYYY-MM')
  PUT  /calendario/meses/{clave}    — guarda el mes entero
  POST /calendario/aviso-retail     — avisa que alguien movió las posiciones de RM

Hasta el 23/09/2026 el calendario vivía en el localStorage de cada navegador:
cada persona veía su propia copia y el servidor no sabía que existía ninguna
acción, así que no podía avisar nada con anticipación. Acá pasa a la base.

El mes se guarda como documento, tal cual lo arma el front. Ver el modelo para
por qué no se parte en tablas.
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import client_ip as _client_ip, require_permission
from app.models.audit_log import AuditLog
from app.models.calendario_mes import CalendarioMes
from app.models.notificacion import Notificacion
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendario", tags=["calendario"])

_CLAVE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validar_clave(clave: str) -> str:
    if not _CLAVE.match(clave):
        raise HTTPException(status_code=422, detail="El mes se escribe 'YYYY-MM'")
    return clave


class MesEntrante(BaseModel):
    # El mes completo tal cual lo tiene el front (tipo `Mes`). No se valida
    # campo por campo a propósito: el modelo del calendario cambia seguido y
    # duplicar acá su forma haría que cada cambio del front rompa el guardado.
    datos: dict = Field(..., description="El mes entero, tal cual lo arma el calendario")


class AvisoRetail(BaseModel):
    clave: str
    antes: list[int]
    ahora: list[int]


@router.get("/meses")
async def listar_meses(
    _: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Todos los meses guardados, como {clave: datos}. El front decide cuáles
    usa y arma los que falten."""
    meses = (await db.execute(select(CalendarioMes).order_by(CalendarioMes.clave))).scalars()
    return {m.clave: m.datos for m in meses}


@router.get("/meses/{clave}")
async def traer_mes(
    clave: str,
    _: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    _validar_clave(clave)
    mes = (await db.execute(
        select(CalendarioMes).where(CalendarioMes.clave == clave)
    )).scalar_one_or_none()
    if mes is None:
        raise HTTPException(status_code=404, detail="Ese mes todavía no está guardado")
    return {"clave": mes.clave, "datos": mes.datos}


@router.put("/meses/{clave}")
async def guardar_mes(
    clave: str,
    payload: MesEntrante,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Guarda el mes entero. Es un reemplazo, no un merge: el calendario manda
    el estado completo después de cada cambio, y dos personas editando el mismo
    mes a la vez se pisan — igual que pasaba con el Excel, y con la ventaja de
    que ahora queda quién lo tocó último."""
    _validar_clave(clave)
    mes = (await db.execute(
        select(CalendarioMes).where(CalendarioMes.clave == clave)
    )).scalar_one_or_none()
    if mes is None:
        mes = CalendarioMes(clave=clave)
        db.add(mes)
    mes.datos = payload.datos
    mes.actualizado_por_id = current_user.id
    await db.commit()
    return {"clave": clave, "guardado": True}


@router.post("/aviso-retail", status_code=201)
async def avisar_retail_media(
    payload: AvisoRetail,
    request: Request,
    current_user: User = Depends(require_permission("calendario.retail_media")),
    db: AsyncSession = Depends(get_db),
):
    """Le avisa a quien lleva Retail Media que le movieron las posiciones.

    El aviso entra en las notificaciones de la plataforma, no en una bandeja
    propia del calendario: la campanita ya existe y es por persona.
    Destinatarios: los que tengan `calendario.retail_media`, menos el que lo
    movió — avisarse a uno mismo es ruido."""
    _validar_clave(payload.clave)

    usuarios = (await db.execute(select(User).where(User.is_active == True))).scalars()  # noqa: E712
    destinatarios = [
        u for u in usuarios
        if u.id != current_user.id
        and (u.is_superuser or "calendario.retail_media" in (u.permissions or []))
    ]
    mensaje = (
        f"{current_user.full_name} movió las posiciones de Retail Media en "
        f"{payload.clave}: {', '.join(map(str, payload.antes)) or '—'} → "
        f"{', '.join(map(str, payload.ahora)) or '—'}"
    )
    ref = f"{payload.clave}:{'-'.join(map(str, payload.ahora))}"
    for usuario in destinatarios:
        db.add(Notificacion(
            user_id=usuario.id,
            tipo="calendario_header",
            mensaje=mensaje,
            origen_tipo="calendario_header",
            origen_ref=ref,
        ))
    db.add(AuditLog(
        user_id=current_user.id, action="calendario.posiciones_rm", resource="calendario_mes",
        resource_id=payload.clave, details={"antes": payload.antes, "ahora": payload.ahora},
        ip_address=_client_ip(request),
    ))
    await db.commit()
    return {"avisados": len(destinatarios)}
