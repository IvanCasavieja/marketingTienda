import logging
from decimal import Decimal

from app.core.ai_pricing import estimate_cost
from app.models.ai_usage_log import AIUsageLog

logger = logging.getLogger(__name__)


async def log_ai_usage(
    db,
    user_id: int | None,
    feature: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Agrega (sin commitear) una fila de uso/costo de IA. El caller es dueño
    de la transacción — igual que los AuditLog en auth.py, se commitea junto
    con el resto de lo que esa request ya está guardando. Nunca debe romper
    el flujo principal: cualquier error acá se loguea y se traga."""
    try:
        cost = estimate_cost(provider, model, input_tokens, output_tokens)
        db.add(AIUsageLog(
            user_id=user_id,
            feature=feature,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        ))
    except Exception as exc:
        logger.warning("ai_usage_service: no se pudo loguear uso de IA (%s/%s) — %s", provider, model, exc)


def resumir_usage(usage_items: list[dict]) -> dict:
    """usage_items: [{"provider", "model", "input_tokens", "output_tokens"}, ...]
    acumulados por un agente a lo largo de UNA tarea (puede ser más de una
    llamada si hubo vueltas de tool-use). Devuelve el total para mostrarle al
    usuario cuánto costó esa tarea puntual -- no reemplaza el log persistente
    en ai_usage_logs (eso sigue pasando fila por fila via log_ai_usage, sin
    relación con esto)."""
    input_tokens = sum(u["input_tokens"] for u in usage_items)
    output_tokens = sum(u["output_tokens"] for u in usage_items)
    cost = sum(
        (estimate_cost(u["provider"], u["model"], u["input_tokens"], u["output_tokens"]) for u in usage_items),
        start=Decimal("0"),
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": float(cost),
    }
