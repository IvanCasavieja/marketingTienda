from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgendaExterna(Base):
    """El calendario de una persona, traído de Outlook o Google (0074).

    Pedido de Ivan (17/11/2026): cada uno importa su calendario y se ve en la
    fila "Mi agenda" del calendario de Core Tienda; solo lo ve su dueño. Una
    fila por persona: el link (cifrado, porque quien lo tiene ve el
    calendario) y los eventos de la última lectura (ver
    app/services/agenda_externa.py)."""

    __tablename__ = "agendas_externas"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    url_cifrada: Mapped[str] = mapped_column(Text, nullable=False)
    eventos: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    leida_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Lo que pasó la última vez que no se pudo leer (se muestran los eventos de antes).
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
