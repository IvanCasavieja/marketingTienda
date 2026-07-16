"""Retry con backoff exponencial para llamadas HTTP salientes (conectores de
Ads). Antes de esto, un 5xx o timeout transitorio durante el auto-sync de
cada 6hs simplemente perdía esa plataforma para todo el ciclo — con un solo
intento no había margen para que un error pasajero del lado del proveedor
se resolviera solo.

Solo reintenta fallas transitorias (timeout, error de red/conexión, 5xx) —
nunca 4xx, que son errores de la aplicación (token vencido, permisos, query
mal formada) que reintentar no arregla."""
import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_EXC = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 3,
    base_delay: float = 1.0,
    **kwargs,
) -> httpx.Response:
    """Como client.request(method, url, **kwargs), pero reintenta hasta
    `retries` veces ante timeout/error de red o 5xx, con backoff exponencial
    + jitter. Un 4xx se devuelve tal cual en el primer intento."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = await client.request(method, url, **kwargs)
        except _RETRYABLE_EXC as exc:
            last_exc = exc
            if attempt == retries:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "request_with_retry: %s %s falló (%s) — intento %d/%d, reintenta en %.1fs",
                method, url, exc, attempt, retries, delay,
            )
            await asyncio.sleep(delay)
            continue

        if resp.status_code >= 500 and attempt < retries:
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "request_with_retry: %s %s devolvió %d — intento %d/%d, reintenta en %.1fs",
                method, url, resp.status_code, attempt, retries, delay,
            )
            await asyncio.sleep(delay)
            continue

        return resp

    assert last_exc is not None
    raise last_exc
