"""Retry con backoff para llamadas no-streaming a APIs de LLM (Claude/GPT/
Groq). Antes de esto, un rate-limit o 5xx transitorio de cualquiera de los 3
proveedores mataba esa ronda del debate sin reintentar.

Solo se usa en las variantes no-streaming (_ask_claude/_ask_gpt/_ask_llama en
debate_service.py) — reintentar a mitad de un stream ya parcialmente
consumido/reenviado al frontend arriesga duplicar contenido, así que las
variantes _stream quedan afuera a propósito."""
import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Las 3 SDKs (anthropic, openai, groq) exponen estas mismas clases con el
# mismo nombre en su root package — cubre timeout, error de conexión,
# rate limit (429) y 5xx del proveedor.
try:
    import anthropic as _anthropic
    import openai as _openai
    from groq import (
        APIConnectionError as _GroqConnErr,
        APITimeoutError as _GroqTimeoutErr,
        RateLimitError as _GroqRateLimitErr,
        InternalServerError as _GroqInternalErr,
    )
    RETRYABLE_LLM_EXCEPTIONS = (
        _anthropic.APIConnectionError, _anthropic.APITimeoutError,
        _anthropic.RateLimitError, _anthropic.InternalServerError,
        _openai.APIConnectionError, _openai.APITimeoutError,
        _openai.RateLimitError, _openai.InternalServerError,
        _GroqConnErr, _GroqTimeoutErr, _GroqRateLimitErr, _GroqInternalErr,
    )
except ImportError:
    RETRYABLE_LLM_EXCEPTIONS = ()


async def llm_call_with_retry(
    call: Callable[[], Awaitable[T]],
    *,
    label: str,
    retries: int = 3,
    base_delay: float = 1.5,
) -> T:
    """call: función sin argumentos que devuelve la coroutine a esperar (no
    la coroutine ya creada — una coroutine no se puede re-await en el
    siguiente intento)."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await call()
        except RETRYABLE_LLM_EXCEPTIONS as exc:
            last_exc = exc
            if attempt == retries:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "%s: intento %d/%d falló (%s) — reintenta en %.1fs",
                label, attempt, retries, exc, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc
