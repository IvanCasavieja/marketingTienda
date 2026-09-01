from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FacturacionProveedorCuenta(Base):
    """Cuenta recomendada para un proveedor recurrente.

    Un proveedor entra a esta tabla cuando su historial muestra que factura
    siempre a la misma cuenta (recurrencia derivada de Gastos 2026.xlsx, y
    lo que se agregue despues). Al subir un PDF suyo, esa cuenta se
    preselecciona en la revision y alcanza con aprobar -- la persona
    siempre puede elegir otra.

    `proveedor` se guarda NORMALIZADO (ver normalizar_proveedor en
    services/facturacion/recomendacion.py): los nombres vienen de sistemas
    distintos y "CREATIVAS S A" y "CREATIVAS S.A" son el mismo proveedor.
    """

    __tablename__ = "facturacion_proveedor_cuenta"
    __table_args__ = (
        UniqueConstraint("proveedor", name="uq_facturacion_proveedor_cuenta_proveedor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor: Mapped[str] = mapped_column(String(200), nullable=False)
    cuenta_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("facturacion_cuentas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    facturas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    origen: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
