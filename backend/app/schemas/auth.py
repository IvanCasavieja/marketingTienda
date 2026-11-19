from pydantic import BaseModel, EmailStr, Field, field_validator


# Cuántos caracteres puede tener una contraseña nueva. Ivan, 19/11/2026: la
# plataforma es interna de Tienda Inglesa y pedir 12 caracteres con
# mayúscula, número y símbolo era demasiado ("de 6 a 20 caracteres está
# bárbara"). Solo se mira el largo.
CLAVE_MINIMO = 6
CLAVE_MAXIMO = 20


def _validate_password_strength(v: str) -> str:
    """Compartido entre los schemas que piden una contraseña nueva (registro,
    reset y change-password) y el alta desde el panel de usuarios: entre
    CLAVE_MINIMO y CLAVE_MAXIMO caracteres, de cualquier tipo."""
    if len(v) < CLAVE_MINIMO:
        raise ValueError(f"La contraseña tiene que tener al menos {CLAVE_MINIMO} caracteres.")
    if len(v) > CLAVE_MAXIMO:
        raise ValueError(f"La contraseña puede tener hasta {CLAVE_MAXIMO} caracteres.")
    return v


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
    # Los mundos a los que entra (claves de app/core/mundos.py). Siempre viene
    # al menos uno; para un superadmin vienen todos.
    mundos: list[str] = []
    must_change_password: bool = False
    # Cuenta externa (la agencia, 0069): el front la lleva directo a su trabajo.
    es_externo: bool = False
    empresa: str | None = None
    # Hasta dónde ve el calendario (0070, app/core/alcance.py): 'nada', '1m',
    # '2m', '12m' o 'todo'. `ventana` son las fechas (ISO) que ve hoy; null si
    # lo ve todo (o no lo ve: ahí lo dice el alcance).
    calendario_alcance: str = "todo"
    ventana: dict | None = None
    # Si los avisos de la campanita le llegan también por mail (0079).
    avisos_por_mail: bool = True

    class Config:
        from_attributes = True
