"""Endpoints de administración — Super Admin y Admin (con restricciones entre sí)."""
import secrets
import string
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import hash_password
from app.core.rate_limit import limiter
from app.models.ai_usage_log import AIUsageLog
from app.models.audit_log import AuditLog
from app.models.local_asignacion import LocalAsignacion
from app.models.role import Role, ALL_PERMISSIONS, is_view_permission
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _require_admin_panel(current_user: User = Depends(get_current_user)) -> User:
    """Puede ver el panel (listar usuarios/roles/permisos)."""
    if current_user.is_superuser or "platform.admin" in (current_user.permissions or []):
        return current_user
    raise HTTPException(status_code=403, detail="Acceso denegado — solo administradores")


def _require_user_management(current_user: User = Depends(get_current_user)) -> User:
    """Puede mutar: crear/editar usuarios, asignar roles y permisos, CRUD de roles."""
    if current_user.is_superuser or "platform.users.manage" in (current_user.permissions or []):
        return current_user
    raise HTTPException(status_code=403, detail="Acceso denegado — permiso de gestión de usuarios requerido")


_ADMIN_TIER_PERMISSIONS = {"platform.super", "platform.admin", "platform.users.manage"}


async def _check_not_protected_admin(current_user: User, target_user: User, db: AsyncSession) -> None:
    """Un Admin (no super) no puede modificar a otro Admin ni al Super Admin —
    solo el Super Admin puede tocar esas cuentas.

    Protege por rol Y por permiso individual: los permisos viven en
    User.permissions y pueden divergir del rol después de asignados, así que
    alcanzar con mirar el nombre del rol dejaba a un usuario "Usuario" con
    platform.users.manage tildado a mano sin ninguna protección entre pares."""
    if current_user.is_superuser:
        return
    if target_user.is_superuser:
        raise HTTPException(status_code=403, detail="Solo el Super Admin puede modificar esta cuenta")
    if _ADMIN_TIER_PERMISSIONS & set(target_user.permissions or []):
        raise HTTPException(status_code=403, detail="No podés modificar a otro administrador")
    if target_user.role_id is not None:
        role = await db.get(Role, target_user.role_id)
        if role and role.name == "Admin":
            raise HTTPException(status_code=403, detail="No podés modificar a otro Admin")


def _ensure_can_grant(current_user: User, permissions: list[str]) -> None:
    """Nadie puede otorgar (a un rol o a un usuario) un permiso que no tiene
    él mismo — sin esto, cualquier cuenta con platform.users.manage podía
    crearse un rol con TODOS los permisos y asignárselo, sin ser Superadmin."""
    if current_user.is_superuser:
        return
    missing = [p for p in permissions if p not in (current_user.permissions or [])]
    if missing:
        raise HTTPException(
            status_code=403,
            detail=f"No podés otorgar permisos que vos mismo no tenés: {missing}",
        )


def _ensure_not_self(current_user: User, user_id: int) -> None:
    """Un Admin (no super) no puede tocar su propio rol/permisos — si pudiera,
    la restricción de 'no otorgar lo que no tenés' se podría esquivar
    escalando de a poco entre varias cuentas con este mismo permiso."""
    if current_user.is_superuser:
        return
    if user_id == current_user.id:
        raise HTTPException(status_code=403, detail="No podés modificar tu propio rol o permisos")


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
async def list_permissions(_: User = Depends(_require_admin_panel)):
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
    _: User = Depends(_require_admin_panel),
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
            "view_only":   r.view_only,
        }
        for r in roles
    ]


@router.post("/roles", status_code=201)
@limiter.limit("20/minute")
async def create_role(
    payload: CreateRoleRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    unknown = [p for p in payload.permissions if p not in ALL_PERMISSIONS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Permisos desconocidos: {unknown}")
    _ensure_can_grant(current_user, payload.permissions)

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
    db.add(AuditLog(
        user_id=current_user.id, action="admin.role.create", resource="role", resource_id=str(role.id),
        details={"name": role.name, "permissions": role.permissions}, ip_address=_client_ip(request),
    ))
    return {"id": role.id, "name": role.name, "description": role.description, "permissions": role.permissions, "is_system": False, "view_only": False}


@router.patch("/roles/{role_id}")
@limiter.limit("20/minute")
async def update_role(
    role_id: int,
    payload: UpdateRoleRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    if payload.permissions is not None:
        unknown = [p for p in payload.permissions if p not in ALL_PERMISSIONS]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Permisos desconocidos: {unknown}")
        if role.is_system and not current_user.is_superuser:
            raise HTTPException(
                status_code=403,
                detail="Solo el Super Admin puede cambiar los permisos de un rol del sistema",
            )
        _ensure_can_grant(current_user, payload.permissions)
        role.permissions = payload.permissions

    if payload.name is not None:
        if role.is_system:
            raise HTTPException(status_code=400, detail="No se puede renombrar un rol del sistema")
        role.name = payload.name

    if payload.description is not None:
        role.description = payload.description

    db.add(role)
    db.add(AuditLog(
        user_id=current_user.id, action="admin.role.update", resource="role", resource_id=str(role.id),
        details={"name": role.name, "permissions": role.permissions}, ip_address=_client_ip(request),
    ))
    return {"id": role.id, "name": role.name, "description": role.description, "permissions": role.permissions, "is_system": role.is_system, "view_only": role.view_only}


@router.delete("/roles/{role_id}", status_code=204)
@limiter.limit("20/minute")
async def delete_role(
    role_id: int,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    if role.is_system:
        raise HTTPException(status_code=400, detail="No se pueden eliminar roles del sistema")
    db.add(AuditLog(
        user_id=current_user.id, action="admin.role.delete", resource="role", resource_id=str(role.id),
        details={"name": role.name}, ip_address=_client_ip(request),
    ))
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


class AssignRoleRequest(BaseModel):
    role_id: int | None


class UpdatePermissionsRequest(BaseModel):
    permissions: list[str]


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None


def _seed_permissions_for_role(role: Role | None) -> list[str]:
    if role is None:
        return []
    perms = list(role.permissions or [])
    if role.view_only:
        perms = [p for p in perms if is_view_permission(p)]
    return perms


@router.get("/users")
async def list_users(
    _: User = Depends(_require_admin_panel),
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
            "permissions":  u.permissions or [],
            "is_active":    u.is_active,
            "is_superuser": u.is_superuser,
            "created_at":   u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users", status_code=201)
@limiter.limit("20/minute")
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email ya registrado")

    role: Role | None = None
    if payload.role_id is not None:
        role = await db.get(Role, payload.role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
        if role.name == "Superadmin" and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Solo el Super Admin puede asignar ese rol")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role_id=payload.role_id,
        permissions=_seed_permissions_for_role(role),
        is_superuser=False,
        # La contraseña la eligió quien está creando la cuenta, no su dueño —
        # se lo obliga a poner una propia en el primer login.
        must_change_password=True,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.create", resource="user", resource_id=str(user.id),
        details={"email": user.email, "role_id": user.role_id}, ip_address=_client_ip(request),
    ))
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


@router.patch("/users/{user_id}")
@limiter.limit("20/minute")
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await _check_not_protected_admin(current_user, user, db)

    if payload.email is not None and payload.email != user.email:
        existing = await db.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="El email ya está en uso por otro usuario")
        user.email = payload.email

    if payload.full_name is not None:
        user.full_name = payload.full_name

    db.add(user)
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.update", resource="user", resource_id=str(user.id),
        details={"email": user.email, "full_name": user.full_name}, ip_address=_client_ip(request),
    ))
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


@router.post("/users/{user_id}/reset-password")
@limiter.limit("20/minute")
async def reset_password(
    user_id: int,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await _check_not_protected_admin(current_user, user, db)

    temp_pwd = _temp_password()
    now = datetime.now(timezone.utc)
    user.hashed_password = hash_password(temp_pwd)
    user.tokens_invalidated_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    # Los logins de sucursal (LocalAsignacion) quedan afuera de la política de
    # renovación — comparten contraseña a propósito y ya no pueden cambiarla
    # ellos mismos, así que "obligarlos" a hacerlo los dejaría trabados.
    is_sucursal = (await db.execute(
        select(LocalAsignacion).where(LocalAsignacion.user_id == user.id).limit(1)
    )).scalar_one_or_none() is not None
    if not is_sucursal:
        user.must_change_password = True
    user.password_changed_at = now
    db.add(user)
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.reset_password", resource="user", resource_id=str(user.id),
        ip_address=_client_ip(request),
    ))
    return {"temp_password": temp_pwd, "message": "Contraseña reseteada — compartila de forma segura"}


@router.patch("/users/{user_id}/role")
@limiter.limit("20/minute")
async def assign_role(
    user_id: int,
    payload: AssignRoleRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await _check_not_protected_admin(current_user, user, db)
    _ensure_not_self(current_user, user_id)

    role: Role | None = None
    if payload.role_id is not None:
        role = await db.get(Role, payload.role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
        if role.name == "Superadmin" and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Solo el Super Admin puede asignar ese rol")
        _ensure_can_grant(current_user, _seed_permissions_for_role(role))
        # Sync is_superuser with Superadmin role
        user.is_superuser = role.name == "Superadmin"
    else:
        user.is_superuser = False

    role_id_anterior = user.role_id
    user.role_id = payload.role_id
    # Asignar un rol siembra el combo de permisos de ese rol — se puede
    # afinar después por usuario vía /users/{id}/permissions.
    user.permissions = _seed_permissions_for_role(role)
    db.add(user)
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.update_role", resource="user", resource_id=str(user.id),
        details={"role_id_antes": role_id_anterior, "role_id_despues": payload.role_id}, ip_address=_client_ip(request),
    ))
    return {"ok": True}


@router.patch("/users/{user_id}/permissions")
@limiter.limit("20/minute")
async def update_permissions(
    user_id: int,
    payload: UpdatePermissionsRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await _check_not_protected_admin(current_user, user, db)
    _ensure_not_self(current_user, user_id)

    unknown = [p for p in payload.permissions if p not in ALL_PERMISSIONS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Permisos desconocidos: {unknown}")
    _ensure_can_grant(current_user, payload.permissions)

    if user.role_id is not None:
        role = await db.get(Role, user.role_id)
        if role and role.view_only:
            no_view = [p for p in payload.permissions if not is_view_permission(p)]
            if no_view:
                raise HTTPException(
                    status_code=422,
                    detail=f"Este usuario tiene un rol de solo lectura — no se le pueden dar estos permisos: {no_view}",
                )

    permisos_antes = user.permissions or []
    user.permissions = payload.permissions
    db.add(user)
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.update_permissions", resource="user", resource_id=str(user.id),
        details={"permissions_antes": permisos_antes, "permissions_despues": payload.permissions}, ip_address=_client_ip(request),
    ))
    return {"permissions": user.permissions}


@router.patch("/users/{user_id}/activate")
@limiter.limit("20/minute")
async def toggle_active(
    user_id: int,
    payload: dict,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await _check_not_protected_admin(current_user, user, db)

    user.is_active = bool(payload.get("is_active", True))
    db.add(user)
    db.add(AuditLog(
        user_id=current_user.id,
        action="admin.user.activate" if user.is_active else "admin.user.deactivate",
        resource="user", resource_id=str(user.id), ip_address=_client_ip(request),
    ))
    return {"is_active": user.is_active}


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def list_audit_log(
    limit: int = 50,
    offset: int = 0,
    _: User = Depends(_require_admin_panel),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    result = await db.execute(
        select(AuditLog).order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
    )
    entries = result.scalars().all()

    user_ids = {e.user_id for e in entries if e.user_id}
    users_map: dict[int, User] = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in users_result.scalars().all():
            users_map[u.id] = u

    return [
        {
            "id": e.id,
            "user_id": e.user_id,
            "user_email": users_map[e.user_id].email if e.user_id and e.user_id in users_map else None,
            "action": e.action,
            "resource": e.resource,
            "resource_id": e.resource_id,
            "details": e.details,
            "ip_address": e.ip_address,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------
# Uso/costo de IA
# ---------------------------------------------------------------------------

@router.get("/ai-usage/summary")
async def ai_usage_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    _: User = Depends(_require_admin_panel),
    db: AsyncSession = Depends(get_db),
):
    date_to = date_to or date.today()
    date_from = date_from or (date_to - timedelta(days=30))
    day_col = func.date(AIUsageLog.created_at)
    filters = (day_col >= date_from, day_col <= date_to)

    total_cost, total_input, total_output = (await db.execute(
        select(
            func.coalesce(func.sum(AIUsageLog.estimated_cost_usd), 0),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
        ).where(*filters)
    )).one()

    by_provider = [
        {"provider": provider, "cost_usd": float(cost)}
        for provider, cost in (await db.execute(
            select(AIUsageLog.provider, func.sum(AIUsageLog.estimated_cost_usd))
            .where(*filters).group_by(AIUsageLog.provider)
        )).all()
    ]

    by_feature = [
        {"feature": feature, "cost_usd": float(cost)}
        for feature, cost in (await db.execute(
            select(AIUsageLog.feature, func.sum(AIUsageLog.estimated_cost_usd))
            .where(*filters).group_by(AIUsageLog.feature)
        )).all()
    ]

    user_rows = (await db.execute(
        select(AIUsageLog.user_id, func.sum(AIUsageLog.estimated_cost_usd))
        .where(*filters).group_by(AIUsageLog.user_id)
        .order_by(desc(func.sum(AIUsageLog.estimated_cost_usd))).limit(10)
    )).all()
    user_ids = {uid for uid, _ in user_rows if uid is not None}
    users_map: dict[int, User] = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in users_result.scalars().all():
            users_map[u.id] = u
    by_user = [
        {"user_id": uid, "user_email": users_map[uid].email if uid in users_map else None, "cost_usd": float(cost)}
        for uid, cost in user_rows
    ]

    daily = [
        {"date": str(d), "cost_usd": float(cost)}
        for d, cost in (await db.execute(
            select(day_col, func.sum(AIUsageLog.estimated_cost_usd))
            .where(*filters).group_by(day_col).order_by(day_col)
        )).all()
    ]

    return {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "total_cost_usd": float(total_cost),
        "total_input_tokens": int(total_input),
        "total_output_tokens": int(total_output),
        "by_provider": by_provider,
        "by_feature": by_feature,
        "by_user": by_user,
        "daily": daily,
    }
