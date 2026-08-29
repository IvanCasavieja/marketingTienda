"""Precios de referencia por modelo, en USD por millón de tokens — mantenidos
a mano, no se consultan en vivo. Actualizar acá cuando cambien las tarifas
públicas de cada proveedor. Un modelo desconocido no rompe nada: estimate_cost
devuelve 0 y se loguea igual (mejor tener tokens sin costo que perder el
registro de la llamada)."""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# (provider, model) -> {"input": $/millón tokens input, "output": $/millón tokens output}
_PRICING: dict[tuple[str, str], dict[str, Decimal]] = {
    ("anthropic", "claude-sonnet-5"):   {"input": Decimal("2.00"), "output": Decimal("10.00")},
    # Queda el anterior para que las llamadas ya registradas conserven su costo
    # real: el histórico del informe de consumo se calculó con esta tarifa.
    ("anthropic", "claude-sonnet-4-6"): {"input": Decimal("3.00"), "output": Decimal("15.00")},
    ("openai", "gpt-4o"): {"input": Decimal("2.50"), "output": Decimal("10.00")},
    ("openai", "gpt-4o-search-preview"): {"input": Decimal("2.50"), "output": Decimal("10.00")},
    ("openai", "gpt-5.4"): {"input": Decimal("2.00"), "output": Decimal("10.00")},
    ("groq", "llama-3.3-70b-versatile"): {"input": Decimal("0.59"), "output": Decimal("0.79")},
}


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    pricing = _PRICING.get((provider, model))
    if not pricing:
        logger.warning("ai_pricing: sin precio de referencia para (%s, %s)", provider, model)
        return Decimal("0")
    cost = (Decimal(input_tokens) * pricing["input"] + Decimal(output_tokens) * pricing["output"]) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))
