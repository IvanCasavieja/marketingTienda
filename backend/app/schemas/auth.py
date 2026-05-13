from pydantic import BaseModel, EmailStr, field_validator
import re


class UserRegister(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    join_code: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain a digit")
        if not re.search(r"[^a-zA-Z0-9]", v):
            raise ValueError("Password must contain a special character")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    join_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class JoinTeamRequest(BaseModel):
    join_code: str


class JoinTeamResponse(BaseModel):
    team_name: str
    group_name: str


class TeamGroupCreateRequest(BaseModel):
    team_name: str
    team_slug: str
    group_name: str


class TeamGroupCreateResponse(BaseModel):
    team_name: str
    group_name: str
    join_code: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    team_group_id: int | None = None
    team_name: str | None = None
    group_name: str | None = None
    join_code: str | None = None
    is_active: bool
    is_superuser: bool

    class Config:
        from_attributes = True
