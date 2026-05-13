import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import get_db

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


def _user_response(user: User) -> UserResponse:
    team_group = user.team_group
    team = team_group.team if team_group else None
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        team_group_id=user.team_group_id,
        team_name=team.name if team else None,
        group_name=team_group.name if team_group else None,
        join_code=decrypt_token(team_group.join_code) if team_group else None,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
    )


async def _get_group_by_join_code(db: AsyncSession, join_code: str) -> TeamGroup:
    result = await db.execute(select(TeamGroup).options(selectinload(TeamGroup.team)))
    for group in result.scalars().all():
        try:
            if decrypt_token(group.join_code) == join_code:
                return group
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

    db.add(AuditLog(user_id=user.id, action="user.register", ip_address=request.client.host))
    return _user_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if payload.join_code and not user.team_group_id:
        team_group = await _get_group_by_join_code(db, payload.join_code)
        user.team_group_id = team_group.id

    db.add(AuditLog(user_id=user.id, action="user.login", ip_address=request.client.host))

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    data = decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == int(data["sub"]), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .options(selectinload(User.team_group).selectinload(TeamGroup.team))
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
    return JoinTeamResponse(team_name=team_group.team.name, group_name=team_group.name)


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
        team_group = TeamGroup(team_id=team.id, name=payload.group_name, join_code=encrypt_token(join_code))
        db.add(team_group)

    db.add(AuditLog(user_id=current_user.id, action="team_group.create", resource="team_group"))
    return TeamGroupCreateResponse(team_name=team.name, group_name=payload.group_name, join_code=join_code)
