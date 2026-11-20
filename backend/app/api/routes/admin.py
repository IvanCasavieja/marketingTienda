"""Endpoints de administración — Super Admin y Admin (con restricciones entre sí).

Las cuentas externas (la agencia, 0069) se crean y se editan acá, con el
mismo panel: `es_externo` y el nombre de la empresa. Un externo nunca recibe
permisos de gestión ni de admin, ni un rol: el servidor lo rechaza aunque se
pida (`_ensure_externo_puede_tener`), y la base también (ver la 0069).

La empresa se elige de las agencias que ya existen (GET /agencias) o se
agrega una nueva, y se guarda como ya está escrita si es la misma
(19/11/2026, ver app/services/agencias.py).
"""
import secrets
import string
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from app.schemas.auth import _validate_password_strength
from sqlalchemy import select, desc, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, client_ip as _client_ip
from app.core.security import hash_password
from app.core.rate_limit import limiter
from app.models.ai_usage_log import AIUsageLog
from app.models.audit_log import AuditLog
from app.models.cenefa_job import CenefaJob
from app.models.calendario import CalendarioTarea
from app.models.local_asignacion import LocalAsignacion
from app.models.role import Role, ALL_PERMISSIONS, is_view_permission
from app.core import alcance, externos
from app.core.mundos import MUNDO_POR_DEFECTO, MUNDOS, mundos_de, mundos_iniciales, mundos_que_no_puede_dar
from app.core.tableros import tablero_de
from app.models.user import User
from app.services import agencias

router = APIRouter(prefix="/admin", tags=["admin"])



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


def _ensure_externo_puede_tener(target: User, permissions: list[str]) -> None:
    """Una cuenta externa (la agencia) tiene como mucho los permisos de
    PERMISOS_DE_EXTERNOS: nada de gestión (tareas, edición del calendario,
    Retail Media) ni de admin. Lo pida quien lo pida, superadmin incluido."""
    if not externos.es_externo(target):
        return
    de_mas = externos.permisos_no_permitidos(permissions)
    if de_mas:
        raise HTTPException(
            status_code=422,
            detail=f"Una cuenta externa solo puede ver el calendario: no se le pueden dar {de_mas}",
        )


def _validar_mundos_pedidos(current_user: User, antes, pedidos: list[str]) -> list[str]:
    """Los mundos pedidos, en el orden del catálogo, con las mismas reglas que
    PATCH /users/{id}/mundos: que existan, al menos uno, y nadie da un mundo al
    que no entra."""
    desconocidos = [m for m in pedidos if m not in MUNDOS]
    if desconocidos:
        raise HTTPException(status_code=422, detail=f"Mundos desconocidos: {desconocidos}")
    if not pedidos:
        raise HTTPException(status_code=422, detail="Tiene que quedar al menos un mundo.")
    ajenos = mundos_que_no_puede_dar(current_user, antes, pedidos)
    if ajenos:
        raise HTTPException(
            status_code=403,
            detail="No podés dar acceso a un mundo al que vos no entrás: " + ", ".join(MUNDOS[m] for m in ajenos),
        )
    return [m for m in MUNDOS if m in set(pedidos)]


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
    await db.delete(role)
    return None


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role_id: int | None = None
    # Cuenta externa (la agencia): sin rol, solo ve el calendario, con la
    # vista limitada de app/core/externos.py. La empresa es obligatoria.
    es_externo: bool = False
    empresa: str | None = Field(None, max_length=120)
    # Solo para una cuenta externa: los mundos donde trabaja (por defecto
    # Tienda Inglesa). A una interna se le dan según su rol, como siempre.
    mundos: list[str] | None = None
    # Hasta dónde ve el calendario (0070). Sin decirlo: una externa, "No lo
    # ve"; una del equipo, "Todo" (ver app/core/alcance.py).
    calendario_alcance: str | None = None


class UpdateAlcanceRequest(BaseModel):
    calendario_alcance: str


class UpdateExternoRequest(BaseModel):
    es_externo: bool
    empresa: str | None = Field(None, max_length=120)


class AssignRoleRequest(BaseModel):
    role_id: int | None


class UpdatePermissionsRequest(BaseModel):
    permissions: list[str]


class UpdateMundosRequest(BaseModel):
    mundos: list[str]


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

    # Una sola query agregada para todos los usuarios (no N+1) -- ix_audit_logs_user_id_action
    # (migración 0039) la cubre.
    login_stats_result = await db.execute(
        select(AuditLog.user_id, func.count(AuditLog.id), func.max(AuditLog.created_at))
        .where(AuditLog.action == "user.login")
        .group_by(AuditLog.user_id)
    )
    login_stats = {
        user_id: {"login_count": count, "last_login_at": last_login}
        for user_id, count, last_login in login_stats_result.all()
    }

    # Los logins de sucursal conviven en la misma tabla que las personas, pero
    # el panel los muestra en pestañas aparte: sin esto no hay forma de
    # distinguirlos, porque un login de sucursal es un User igual que los demás.
    sucursales: dict[int, list[str]] = {}
    tipo_sucursal: dict[int, str] = {}
    for user_id, nombre, tipo in (await db.execute(
        select(LocalAsignacion.user_id, LocalAsignacion.local_nombre, LocalAsignacion.tipo)
    )).all():
        sucursales.setdefault(user_id, []).append(nombre)
        tipo_sucursal[user_id] = tipo

    return [
        {
            "id":           u.id,
            "email":        u.email,
            "full_name":    u.full_name,
            "role_id":      u.role_id,
            "role_name":    roles_map[u.role_id].name if u.role_id and u.role_id in roles_map else None,
            "permissions":  u.permissions or [],
            "mundos":       mundos_de(u),
            "is_active":    u.is_active,
            "is_superuser": u.is_superuser,
            "es_externo":   bool(u.es_externo),
            "empresa":      u.empresa,
            "calendario_alcance": alcance.alcance_de(u),
            "created_at":   u.created_at.isoformat() if u.created_at else None,
            "sucursales":   sorted(sucursales.get(u.id, [])),
            "sucursal_tipo": tipo_sucursal.get(u.id),
            "login_count":  login_stats.get(u.id, {}).get("login_count", 0),
            "last_login_at": (
                login_stats[u.id]["last_login_at"].isoformat()
                if u.id in login_stats and login_stats[u.id]["last_login_at"] else None
            ),
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

    if payload.es_externo:
        return await _crear_externo(payload, request, current_user, db)

    role: Role | None = None
    if payload.role_id is not None:
        role = await db.get(Role, payload.role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
        if role.name == "Superadmin" and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Solo el Super Admin puede asignar ese rol")
    # Igual que assign_role: nadie crea una cuenta con permisos que no tiene.
    # Sin esto, un gestor de usuarios se creaba una cuenta "títere" con el rol
    # Admin y entraba con más permisos que los propios (auditoría 15/11/2026).
    _ensure_can_grant(current_user, _seed_permissions_for_role(role))
    try:
        _validate_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role_id=payload.role_id,
        permissions=_seed_permissions_for_role(role),
        # Arranca en Tienda Inglesa (y en Redexpres, si el rol trae permisos de
        # Redexpres); los demás mundos se tildan después, uno por uno.
        mundos=mundos_iniciales(_seed_permissions_for_role(role)),
        is_superuser=False,
        calendario_alcance=_alcance_pedido(current_user, payload.calendario_alcance, es_externo=False),
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


async def _crear_externo(
    payload: CreateUserRequest, request: Request, current_user: User, db: AsyncSession,
) -> dict:
    """Una cuenta externa: sin rol, con solo ver el calendario (la vista
    limitada la ponen las rutas) y en los mundos pedidos. Como cualquier cuenta
    nueva, tiene que elegir su contraseña al entrar la primera vez."""
    if payload.role_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Una cuenta externa no lleva rol: solo ve el calendario de su mes y sus tareas",
        )
    # Si es una agencia que ya existe, con el nombre que ya tiene: «diseñadores »
    # es Diseñadores (19/11/2026).
    empresa = await agencias.como_ya_esta(db, payload.empresa)
    if not empresa:
        raise HTTPException(status_code=422, detail="Elegí de qué agencia es")
    permisos = sorted(externos.PERMISOS_DE_EXTERNOS)
    # Igual que con cualquier cuenta: nadie da lo que no tiene.
    _ensure_can_grant(current_user, permisos)
    mundos = _validar_mundos_pedidos(current_user, [], payload.mundos or [MUNDO_POR_DEFECTO])
    try:
        _validate_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role_id=None,
        permissions=permisos,
        mundos=mundos,
        is_superuser=False,
        es_externo=True,
        empresa=empresa,
        calendario_alcance=_alcance_pedido(current_user, payload.calendario_alcance, es_externo=True),
        must_change_password=True,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.create", resource="user", resource_id=str(user.id),
        details={"email": user.email, "externo": True, "empresa": empresa, "mundos": mundos},
        ip_address=_client_ip(request),
    ))
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "es_externo": True, "empresa": empresa}


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
        # Un login de sucursal no tiene mail: entra con el nombre del local.
        es_sucursal = (await db.execute(
            select(LocalAsignacion.id).where(LocalAsignacion.user_id == user.id).limit(1)
        )).scalar_one_or_none()
        if es_sucursal is not None:
            raise HTTPException(
                status_code=422,
                detail="Una sucursal entra con el nombre del local, no con un mail: ese usuario no se cambia desde acá",
            )
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
    if externos.es_externo(user) and payload.role_id is not None:
        # Un rol siembra permisos de gestión (Admin, Usuario...): a una cuenta
        # externa no. Para darle más, primero deja de ser externa.
        raise HTTPException(
            status_code=422,
            detail="Una cuenta externa no lleva rol: solo ve el calendario de su mes y sus tareas",
        )
    if externos.es_externo(user):
        # "Sin rol" a una externa: ya no tiene. No se le tocan los permisos
        # (sembrar los de "ningún rol" le sacaría ver el calendario).
        return {"ok": True}

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
    _ensure_externo_puede_tener(user, payload.permissions)
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


@router.patch("/users/{user_id}/externo")
@limiter.limit("20/minute")
async def update_externo(
    user_id: int,
    payload: UpdateExternoRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    """Marcar (o desmarcar) una cuenta como externa, o cambiarle la empresa.

    Al pasar a externa pierde el rol y todo permiso que no sea de los suyos
    (queda viendo el calendario, con la vista limitada): es la forma de que
    alguien que pasó a trabajar desde la agencia no siga viendo lo interno.
    No aplica a uno mismo, a un admin protegido ni a un login de sucursal.
    Desmarcarla no le da nada: los permisos se dan después, uno por uno."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await _check_not_protected_admin(current_user, user, db)
    _ensure_not_self(current_user, user_id)

    antes = {"es_externo": bool(user.es_externo), "empresa": user.empresa, "permissions": list(user.permissions or [])}
    ya_era_externa = bool(user.es_externo)
    empresa_vieja = externos.limpiar_empresa(user.empresa)
    tarjetas_pasadas = 0
    plantillas_pasadas = 0
    if payload.es_externo:
        # Como ya está escrita si es una agencia que existe (19/11/2026). Sin
        # contar esta misma cuenta: si es la única de su agencia, se le puede
        # corregir cómo se escribe.
        empresa = await agencias.como_ya_esta(db, payload.empresa, menos=user.id)
        if not empresa:
            raise HTTPException(status_code=422, detail="Elegí de qué agencia es")
        if user.is_superuser:
            raise HTTPException(status_code=422, detail="El superadmin no puede ser una cuenta externa")
        es_sucursal = (await db.execute(
            select(LocalAsignacion.id).where(LocalAsignacion.user_id == user.id).limit(1)
        )).scalar_one_or_none()
        if es_sucursal is not None:
            raise HTTPException(status_code=422, detail="Un login de sucursal no puede ser una cuenta externa")
        if (ya_era_externa and empresa_vieja and not externos.misma_empresa(empresa_vieja, empresa)
                and not tablero_de(empresa_vieja)):
            # Le corrigieron el nombre a la empresa ("Publisis" -> "Publicis").
            # Las tarjetas son de la AGENCIA, por nombre: si era la última
            # cuenta con el nombre viejo, se pasan al nuevo; si no, el
            # tablero de la agencia quedaba vacío y nadie las podía entregar.
            # Si quedan otras cuentas con el nombre viejo, las tarjetas siguen
            # siendo de ellas: esta cuenta es la que cambió de agencia.
            # Si la vieja es uno de los tres tableros (Publicis, Another
            # Monday, Diseñadores) no es un nombre mal escrito: la cuenta se
            # cambió de agencia y lo de ese tablero se queda ahí, aunque se
            # quede sin cuentas. Antes, pasar a la única cuenta de Diseñadores
            # a Publicis (porque se eligió mal) se llevaba todas las tarjetas
            # y plantillas de Diseñadores, y volverla atrás se traía también
            # las de Publicis (revisión del 19/11/2026).
            clave_vieja = externos.clave_de_empresa(empresa_vieja)
            quedan = (await db.execute(
                select(func.count()).select_from(User).where(
                    User.id != user.id, User.es_externo.is_(True),
                    externos.empresa_en_sql(User.empresa) == clave_vieja,
                )
            )).scalar_one()
            if not quedan:
                tarjetas_pasadas = (await db.execute(
                    update(CalendarioTarea)
                    .where(
                        CalendarioTarea.para == "agencia",
                        externos.empresa_en_sql(CalendarioTarea.agencia) == clave_vieja,
                    )
                    .values(agencia=empresa)
                    .execution_options(synchronize_session=False)
                )).rowcount or 0
                plantillas_pasadas = await _pasar_plantillas_de_agencia(db, empresa_vieja, empresa)
        user.es_externo = True
        user.empresa = empresa
        user.role_id = None
        if not ya_era_externa:
            # Una cuenta externa arranca sin ver el calendario (0070): si
            # después tiene que verlo, se le da a ella puntualmente. A una
            # que ya era externa no se le toca lo que ya le habilitaron:
            # corregirle la empresa le cerraba el calendario sin aviso.
            user.calendario_alcance = alcance.POR_DEFECTO_EXTERNO
        user.permissions = [p for p in (user.permissions or []) if p in externos.PERMISOS_DE_EXTERNOS]
    else:
        user.es_externo = False
        user.empresa = None
    db.add(user)
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.update_externo", resource="user", resource_id=str(user.id),
        details={"antes": antes, "es_externo": user.es_externo, "empresa": user.empresa,
                 "permissions": list(user.permissions or []), "tarjetas_pasadas": tarjetas_pasadas,
                 "plantillas_pasadas": plantillas_pasadas},
        ip_address=_client_ip(request),
    ))
    return {
        "es_externo": user.es_externo, "empresa": user.empresa, "permissions": user.permissions or [],
        # Cuántas tarjetas y plantillas pasaron al nombre nuevo de la agencia
        # (0 si no se le corrigió el nombre a ninguna): el panel lo avisa.
        "tarjetas_pasadas": tarjetas_pasadas, "plantillas_pasadas": plantillas_pasadas,
    }


@router.get("/mundos")
async def list_mundos(_: User = Depends(_require_admin_panel)):
    """El catálogo de mundos, para tildarlos por usuario."""
    return [{"key": clave, "nombre": nombre} for clave, nombre in MUNDOS.items()]


@router.get("/agencias")
async def list_agencias(
    _: User = Depends(_require_admin_panel),
    db: AsyncSession = Depends(get_db),
):
    """Las agencias que ya existen, para elegir la de una cuenta externa
    (19/11/2026, Ivan: "¿no debería ser una selección?"): los tres tableros
    (Publicis, Another Monday, Diseñadores) y las empresas de las cuentas
    externas, cada una una sola vez. Una nueva se agrega escribiéndola en el
    panel, que solo usa quien administra."""
    return await agencias.existentes(db)


async def _pasar_plantillas_de_agencia(db: AsyncSession, vieja: str, nueva: str) -> int:
    """Al corregirle el nombre a una agencia ("Publisis" -> "Publicis"), las
    plantillas que la nombran pasan al nombre nuevo, como sus tarjetas. Si
    no, cada vez que se aplicaba la plantilla nacía una tarjeta para el
    nombre viejo, que la agencia no veía ni le avisaba (revisión del
    16/11/2026). Devuelve cuántas plantillas cambió.

    Las tareas de una plantilla son una lista en JSONB: se asigna una lista
    nueva (si no, SQLAlchemy no ve el cambio y no lo guarda)."""
    from app.api.routes.calendario import _nueva_revision
    from app.models.calendario import CalendarioPlantilla

    mundos: set[str] = set()
    n = 0
    for p in (await db.execute(select(CalendarioPlantilla).with_for_update())).scalars():
        tareas = [dict(t) for t in (p.tareas or [])]
        cambio = False
        for t in tareas:
            if t.get("para") == "agencia" and externos.misma_empresa(t.get("agencia"), vieja):
                t["agencia"] = nueva
                cambio = True
        if cambio:
            p.tareas = tareas
            mundos.add(p.mundo)
            n += 1
    # Quien tiene el calendario abierto ve la plantilla con el nombre nuevo.
    for mundo in sorted(mundos):
        await _nueva_revision(db, mundo)
    return n


def _alcance_pedido(quien_da: User, pedido: str | None, *, es_externo: bool) -> str:
    """El alcance con el que se crea (o al que se cambia) una cuenta: el
    pedido, o el de su tipo si no se pidió ninguno. Nadie da más calendario
    del que ve: como con los permisos y los mundos.

    Sin pedido, la cuenta nace con lo menos entre el de su tipo y lo que ve
    quien la crea: el panel no manda el alcance al crear una cuenta del
    equipo, y un Admin con el calendario limitado recibía «No podés dar más
    calendario del que ves vos» y no podía crear ninguna (revisión del
    16/11/2026). El 403 queda para un alcance pedido a propósito."""
    valor = pedido or alcance.por_defecto(es_externo)
    if valor not in alcance.ALCANCES:
        raise HTTPException(status_code=422, detail="Ese alcance del calendario no existe")
    if not pedido and not quien_da.is_superuser:
        valor = min(valor, alcance.alcance_de(quien_da), key=alcance.ALCANCES.index)
    if not quien_da.is_superuser and alcance.ALCANCES.index(valor) > alcance.ALCANCES.index(alcance.alcance_de(quien_da)):
        raise HTTPException(status_code=403, detail="No podés dar más calendario del que ves vos")
    return valor


@router.patch("/users/{user_id}/alcance")
@limiter.limit("20/minute")
async def update_alcance(
    user_id: int,
    payload: UpdateAlcanceRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    """Hasta dónde ve el calendario una persona (0070): No lo ve / 1 mes /
    2 meses / 12 meses / Todo. Pedido de Ivan (16/11/2026): el calendario lo
    ve mucha gente y lo quiere empezar a cerrar; y a la agencia, darle de a
    poco (al dueño, por ejemplo). El tablero de tarjetas lo ve siempre: es su
    trabajo. Uno no se lo cambia a sí mismo."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_not_self(current_user, user_id)
    await _check_not_protected_admin(current_user, user, db)
    antes = alcance.alcance_de(user)
    user.calendario_alcance = _alcance_pedido(current_user, payload.calendario_alcance, es_externo=bool(user.es_externo))
    db.add(user)
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.update_alcance", resource="user", resource_id=str(user.id),
        details={"antes": antes, "despues": user.calendario_alcance}, ip_address=_client_ip(request),
    ))
    return {"calendario_alcance": user.calendario_alcance}


@router.patch("/users/{user_id}/mundos")
@limiter.limit("20/minute")
async def update_mundos(
    user_id: int,
    payload: UpdateMundosRequest,
    request: Request,
    current_user: User = Depends(_require_user_management),
    db: AsyncSession = Depends(get_db),
):
    """A qué mundos entra una persona. A diferencia de los permisos, uno se
    los puede cambiar a sí mismo, pero igual que con los permisos nadie da
    acceso a un mundo al que él mismo no entra: el mundo es lo único que
    separa los datos de un negocio de los de otro. Tiene que quedar al menos
    uno: sin mundo no se puede entrar a la plataforma (para eso se desactiva
    la cuenta)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.id != current_user.id:
        await _check_not_protected_admin(current_user, user, db)

    desconocidos = [m for m in payload.mundos if m not in MUNDOS]
    if desconocidos:
        raise HTTPException(status_code=422, detail=f"Mundos desconocidos: {desconocidos}")
    if not payload.mundos:
        raise HTTPException(
            status_code=422,
            detail="Tiene que quedar al menos un mundo. Para sacarle el acceso a alguien, desactivá su cuenta.",
        )

    antes = list(user.mundos or [])
    ajenos = mundos_que_no_puede_dar(current_user, antes, payload.mundos)
    if ajenos:
        raise HTTPException(
            status_code=403,
            detail="No podés dar acceso a un mundo al que vos no entrás: " + ", ".join(MUNDOS[m] for m in ajenos),
        )
    user.mundos = [m for m in MUNDOS if m in set(payload.mundos)]
    db.add(user)
    db.add(AuditLog(
        user_id=current_user.id, action="admin.user.update_mundos", resource="user", resource_id=str(user.id),
        details={"mundos_antes": antes, "mundos_despues": user.mundos}, ip_address=_client_ip(request),
    ))
    return {"mundos": user.mundos}


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


@router.get("/users/{user_id}/stats")
async def user_stats(
    user_id: int,
    _: User = Depends(_require_admin_panel),
    db: AsyncSession = Depends(get_db),
):
    """Resumen compacto de actividad de un usuario -- alimenta el header del
    modal de actividad en el frontend. El historial completo (línea por
    línea) se pide aparte a /audit-log y /ai-usage/summary, ambos ya
    filtrables por user_id."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    login_count, last_login_at = (await db.execute(
        select(func.count(AuditLog.id), func.max(AuditLog.created_at))
        .where(AuditLog.user_id == user_id, AuditLog.action == "user.login")
    )).one()

    last_login_ip = (await db.execute(
        select(AuditLog.ip_address)
        .where(AuditLog.user_id == user_id, AuditLog.action == "user.login")
        .order_by(desc(AuditLog.created_at)).limit(1)
    )).scalar_one_or_none()

    cenefas_generated_count = (await db.execute(
        select(func.count(CenefaJob.id)).where(CenefaJob.created_by == user_id)
    )).scalar_one()

    thirty_days_ago = date.today() - timedelta(days=30)
    ai_cost_last_30d = (await db.execute(
        select(func.coalesce(func.sum(AIUsageLog.estimated_cost_usd), 0))
        .where(AIUsageLog.user_id == user_id, func.date(AIUsageLog.created_at) >= thirty_days_ago)
    )).scalar_one()

    return {
        "login_count": login_count,
        "last_login_at": last_login_at.isoformat() if last_login_at else None,
        "last_login_ip": last_login_ip,
        "cenefas_generated_count": cenefas_generated_count,
        "ai_cost_last_30d_usd": float(ai_cost_last_30d),
        "account_created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def list_audit_log(
    limit: int = 50,
    offset: int = 0,
    user_id: int | None = None,
    _: User = Depends(_require_admin_panel),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    query = select(AuditLog).order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    result = await db.execute(query)
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
    user_id: int | None = None,
    _: User = Depends(_require_admin_panel),
    db: AsyncSession = Depends(get_db),
):
    date_to = date_to or date.today()
    date_from = date_from or (date_to - timedelta(days=30))
    day_col = func.date(AIUsageLog.created_at)
    filters = (day_col >= date_from, day_col <= date_to)
    if user_id is not None:
        # by_user de por sí da como mucho una fila (la de este usuario) cuando
        # se filtra acá -- no hace falta ninguna rama especial, el resto de
        # las subqueries (totales, by_provider, by_feature, daily) ya comparten
        # este mismo tuple `filters`.
        filters = (*filters, AIUsageLog.user_id == user_id)

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
