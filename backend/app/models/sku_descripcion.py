from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SkuDescripcion(Base):
    """Catálogo compartido SKU → descripción correcta de cenefa.

    Poblado inicialmente desde Gestion/Diccionario.xlsx (ver
    scripts/seed_sku_descripciones_standalone.py) y alimentado en adelante
    por el Convertidor de Excel: cada corrección manual de una fila sin
    match queda guardada acá, para que la próxima vez que ese SKU aparezca
    en cualquier import futuro (de cualquier usuario) ya venga resuelto."""

    __tablename__ = "sku_descripciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Texto y no entero a propósito: en otras partes del sistema el "código"
    # de un artículo a veces es un rango o trae varios SKUs separados por
    # "/" — no asumimos que el Excel de gestión siempre trae un entero puro.
    #
    # 600 y no 64 (migración 0049): un grupo unificado guarda su descripción
    # bajo el código COMBINADO de todos sus SKU ("520221 - 512909 - ..."), y con
    # 64 un grupo de 11 productos no entraba -- la unificación se cortaba justo
    # cuando más sentido tenía. Ver SKU_COMBINADO_MAX_CHARS en
    # frontend/components/cenefas/convertidor/ConvertidorGrid.tsx, que es el
    # espejo de este número.
    sku: Mapped[str] = mapped_column(String(600), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    # NULL en las filas del seed inicial (no hay usuario); se completa con
    # el usuario real cuando alguien corrige desde el Convertidor.
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("sku", name="uq_sku_descripciones_sku"),
    )
