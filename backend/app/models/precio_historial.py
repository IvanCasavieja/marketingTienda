from sqlalchemy import String, Float, Date, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date
from app.core.database import Base


class PrecioHistorial(Base):
    __tablename__ = "precio_historial"

    id:           Mapped[int]           = mapped_column(primary_key=True)
    tienda:       Mapped[str]           = mapped_column(String(100), nullable=False)
    url:          Mapped[str]           = mapped_column(String(1000), nullable=False)
    nombre:       Mapped[str | None]    = mapped_column(String(500))
    precio:       Mapped[float | None]  = mapped_column(Float)
    precio_lista: Mapped[float | None]  = mapped_column(Float)
    sku:             Mapped[str | None]    = mapped_column(String(100))
    barcode:         Mapped[str | None]    = mapped_column(String(50))
    marca:           Mapped[str | None]    = mapped_column(String(200))
    categoria:       Mapped[str | None]    = mapped_column(String(500))
    sucursal_id:     Mapped[str | None]    = mapped_column(String(50))
    sucursal_nombre: Mapped[str | None]    = mapped_column(String(200))
    fecha_scan:      Mapped[date]          = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("url", "fecha_scan", name="uq_historial_url_fecha"),
        Index("ix_historial_fecha_scan", "fecha_scan"),
        Index("ix_historial_tienda",     "tienda"),
        Index("ix_historial_barcode",    "barcode"),
        Index("ix_historial_sucursal",   "sucursal_id"),
    )
