import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.core.database import get_db

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.core.deps import get_current_user, _needs_password_change, client_ip as _client_ip
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.local_asignacion import LocalAsignacion
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshRequest,
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_logger = logging.getLogger(__name__)
_RESET_TOKEN_TTL = 3600  # 1 hora

_COOKIE_MAX_AGE_ACCESS  = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
_COOKIE_MAX_AGE_REFRESH = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    is_prod = settings.APP_ENV == "production"
    common = dict(httponly=True, secure=is_prod, samesite="none" if is_prod else "lax")
    response.set_cookie("access_token",  access_token,  max_age=_COOKIE_MAX_AGE_ACCESS,  **common)
    response.set_cookie("refresh_token", refresh_token, max_age=_COOKIE_MAX_AGE_REFRESH, **common)


def _clear_auth_cookies(response: Response) -> None:
    # Must pass the same path/secure/samesite that were used when setting the
    # cookie — otherwise the browser won't match and the cookie stays alive.
    is_prod = settings.APP_ENV == "production"
    response.delete_cookie("access_token",  path="/", secure=is_prod, samesite="none" if is_prod else "lax")
    response.delete_cookie("refresh_token", path="/", secure=is_prod, samesite="none" if is_prod else "lax")


def _user_response(
    user: User, assigned_locales: list[str] | None = None, must_change_password: bool = False
) -> UserResponse:
    role = user.role
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        role_id=role.id if role else None,
        role_name=role.name if role else None,
        permissions=user.permissions or [],
        assigned_locales=assigned_locales or [],
        must_change_password=must_change_password,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(payload: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        password_changed_at=datetime.now(timezone.utc),  # elegida por el propio dueño desde el vamos
    )
    db.add(user)
    await db.flush()

    db.add(AuditLog(user_id=user.id, action="user.register", ip_address=_client_ip(request)))
    return _user_response(user)


_LOGIN_FAIL_LIMIT = 5
_LOGIN_LOCKOUT_MINUTES = 15


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(payload: UserLogin, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Bloqueo por intentos fallidos, persistido en la propia fila del
    usuario (no en Redis) — además del límite por IP de arriba, que un
    atacante puede esquivar mandando un X-Forwarded-For distinto en cada
    request (uvicorn confía en ese header por default). Esto no depende de
    la IP en absoluto ni de que Redis esté arriba: a la cuenta objetivo se la
    protege igual, y queda visible/reseteable desde el panel de admin."""
    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(
            status_code=403,
            detail=f"Cuenta bloqueada por intentos fallidos — probá de nuevo después de las {user.locked_until.strftime('%H:%M')} UTC",
        )

    if not user or not verify_password(payload.password, user.hashed_password):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= _LOGIN_FAIL_LIMIT:
                user.locked_until = now + timedelta(minutes=_LOGIN_LOCKOUT_MINUTES)
            db.add(user)
            # get_db() solo hace commit si el endpoint termina sin excepción —
            # como acá siempre levantamos una en el camino de fallo, sin este
            # commit explícito el conteo de intentos se revertía siempre y el
            # bloqueo nunca se activaba (comprobado en vivo: sin esto, una
            # cuenta "bloqueada" seguía aceptando la contraseña correcta).
            await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
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

    if user.tokens_invalidated_at is not None:
        iat = data.get("iat")
        issued_at = datetime.fromtimestamp(iat, tz=timezone.utc) if iat else None
        # Mismo margen de 2s que en get_current_user — ver comentario ahí.
        if not issued_at or issued_at < user.tokens_invalidated_at - timedelta(seconds=2):
            raise HTTPException(status_code=401, detail="Token invalidado — volvé a iniciar sesión")

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
    locales_result = await db.execute(
        select(LocalAsignacion.local_nombre).where(LocalAsignacion.user_id == current_user.id)
    )
    assigned_locales = list(locales_result.scalars().all())
    must_change = await _needs_password_change(current_user, db)
    return _user_response(result.scalar_one(), assigned_locales, must_change)


@router.post("/forgot-password", status_code=200)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    if not settings.SENDGRID_API_KEY:
        raise HTTPException(status_code=503, detail="Email service not configured")

    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if user:
        from app.models.password_reset_token import PasswordResetToken
        from app.services.email_service import send_email, build_reset_email

        now = datetime.now(timezone.utc)
        # Sin TTL nativo como tenía Redis — barremos vencidos acá en vez de
        # un cron aparte, alcanza de sobra para el volumen de este endpoint.
        await db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at < now))

        token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            token=token,
            user_id=user.id,
            expires_at=now + timedelta(seconds=_RESET_TOKEN_TTL),
        ))

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
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.models.password_reset_token import PasswordResetToken

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetToken, User)
        .join(User, User.id == PasswordResetToken.user_id)
        .where(
            PasswordResetToken.token == payload.token,
            PasswordResetToken.expires_at > now,
            User.is_active == True,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
    reset_token, user = row

    user.hashed_password = hash_password(payload.new_password)
    user.tokens_invalidated_at = now
    user.password_changed_at = now
    user.must_change_password = False  # la eligió el propio dueño de la cuenta
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.delete(reset_token)  # token de un solo uso
    db.add(AuditLog(user_id=user.id, action="user.password_reset"))

    return {"message": "Contraseña actualizada correctamente."}


@router.post("/change-password", status_code=200)
@limiter.limit("10/minute")
async def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Un usuario logueado cambia su propia contraseña sabiendo la actual —
    distinto del flujo de /reset-password, que es para cuando no tenés acceso.

    Los logins de sucursal (usuario = contraseña = nombre del local, sin dueño
    individual — ver create_sucursal_users.py) quedan afuera de este flujo:
    la contraseña es pública a propósito dentro del local, así que cualquiera
    que la supiera podría entrar una vez y cambiarla, dejando afuera para
    siempre al resto del personal real. Cambiarla es una decisión de un
    superadmin (vía /admin/users/{id}/reset-password), no autoservicio."""
    has_local = await db.execute(
        select(LocalAsignacion).where(LocalAsignacion.user_id == current_user.id).limit(1)
    )
    if has_local.scalar_one_or_none():
        raise HTTPException(
            status_code=403,
            detail="Los usuarios de sucursal no pueden cambiar su propia contraseña — pedile a un administrador que la resetee",
        )

    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="La nueva contraseña tiene que ser distinta de la actual")

    now = datetime.now(timezone.utc)
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.tokens_invalidated_at = now
    current_user.password_changed_at = now
    current_user.must_change_password = False
    db.add(current_user)
    db.add(AuditLog(user_id=current_user.id, action="user.password_change"))

    # tokens_invalidated_at recién puesto mata cualquier token viejo — incluido
    # el que se está usando en este mismo request. Sin emitir uno nuevo acá, la
    # siguiente llamada del frontend (incluso /auth/me) rebota con 401, el
    # intento de refresh también falla (el refresh token quedó invalidado
    # igual) y el interceptor manda a la persona de vuelta a /login — quedaba
    # forzada a loguearse de nuevo justo después de cambiar la contraseña.
    access_token = create_access_token(current_user.id)
    refresh_token = create_refresh_token(current_user.id)
    _set_auth_cookies(response, access_token, refresh_token)

    return {
        "message": "Contraseña actualizada correctamente.",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


