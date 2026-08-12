from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FacturacionCuenta(Base):
    """Cuenta a la que ingresan gastos del presupuesto y canjes (ej. distintas
    razones sociales/locales que manejan su propio presupuesto). Catálogo
    editable desde el panel de administración de Facturación.

    "Eliminar" una cuenta NUNCA borra la fila -- solo la marca inactiva
    (activa=False). Movimientos/canjes ya cargados guardan el cuenta_id
    tal cual, así que su historial y su nombre de cuenta se conservan
    siempre, aunque esa cuenta ya no aparezca como opción para cargas
    nuevas. Ver facturacion/cuentas_service.py."""

    __tablename__ = "facturacion_cuentas"
    __table_args__ = (
        UniqueConstraint("nombre", name="uq_facturacion_cuentas_nombre"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
