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

from app.core.config import settings


def ip_de_la_cadena(forwarded: str | None, saltos_de_confianza: int) -> str | None:
    """La IP del cliente según X-Forwarded-For.

    El primer eslabón lo escribe quien pide, así que se puede falsear
    (auditoría 15/11/2026: 12 logins rotando ese header y ningún 429). Lo que
    agregan los proxies propios va al final: con `saltos_de_confianza` = N se
    toma el eslabón N contando desde el final, que es el que escribió nuestro
    proxy y no se puede falsear. Con 0 (el valor por defecto) se sigue
    tomando el primero, como siempre: se prende con PROXY_SALTOS_DE_CONFIANZA
    después de confirmar en los logs cómo arma la cadena Render (o Azure)."""
    if not forwarded:
        return None
    cadena = [p.strip() for p in forwarded.split(",") if p.strip()]
    if not cadena:
        return None
    if saltos_de_confianza <= 0 or len(cadena) < saltos_de_confianza:
        return cadena[0]
    return cadena[-saltos_de_confianza]


def ip_de_quien_pide(request: Request) -> str:
    """La IP del cliente, no la del proxy. Sin esto el límite es compartido."""
    ip = ip_de_la_cadena(request.headers.get("X-Forwarded-For"), settings.PROXY_SALTOS_DE_CONFIANZA)
    return ip or get_remote_address(request)


limiter = Limiter(key_func=ip_de_quien_pide, default_limits=["200/minute"])
