from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FacturacionCanje(Base):
    """Acuerdo de canje (trueque) con una marca/proveedor -- valor equivalente
    en dinero, estado, vigencia y cuenta a la que ingresa (mismo concepto de
    cuenta que FacturacionMovimiento, ver ese modelo). Igual que Movimiento,
    documento_id es nullable para no cerrar la puerta a una carga manual
    futura."""

    __tablename__ = "facturacion_canjes"
    __table_args__ = (
        UniqueConstraint("documento_id", name="uq_facturacion_canjes_documento_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    marca_proveedor: Mapped[str] = mapped_column(String(200), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, default="UYU")
    # pendiente | activo | cerrado
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    vigencia_desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cuenta_id: Mapped[int | None] = mapped_column(
        ForeignKey("facturacion_cuentas.id", ondelete="RESTRICT"), nullable=True
    )
    documento_id: Mapped[int | None] = mapped_column(
        ForeignKey("facturacion_documentos.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
