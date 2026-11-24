"""ia_brief.py — ordenar con IA un pedido dictado para la agencia.

  POST /ia/brief/ordenar   — {texto, tipo} → campos del tipo de pieza + lo que falta

El dictado lo hace el navegador (Web Speech API, sin servicios pagos de voz):
acá llega solo el texto, dictado o escrito a mano, que es el mismo flujo. Lo
usa el componente `frontend/components/ia/DictarBrief.tsx`, pensado para
enchufarse en cualquier formulario de pedido (hoy, el detalle de una tarea del
calendario). La lógica de qué campos lleva cada tipo y qué falta está en
app/services/brief_ia.py.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_any_permission
from app.core.rate_limit import limiter
from app.models.user import User
from app.services import brief_ia, ia_cliente
from app.services.ai_usage_service import log_ai_usage, resumir_usage
from app.services.calendario_consultas import hoy_en_uruguay

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ia", tags=["ia"])

# Quién puede pedir que la IA ordene un pedido: quien puede escribirlo en algún
# lado (el detalle de una tarea o una acción). Ver solo el calendario no
# alcanza: no tendría dónde usar el resultado, y cada llamada se paga. Cuando
# el formulario de "entregas por fases" lo use, su permiso se suma acá.
# `calendario.pedidos` (0071): el dictado está en "Nueva tarea", y quien
# pide piezas puede no editar el calendario.
PERMISOS_BRIEF = ("calendario.tareas", "calendario.edit", "calendario.pedidos")


class PedidoBrief(BaseModel):
    # El tope va en el modelo: un texto más largo es un 422 antes de llegar a
    # la IA (y de pagarla).
    texto: str = Field(..., min_length=1, max_length=brief_ia.MAX_TEXTO)
    tipo: brief_ia.TipoPieza


@router.post("/brief/ordenar")
# Una persona ordenando su pedido lo hace una o dos veces; diez por minuto es
# para que nadie (ni un botón trabado) gaste de más.
@limiter.limit("10/minute")
async def ordenar_brief(
    request: Request,
    body: PedidoBrief,
    current_user: User = Depends(require_any_permission(*PERMISOS_BRIEF)),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="La IA no está configurada en este servidor")
    texto = body.texto.strip()
    if len(texto) < 3:
        raise HTTPException(status_code=422, detail="Dictá o escribí el pedido primero")

    try:
        resultado, uso = await brief_ia.ordenar(
            texto, body.tipo, cliente=ia_cliente.cliente_anthropic(), hoy=hoy_en_uruguay(),
        )
    except brief_ia.BriefNoOrdenado as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.warning("ia_brief: no se pudo ordenar el pedido — %s", exc)
        raise HTTPException(status_code=502, detail="No se pudo contactar a la IA. Probá de nuevo en un rato.")

    usage_items = []
    if uso:
        # Igual que Don Tino: lo leído y escrito en caché se suma como entrada
        # (el costo estimado queda por encima del real, el lado seguro).
        input_tokens = (
            (uso.input_tokens or 0)
            + (getattr(uso, "cache_creation_input_tokens", 0) or 0)
            + (getattr(uso, "cache_read_input_tokens", 0) or 0)
        )
        output_tokens = uso.output_tokens or 0
        usage_items.append({
            "provider": "anthropic", "model": settings.MODELO_IA,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
        })
        await log_ai_usage(
            db, current_user.id, "brief_dictado", "anthropic", settings.MODELO_IA,
            input_tokens, output_tokens,
        )
    return {**resultado, "usage": resumir_usage(usage_items)}
