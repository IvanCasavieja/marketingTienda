from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.models.local_asignacion import LocalAsignacion

bearer_scheme = HTTPBearer(auto_error=False)


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_PASSWORD_MAX_AGE_DAYS = 20

# Rutas que siguen accesibles aunque el usuario tenga la renovación de
# contraseña pendiente — sin esto, no habría forma de llegar a la pantalla
# que le permite justamente cambiarla.
_PASSWORD_CHANGE_EXEMPT_PATHS = {
    "/api/v1/auth/me",
    "/api/v1/auth/change-password",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
}


async def _needs_password_change(user: User, db: AsyncSession) -> bool:
    """Los logins de sucursal (LocalAsignacion) quedan afuera de esta política
    a propósito: comparten contraseña por diseño y ya no pueden cambiarla
    ellos mismos (ver /auth/change-password), así que exigírselo los dejaría
    trabados sin salida."""
    is_sucursal = (await db.execute(
        select(LocalAsignacion).where(LocalAsignacion.user_id == user.id).limit(1)
    )).scalar_one_or_none() is not None
    if is_sucursal:
        return False

    if user.must_change_password:
        return True

    if user.password_changed_at:
        age = datetime.now(timezone.utc) - user.password_changed_at
        if age > timedelta(days=_PASSWORD_MAX_AGE_DAYS):
            return True

    return False


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    cookie_token = request.cookies.get("access_token")
    header_token = credentials.credentials if credentials else None

    if request.method in _UNSAFE_METHODS:
        # La cookie de sesión viaja sola en un request cross-site (por eso es
        # SameSite=None en producción — frontend y backend son dominios
        # distintos), así que un sitio malicioso podría hacer que el navegador
        # de un usuario logueado dispare un POST/PATCH/DELETE con la cookie
        # puesta, sin que el usuario se entere (CSRF). El header Authorization
        # no viaja solo — el navegador nunca lo agrega automáticamente, hay
        # que leerlo del localStorage de nuestro propio origen — así que exigirlo
        # para cualquier método que escribe/borra neutraliza ese ataque sin
        # afectar el uso normal (nuestro frontend ya lo manda siempre).
        token = header_token
    else:
        token = cookie_token or header_token

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == user_id_int, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # JWT es sin estado — sin esto, un token robado seguía sirviendo después
    # de "cerrar sesión" o de cambiar la contraseña, hasta que expirara solo
    # (hasta 7 días para el refresh token). Cualquier token emitido antes de
    # esta marca queda invalidado, sin tocar la firma ni una lista de baneados.
    #
    # El margen de 2s es porque JWT codifica "iat" en segundos enteros (le
    # trunca los microsegundos), mientras que tokens_invalidated_at en la base
    # los conserva — sin este margen, un token emitido el mismo segundo en que
    # se invalida (ej. el que devuelve /change-password para no cortar la
    # sesión) podía quedar del lado "anterior" solo por el redondeo, y la
    # persona terminaba desconectada justo después de cambiar la contraseña.
    if user.tokens_invalidated_at is not None:
        iat = payload.get("iat")
        issued_at = datetime.fromtimestamp(iat, tz=timezone.utc) if iat else None
        if not issued_at or issued_at < user.tokens_invalidated_at - timedelta(seconds=2):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalidado — volvé a iniciar sesión")

    if request.url.path not in _PASSWORD_CHANGE_EXEMPT_PATHS and await _needs_password_change(user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PASSWORD_CHANGE_REQUIRED",
        )

    return user


def require_permission(permission: str):
    """Dependencia de FastAPI que verifica que el usuario tenga un permiso específico.

    Los permisos viven en User.permissions (no en el rol) — el rol solo sirve
    para sembrar ese valor al asignarlo; de ahí en más cada usuario tiene su
    propia lista, editable desde su perfil."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user
        user_perms = user.permissions or []
        if permission not in user_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso requerido: {permission}",
            )
        return user
    return _check
