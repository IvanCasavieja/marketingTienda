from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class WatchlistShare(Base):
    """Con qué usuarios está compartida una Watchlist — el dueño sigue viviendo
    en Watchlist.user_id, esta tabla solo agrega colaboradores de solo lectura
    que también reciben las notificaciones de cambio de precio."""

    __tablename__ = "watchlist_shares"
    __table_args__ = (UniqueConstraint("watchlist_id", "user_id", name="uq_watchlist_shares_watchlist_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
