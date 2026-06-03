"""Endpoints de administración — solo superusuarios."""
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import hash_password
from app.models.team import TeamGroup
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Acceso denegado — solo administradores")
    return current_user


def _temp_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$"
    pwd = (
        secrets.choice(string.ascii_uppercase)
        + secrets.choice(string.digits)
        + secrets.choice("!@#$")
        + "".join(secrets.choice(chars) for _ in range(length - 3))
    )
    return pwd


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    team_group_id: int | None = None
    is_superuser: bool = False


class AssignTeamRequest(BaseModel):
    team_group_id: int | None


@router.get("/users")
async def list_users(
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [
        {
            "id":            u.id,
            "email":         u.email,
            "full_name":     u.full_name,
            "team_group_id": u.team_group_id,
            "is_active":     u.is_active,
            "is_superuser":  u.is_superuser,
            "created_at":    u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users", status_code=201)
async def create_user(
    payload: CreateUserRequest,
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email ya registrado")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        team_group_id=payload.team_group_id,
        is_superuser=payload.is_superuser,
    )
    db.add(user)
    await db.flush()
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    temp_pwd = _temp_password()
    user.hashed_password = hash_password(temp_pwd)
    db.add(user)
    return {"temp_password": temp_pwd, "message": "Contraseña reseteada — compartila de forma segura"}


@router.patch("/users/{user_id}/team")
async def assign_team(
    user_id: int,
    payload: AssignTeamRequest,
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if payload.team_group_id is not None:
        grp = await db.get(TeamGroup, payload.team_group_id)
        if not grp:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")

    user.team_group_id = payload.team_group_id
    db.add(user)
    return {"ok": True}


@router.patch("/users/{user_id}/activate")
async def toggle_active(
    user_id: int,
    payload: dict,
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.is_active = bool(payload.get("is_active", True))
    db.add(user)
    return {"is_active": user.is_active}


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

@router.get("/team-groups")
async def list_team_groups(
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TeamGroup).order_by(TeamGroup.id))
    groups = result.scalars().all()
    return [
        {
            "id":        g.id,
            "name":      g.name,
            "team_type": g.team_type,
            "team_id":   g.team_id,
        }
        for g in groups
    ]
