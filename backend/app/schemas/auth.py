from pydantic import BaseModel, EmailStr, Field, field_validator
import re


def _validate_password_strength(v: str) -> str:
    """Compartido entre los 3 schemas que piden una contraseña nueva
    (registro, reset y change-password) — junta TODAS las reglas que
    faltan en un solo mensaje en vez de cortar en la primera, para que el
    usuario no tenga que ir a los tumbos probando de a un requisito."""
    faltantes = []
    if len(v) < 12:
        faltantes.append("al menos 12 caracteres")
    if not re.search(r"[A-Z]", v):
        faltantes.append("una letra mayúscula")
    if not re.search(r"[0-9]", v):
        faltantes.append("un número")
    if not re.search(r"[^a-zA-Z0-9]", v):
        faltantes.append("un símbolo")
    if faltantes:
        raise ValueError("La contraseña debe tener " + ", ".join(faltantes) + ".")
    return v


class UserRegister(BaseModel):
    email: EmailStr
    full_name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserLogin(BaseModel):
    # No es EmailStr a propósito: los usuarios de sucursal de Redexpres
    # loguean con el nombre del local como "email" (ver create_sucursal_users.py),
    # no con una casilla real. El login de personal real sigue usando su email
    # normal, que sigue siendo un string válido con este tipo más laxo.
    email: str = Field(min_length=1)
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    role_id: int | None = None
    role_name: str | None = None
    permissions: list[str] = []
    assigned_locales: list[str] = []
    must_change_password: bool = False

    class Config:
        from_attributes = True
