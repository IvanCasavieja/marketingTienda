from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FacturacionMovimiento(Base):
    """Ledger de la cuenta única de presupuesto de la empresa -- una fila por
    entrada/salida confirmada desde el flujo de revisión de una factura.

    documento_id es nullable a propósito: hoy un movimiento siempre nace de
    un PDF, pero no cierra la puerta a una carga manual sin factura más
    adelante. Numeric (no Float) para el monto -- es dinero real, no debe
    acumular error de redondeo."""

    __tablename__ = "facturacion_movimientos"
    __table_args__ = (
        UniqueConstraint("documento_id", name="uq_facturacion_movimientos_documento_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # entrada | salida
    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # siempre positivo, el signo lo da `tipo`
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, default="UYU")
    concepto: Mapped[str] = mapped_column(String(300), nullable=False)
    proveedor_marca: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero_factura: Mapped[str | None] = mapped_column(String(100), nullable=True)  # informativo, no numeración fiscal
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    documento_id: Mapped[int | None] = mapped_column(
        ForeignKey("facturacion_documentos.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
