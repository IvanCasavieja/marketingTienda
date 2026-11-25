"""La guía de uso (/ayuda), con lo que la persona puede usar.

    GET /guia  — las secciones de la guía que ve quien pregunta

El contenido vive en app/services/guia.py, que es también lo que sabe Don
Tino (25/11/2026): se cambia en un solo lugar. Lo ve cualquier persona
logueada, también una agencia (solo sus secciones: su tablero, la tarjeta y
lo básico) y un local de Redexpres (Mi pedido y sus fotos).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services import guia

router = APIRouter(prefix="/guia", tags=["guia"])


@router.get("")
async def ver_guia(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    local = await guia.tiene_local(db, current_user)
    return {"secciones": guia.como_json(guia.secciones_para(current_user, local))}
