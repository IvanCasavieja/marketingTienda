"""El límite de pedidos por minuto.

OJO con la clave: `get_remote_address` de slowapi mira `request.client.host`, y
detrás del proxy de Render eso es SIEMPRE la IP del proxy, no la de quien pide.
Con esa clave TODA la plataforma comparte un solo balde de 200 pedidos por
minuto: alcanza con que tres personas trabajen a la vez para que al cuarto le
empiece a salir 429 sin haber hecho nada. Y encima el navegador lo reporta como
un error de CORS, porque la respuesta de rechazo no lleva los headers.

La IP real viene en X-Forwarded-For, igual que para el AuditLog (ver
`client_ip` en deps.py). Se usa el primer eslabón de la cadena, que es el
cliente; los que siguen son proxies.
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def ip_de_quien_pide(request: Request) -> str:
    """La IP del cliente, no la del proxy. Sin esto el límite es compartido."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        primera = forwarded.split(",")[0].strip()
        if primera:
            return primera
    return get_remote_address(request)


limiter = Limiter(key_func=ip_de_quien_pide, default_limits=["200/minute"])
