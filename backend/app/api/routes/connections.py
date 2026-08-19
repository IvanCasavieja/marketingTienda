from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import List
from app.core.database import get_db
from app.core.deps import require_permission, client_ip as _client_ip
from app.core.security import encrypt_token, verify_password
from app.core.rate_limit import limiter
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.platform_connection import PlatformConnection, Platform

router = APIRouter(prefix="/connections", tags=["connections"])


# Crear/borrar una conexión maneja un access_token real de una cuenta
# publicitaria — además del permiso, se exige reconfirmar la contraseña de
# quien lo está haciendo (como /auth/change-password) para que no alcance con
# tener una sesión abierta. Tercer nivel: nunca se devuelve el token guardado
# por ningún endpoint (ver ConnectionOut) y queda cifrado en DB (encrypt_token).
class ConnectionCreate(BaseModel):
    platform: Platform
    account_id: str
    account_name: str | None = None
    access_token: str
    refresh_token: str | None = None
    current_password: str


class ConnectionDelete(BaseModel):
    current_password: str


class ConnectionOut(BaseModel):
    id: int
    platform: Platform
    account_id: str
    account_name: str | None
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ConnectionOut])
async def list_connections(
    _: User = Depends(require_permission("connections.view")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PlatformConnection))
    return result.scalars().all()


@router.post("/", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_connection(
    request: Request,
    payload: ConnectionCreate,
    current_user: User = Depends(require_permission("connections.manage")),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Contraseña incorrecta")

    existing = await db.execute(
        select(PlatformConnection).where(
            and_(
                PlatformConnection.platform == payload.platform,
                PlatformConnection.account_id == payload.account_id,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Connection already exists")

    conn = PlatformConnection(
        platform=payload.platform,
        account_id=payload.account_id,
        account_name=payload.account_name,
        access_token_enc=encrypt_token(payload.access_token),
        refresh_token_enc=encrypt_token(payload.refresh_token) if payload.refresh_token else None,
    )
    db.add(conn)
    await db.flush()

    db.add(AuditLog(
        user_id=current_user.id,
        action="connection.create",
        resource="platform_connection",
        resource_id=str(conn.id),
        ip_address=_client_ip(request),
        details={"platform": payload.platform.value, "account_id": payload.account_id},
    ))
    return conn


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_connection(
    request: Request,
    connection_id: int,
    payload: ConnectionDelete,
    current_user: User = Depends(require_permission("connections.manage")),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Contraseña incorrecta")

    result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    db.add(AuditLog(
        user_id=current_user.id,
        action="connection.delete",
        resource="platform_connection",
        resource_id=str(conn.id),
        ip_address=_client_ip(request),
        details={"platform": conn.platform.value, "account_id": conn.account_id},
    ))
    await db.delete(conn)
