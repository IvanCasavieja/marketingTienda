from datetime import datetime

from sqlalchemy import Float, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class WatchlistPrecioHistorial(Base):
    __tablename__ = "watchlist_precio_historial"

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_item_id: Mapped[int] = mapped_column(
        ForeignKey("watchlist_items.id", ondelete="CASCADE"), nullable=False
    )
    precio: Mapped[float] = mapped_column(Float, nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
