import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import get_db

from app.core.config import settings
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token, decrypt_token, encrypt_token
from app.core.deps import get_current_user
from app.models.team import Team, TeamGroup
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshRequest,
    UserResponse,
    JoinTeamRequest,
    JoinTeamResponse,
    TeamGroupCreateRequest,
    TeamGroupCreateResponse,
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
    team_group = user.team_group
    role = user.role
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        team_group_id=user.team_group_id,
        team_name=team_group.name if team_group else None,
        team_type=team_group.team_type if team_group else None,
        join_code=decrypt_token(team_group.join_code) if team_group else None,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        role_id=role.id if role else None,
        role_name=role.name if role else None,
        permissions=role.permissions if role else [],
    )


async def _get_group_by_join_code(db: AsyncSession, join_code: str) -> TeamGroup:
    # Join codes are Fernet-encrypted (random IV) so we can't query by value.
    # We fetch only the join_code + id columns to minimise data transfer.
    result = await db.execute(
        select(TeamGroup.id, TeamGroup.team_id, TeamGroup.name, TeamGroup.join_code)
    )
    for row in result.all():
        try:
            if decrypt_token(row.join_code) == join_code:
                # Re-fetch the full object (single row by PK — cheap)
                full = await db.get(TeamGroup, row.id)
                if full:
                    return full
        except Exception:
            continue
    raise HTTPException(status_code=400, detail="Invalid join code")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    team_group = await _get_group_by_join_code(db, payload.join_code) if payload.join_code else None

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        team_group_id=team_group.id if team_group else None,
    )
    db.add(user)
    await db.flush()
    if team_group:
        user.team_group = team_group

    db.add(AuditLog(user_id=user.id, action="user.register", ip_address=_client_ip(request)))
    return _user_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if payload.join_code and not user.team_group_id:
        team_group = await _get_group_by_join_code(db, payload.join_code)
        user.team_group_id = team_group.id

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
    from app.models.role import Role as RoleModel
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.team_group).selectinload(TeamGroup.team),
            selectinload(User.role),
        )
        .where(User.id == current_user.id)
    )
    return _user_response(result.scalar_one())


@router.post("/join-team", response_model=JoinTeamResponse)
async def join_team(
    payload: JoinTeamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    team_group = await _get_group_by_join_code(db, payload.join_code)
    current_user.team_group_id = team_group.id
    db.add(AuditLog(user_id=current_user.id, action="user.join_team"))
    return JoinTeamResponse(team_name=team_group.name)


@router.post("/team-groups", response_model=TeamGroupCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_team_group(
    payload: TeamGroupCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only admins can create team groups")

    result = await db.execute(select(Team).where(Team.slug == payload.team_slug))
    team = result.scalar_one_or_none()
    if not team:
        team = Team(name=payload.team_name, slug=payload.team_slug)
        db.add(team)
        await db.flush()
    else:
        team.name = payload.team_name

    result = await db.execute(
        select(TeamGroup)
        .options(selectinload(TeamGroup.team))
        .where(TeamGroup.team_id == team.id, TeamGroup.name == payload.group_name)
    )
    team_group = result.scalar_one_or_none()
    if team_group:
        join_code = decrypt_token(team_group.join_code)
    else:
        join_code = secrets.token_urlsafe(16)
        team_group = TeamGroup(team_id=team.id, name=payload.group_name, join_code=encrypt_token(join_code), team_type=payload.team_type)
        db.add(team_group)

    db.add(AuditLog(user_id=current_user.id, action="team_group.create", resource="team_group"))
    return TeamGroupCreateResponse(team_name=team_group.name, join_code=join_code)


@router.get("/team-members")
async def list_team_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Not part of a team")

    result = await db.execute(
        select(User).where(User.team_group_id == current_user.team_group_id, User.is_active == True)
    )
    members = result.scalars().all()
    return [
        {
            "id": m.id,
            "email": m.email,
            "full_name": m.full_name,
            "is_superuser": m.is_superuser,
        }
        for m in members
    ]


@router.delete("/team-members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only admins can remove members")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    result = await db.execute(
        select(User).where(User.id == user_id, User.team_group_id == current_user.team_group_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found in your team")

    member.team_group_id = None
    db.add(AuditLog(user_id=current_user.id, action="team.remove_member", resource=str(user_id)))


@router.patch("/team-group/type", status_code=200)
async def update_team_group_type(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only admins can change team type")
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Not part of a team")
    team_type = payload.get("team_type")
    if team_type not in ("medios", "marca", "promo"):
        raise HTTPException(status_code=400, detail="team_type must be medios, marca or promo")

    result = await db.execute(select(TeamGroup).where(TeamGroup.id == current_user.team_group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Team group not found")
    group.team_type = team_type
    db.add(AuditLog(user_id=current_user.id, action="team_group.update_type", resource=team_type))
    return {"team_type": team_type}
