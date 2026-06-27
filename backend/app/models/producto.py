from sqlalchemy import String, Float, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.core.database import Base


class Producto(Base):
    __tablename__ = "productos"

    id:           Mapped[int]           = mapped_column(primary_key=True)
    tienda:       Mapped[str]           = mapped_column(String(100), nullable=False)
    url:          Mapped[str]           = mapped_column(String(1000), unique=True, nullable=False)
    nombre:       Mapped[str | None]    = mapped_column(String(500))
    precio:       Mapped[float | None]  = mapped_column(Float)
    precio_lista: Mapped[float | None]  = mapped_column(Float)
    sku:             Mapped[str | None]    = mapped_column(String(100))
    barcode:         Mapped[str | None]    = mapped_column(String(50))
    marca:           Mapped[str | None]    = mapped_column(String(200))
    categoria:       Mapped[str | None]    = mapped_column(String(500))
    sucursal_id:     Mapped[str | None]    = mapped_column(String(50))
    sucursal_nombre: Mapped[str | None]    = mapped_column(String(200))
    actualizado_en:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_productos_tienda",    "tienda"),
        Index("ix_productos_sku",       "sku"),
        Index("ix_productos_barcode",   "barcode"),
        Index("ix_productos_nombre",    "nombre"),
        Index("ix_productos_sucursal",  "sucursal_id"),
    )
