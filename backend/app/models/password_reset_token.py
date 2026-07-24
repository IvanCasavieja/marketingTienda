from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PasswordResetToken(Base):
    """Token de un solo uso para /auth/forgot-password y /auth/reset-password.

    Vive en Postgres (no Redis) a propósito: es la única parte de auth que
    necesitaba guardado temporal con expiración, y el resto del proyecto ya
    trata a Redis como opcional (ver auto_sync.py/watchlist_service.py) —
    no vale la pena el servicio externo extra solo por esto.

    token es la propia primary key: es único e inmutable por construcción
    (secrets.token_urlsafe), así que no hace falta un id surrogate aparte."""

    __tablename__ = "password_reset_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Respalda el DELETE de limpieza de vencidos en cada /forgot-password
        # (ver auth.py) — sin esto, esa query hace full scan a medida que
        # crece la tabla.
        Index("ix_password_reset_tokens_expires_at", "expires_at"),
    )
