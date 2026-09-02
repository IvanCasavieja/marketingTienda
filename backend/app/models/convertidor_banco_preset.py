import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConvertidorBancoPreset(Base):
    """Preset reutilizable de "banco con descuento" del Convertidor.

    Resuelve `precioBanco` (+ su decimal) SIN que el Excel de gestión traiga
    una columna con ese precio ya calculado: muchos descuentos bancarios
    ("15% extra con Club Card Scotia") son un porcentaje fijo que define
    Tienda Inglesa, no algo que gestión calcule por producto. Guardando
    nombre + multiplicador acá, `construir_variables()` calcula
    precioBanco = precioOferta × multiplicador por fila (ver
    convertidor_variables.py) sin tocar el Excel de origen.

    Compartida por todo el equipo, no por usuario -- el descuento de Scotia
    es el mismo para cualquiera que use el Convertidor, igual criterio que
    ConvertidorMapeo.
    """

    __tablename__ = "convertidor_banco_presets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    multiplicador: Mapped[float] = mapped_column(Float, nullable=False)

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
