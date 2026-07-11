"""Cliente Redis async — singleton lazy-initialized."""
import redis.asyncio as aioredis
from redis.backoff import NoBackoff
from redis.retry import Retry
from app.core.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        # Timeouts cortos + cero reintentos, a propósito: si Redis no
        # responde, el código que lo usa (ver auth.py) está pensado para
        # degradar y seguir sin él — pero eso solo sirve si la falla llega
        # rápido. Sin esto, el cliente reintenta con backoff antes de tirar
        # la excepción, y un login normal termina tardando ~9 segundos por
        # request (comprobado en vivo) — una demora así es explotable como
        # DoS de conexiones.
        _client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=False,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
            retry_on_timeout=False,
            retry_on_error=[],
            retry=Retry(NoBackoff(), 0),
        )
    return _client
