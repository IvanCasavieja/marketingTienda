from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import List
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import encrypt_token
from app.models.user import User
from app.models.platform_connection import PlatformConnection, Platform

router = APIRouter(prefix="/connections", tags=["connections"])


class ConnectionCreate(BaseModel):
    platform: Platform
    account_id: str
    account_name: str | None = None
    access_token: str
    refresh_token: str | None = None


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        return []

    result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.team_group_id == current_user.team_group_id)
    )
    return result.scalars().all()


@router.post("/", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Join a team before creating connections")

    existing = await db.execute(
        select(PlatformConnection).where(
            and_(
                PlatformConnection.team_group_id == current_user.team_group_id,
                PlatformConnection.platform == payload.platform,
                PlatformConnection.account_id == payload.account_id,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Connection already exists")

    conn = PlatformConnection(
        team_group_id=current_user.team_group_id,
        platform=payload.platform,
        account_id=payload.account_id,
        account_name=payload.account_name,
        access_token_enc=encrypt_token(payload.access_token),
        refresh_token_enc=encrypt_token(payload.refresh_token) if payload.refresh_token else None,
    )
    db.add(conn)
    await db.flush()
    return conn


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PlatformConnection).where(
            and_(
                PlatformConnection.id == connection_id,
                PlatformConnection.team_group_id == current_user.team_group_id,
            )
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    await db.delete(conn)
