import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from app.core.config import settings

# 10 rondas de bcrypt (25/11/2026; antes, las 12 por defecto). Ivan: "está
# como lenta la plataforma… cuando creo un usuario no me muestra que esté
# cargando y demora". En el servidor de Render (una décima de procesador)
# cifrar o verificar con 12 tardaba ~2,5 s y, como corría en el mismo hilo
# que atiende todo, frenaba a todos mientras alguien entraba. Con 10 es
# 4 veces menos trabajo y sigue siendo lo recomendado (OWASP: 10 o más). Las
# contraseñas guardadas con 12 se siguen aceptando y se pasan a 10 la
# próxima vez que esa persona entra (ver login: necesita_actualizar).
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=10)
fernet = Fernet(settings.ENCRYPTION_KEY.encode())

_JWT_SECRET = settings.JWT_SECRET_KEY or settings.APP_SECRET_KEY


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def necesita_actualizar(hashed: str) -> bool:
    """Si la contraseña guardada usa otra cantidad de rondas que la de hoy."""
    return pwd_context.needs_update(hashed)


async def hash_password_async(password: str) -> str:
    """Igual que hash_password, pero en otro hilo: mientras cifra, el
    servidor sigue atendiendo los demás pedidos."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    """Igual que verify_password, en otro hilo (ver hash_password_async)."""
    return await asyncio.to_thread(verify_password, plain, hashed)


def create_access_token(subject: Any, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode(
        {"sub": str(subject), "iat": now, "exp": expire, "type": "access"},
        _JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(subject: Any) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(subject), "iat": now, "exp": expire, "type": "refresh"},
        _JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return {}


def encrypt_token(raw: str) -> str:
    """AES-256 encrypt a platform OAuth token before storing in DB."""
    return fernet.encrypt(raw.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored platform OAuth token."""
    return fernet.decrypt(encrypted.encode()).decode()
