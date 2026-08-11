from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FacturacionDocumento(Base):
    """Un PDF de factura subido a Facturación, con su estado de revisión.

    El PDF entero se guarda en la propia base (file_bytes) — no hay storage
    tipo S3 en este repo, y es la opción más simple dado que estos archivos
    necesitan persistir para auditoría (a diferencia de los PPTX generados
    por Cenefas, que son descartables — ver cenefas/jobs.py)."""

    __tablename__ = "facturacion_documentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # pendiente_revision | confirmado | descartado
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente_revision")
    # Lo que DogTi extrajo tal cual, sin las ediciones del usuario -- auditoría.
    extraction_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Si DogTi no pudo leer el PDF, la fila igual se crea (nunca un 500 por un
    # PDF raro) y el usuario completa el resto a mano en la revisión.
    extraction_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
