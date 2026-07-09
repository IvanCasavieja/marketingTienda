from datetime import date, datetime

from sqlalchemy import Date, Float, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class CotizacionDolar(Base):
    __tablename__ = "cotizaciones_dolar"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    compra: Mapped[float] = mapped_column(Float, nullable=False)
    venta: Mapped[float] = mapped_column(Float, nullable=False)
    fuente: Mapped[str] = mapped_column(String(20), nullable=False, default="brou")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
