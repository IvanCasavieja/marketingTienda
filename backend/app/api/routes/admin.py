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
from app.models.role import Role, ALL_PERMISSIONS
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
# Permisos disponibles
# ---------------------------------------------------------------------------

@router.get("/permissions")
async def list_permissions(_: User = Depends(_require_superuser)):
    return [
        {"key": key, "description": desc}
        for key, desc in ALL_PERMISSIONS.items()
    ]


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

class CreateRoleRequest(BaseModel):
    name: str
    description: str = ""
    permissions: list[str] = []


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


@router.get("/roles")
async def list_roles(
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Role).order_by(Role.id))
    roles = result.scalars().all()
    return [
        {
            "id":          r.id,
            "name":        r.name,
            "description": r.description,
            "permissions": r.permissions or [],
            "is_system":   r.is_system,
        }
        for r in roles
    ]


@router.post("/roles", status_code=201)
async def create_role(
    payload: CreateRoleRequest,
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    unknown = [p for p in payload.permissions if p not in ALL_PERMISSIONS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Permisos desconocidos: {unknown}")

    existing = await db.execute(select(Role).where(Role.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un rol con ese nombre")

    role = Role(
        name=payload.name,
        description=payload.description,
        permissions=payload.permissions,
        is_system=False,
    )
    db.add(role)
    await db.flush()
    return {"id": role.id, "name": role.name, "description": role.description, "permissions": role.permissions, "is_system": False}


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: int,
    payload: UpdateRoleRequest,
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    if payload.permissions is not None:
        unknown = [p for p in payload.permissions if p not in ALL_PERMISSIONS]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Permisos desconocidos: {unknown}")
        role.permissions = payload.permissions

    if payload.name is not None:
        if role.is_system:
            raise HTTPException(status_code=400, detail="No se puede renombrar un rol del sistema")
        role.name = payload.name

    if payload.description is not None:
        role.description = payload.description

    db.add(role)
    return {"id": role.id, "name": role.name, "description": role.description, "permissions": role.permissions, "is_system": role.is_system}


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: int,
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    if role.is_system:
        raise HTTPException(status_code=400, detail="No se pueden eliminar roles del sistema")
    db.delete(role)
    return None


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role_id: int | None = None
    is_superuser: bool = False


class AssignRoleRequest(BaseModel):
    role_id: int | None


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None


@router.get("/users")
async def list_users(
    _: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()

    role_ids = {u.role_id for u in users if u.role_id}
    roles_map: dict[int, Role] = {}
    if role_ids:
        roles_result = await db.execute(select(Role).where(Role.id.in_(role_ids)))
        for r in roles_result.scalars().all():
            roles_map[r.id] = r

    return [
        {
            "id":           u.id,
            "email":        u.email,
            "full_name":    u.full_name,
            "role_id":      u.role_id,
            "role_name":    roles_map[u.role_id].name if u.role_id and u.role_id in roles_map else None,
            "permissions":  roles_map[u.role_id].permissions if u.role_id and u.role_id in roles_map else [],
            "is_active":    u.is_active,
            "is_superuser": u.is_superuser,
            "created_at":   u.created_at.isoformat() if u.created_at else None,
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

    if payload.role_id is not None:
        role = await db.get(Role, payload.role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Rol no encontrado")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role_id=payload.role_id,
        is_superuser=payload.is_superuser,
    )
    db.add(user)
    await db.flush()
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    current_user: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if payload.email is not None and payload.email != user.email:
        existing = await db.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="El email ya está en uso por otro usuario")
        user.email = payload.email

    if payload.full_name is not None:
        user.full_name = payload.full_name

    db.add(user)
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


@router.patch("/users/{user_id}/role")
async def assign_role(
    user_id: int,
    payload: AssignRoleRequest,
    current_user: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Prevent removing Superadmin role from yourself
    if user.id == current_user.id and payload.role_id is None:
        raise HTTPException(status_code=400, detail="No podés quitarte el rol a vos mismo")

    if payload.role_id is not None:
        role = await db.get(Role, payload.role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
        # Sync is_superuser with Superadmin role
        user.is_superuser = role.name == "Superadmin"

    user.role_id = payload.role_id
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
