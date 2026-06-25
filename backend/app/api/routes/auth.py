import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import get_db

from app.core.config import settings
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.core.deps import get_current_user
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshRequest,
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_MAX_AGE_ACCESS  = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
_COOKIE_MAX_AGE_REFRESH = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    is_prod = settings.APP_ENV == "production"
    common = dict(httponly=True, secure=is_prod, samesite="none" if is_prod else "lax")
    response.set_cookie("access_token",  access_token,  max_age=_COOKIE_MAX_AGE_ACCESS,  **common)
    response.set_cookie("refresh_token", refresh_token, max_age=_COOKIE_MAX_AGE_REFRESH, **common)


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _user_response(user: User) -> UserResponse:
    role = user.role
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        role_id=role.id if role else None,
        role_name=role.name if role else None,
        permissions=role.permissions if role else [],
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.flush()

    db.add(AuditLog(user_id=user.id, action="user.register", ip_address=_client_ip(request)))
    return _user_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    db.add(AuditLog(user_id=user.id, action="user.login", ip_address=_client_ip(request)))

    access_token  = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    # Accept token from cookie (primary) or request body (legacy clients)
    token = request.cookies.get("refresh_token")
    if not token:
        try:
            body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
            token = body.get("refresh_token") if isinstance(body, dict) else None
        except Exception:
            token = None
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    data = decode_token(token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    try:
        sub_id = int(data["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == sub_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token  = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .options(selectinload(User.role))
        .where(User.id == current_user.id)
    )
    return _user_response(result.scalar_one())


import logging as _logging
_logger = _logging.getLogger(__name__)
_RESET_TOKEN_TTL = 3600  # 1 hora


@router.post("/forgot-password", status_code=200)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    if not settings.RESEND_API_KEY:
        raise HTTPException(status_code=503, detail="Email service not configured")

    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if user:
        from app.core.redis_client import get_redis
        from app.services.email_service import send_email, build_reset_email

        token = secrets.token_urlsafe(32)
        redis = get_redis()
        await redis.setex(f"pwd_reset:{token}", _RESET_TOKEN_TTL, str(user.id))

        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        html, plain = build_reset_email(reset_url)
        try:
            await send_email(user.email, "Recuperá tu contraseña — MKTG Platform", html, plain)
        except Exception as exc:
            _logger.error("Failed to send password reset email to %s: %s", user.email, exc)
            raise HTTPException(status_code=502, detail="Error al enviar el email. Intentá de nuevo.")

    # Respuesta idéntica exista o no el email — evita enumeración
    return {"message": "Si el email está registrado, vas a recibir el link en los próximos minutos."}


@router.post("/reset-password", status_code=200)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.core.redis_client import get_redis

    redis = get_redis()
    redis_key = f"pwd_reset:{payload.token}"
    raw = await redis.get(redis_key)

    if not raw:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    try:
        user_id = int(raw.decode() if isinstance(raw, bytes) else raw)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    user.hashed_password = hash_password(payload.new_password)
    await redis.delete(redis_key)  # token de un solo uso
    db.add(AuditLog(user_id=user.id, action="user.password_reset"))

    return {"message": "Contraseña actualizada correctamente."}


