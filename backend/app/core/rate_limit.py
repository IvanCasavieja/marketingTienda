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
from app.core.security import decode_token


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


def clave_de_quien_pide(request: Request) -> str:
    """De quién es el balde: de la PERSONA si viene con sesión, de la IP si no.

    Por IP, toda la oficina (que sale a internet por la misma) compartía un
    solo balde: con el calendario preguntando cada 15 s y la campanita, unas
    40 personas agotaban los 200 por minuto y le empezaba a salir 429 a
    cualquiera. El token va firmado, así que nadie puede usar el balde de
    otro; uno vencido o trucho cae en el de su IP, como quien no inició
    sesión (el login, la recuperación de contraseña)."""
    auth = request.headers.get("Authorization") or ""
    token = auth[7:].strip() if auth[:7].lower() == "bearer " else request.cookies.get("access_token")
    if token:
        datos = decode_token(token)
        if datos.get("type") == "access" and datos.get("sub"):
            return f"usuario:{datos['sub']}"
    return ip_de_quien_pide(request)


limiter = Limiter(key_func=clave_de_quien_pide, default_limits=["200/minute"])


async def limite_general(request: Request) -> None:
    """El límite por defecto (200 por minuto) para las rutas que no tienen uno
    propio con @limiter.limit.

    Antes lo ponía el SlowAPIMiddleware, pero desde FastAPI 0.139 (julio de
    2026) las rutas de la API quedan adentro de un router intermedio y el
    middleware ya no las encuentra: las dejaba TODAS sin límite, sin ningún
    error (auditoría 15/11/2026: 210 pedidos seguidos, ningún 429). Como
    dependencia del router corre después de que FastAPI eligió la ruta, así
    que el endpoint siempre está, sea cual sea la versión. Y el 429 sale por
    el manejador de excepciones de la app, con los headers de CORS: el
    navegador lo muestra como lo que es y no como un error de CORS."""
    endpoint = request.scope.get("endpoint")
    if endpoint is None or not limiter.enabled:
        return
    nombre = f"{endpoint.__module__}.{endpoint.__name__}"
    # Las que tienen su propio @limiter.limit se cuentan ahí (como hacía el middleware).
    if nombre in limiter._route_limits or nombre in limiter._exempt_routes:
        return
    limiter._check_request_limit(request, endpoint, True)
