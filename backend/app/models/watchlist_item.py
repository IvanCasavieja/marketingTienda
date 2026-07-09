from datetime import datetime

from sqlalchemy import String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False)
    tienda: Mapped[str] = mapped_column(String(50), nullable=False)
    # None solo para DIMM/Stienda — esas dos cadenas no traen sku en el scraper
    # (ver _buscar_dimm_stienda en live_search.py); el chequeo diario cae a
    # matchear por nombre exacto para esos casos.
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    # Ta-Ta/ElDorado/GDU devuelven una fila por (producto × sucursal) con precios
    # distintos por sucursal — sin este dato, el chequeo diario no puede saber
    # cuál de las ~15-17 sucursales con el mismo SKU es la que el usuario siguió
    # (ver chequear_item en watchlist_service.py). None en el resto de las cadenas,
    # que no tienen concepto de sucursal (single listing).
    sucursal_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sucursal_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Término de búsqueda original — necesario para poder re-invocar el mismo
    # adapter de la cadena y volver a encontrar este producto en el chequeo diario.
    termino_busqueda: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    precio_actual: Mapped[float] = mapped_column(Float, nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False)
    ultimo_chequeo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
