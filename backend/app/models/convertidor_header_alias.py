from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConvertidorHeaderAlias(Base):
    """Cache de headers de columna que Tinín ya clasificó en un import
    anterior (ver convertidor.py, resolve_date_columns_with_ai en
    convertidor_ai.py). El mismo texto normalizado de columna nunca vuelve a
    pasar por IA una segunda vez — la próxima vez se resuelve por código,
    igual que cualquier entrada de _INPUT_ALIASES, solo que aprendida en vez
    de hardcodeada.

    field_name es NULL cuando Tinín confirmó que esa columna NO es de
    vigencia (ej. "fecha de alta") -- se cachea igual que un match positivo,
    para no volver a preguntarle por ese mismo header en cada import futuro."""

    __tablename__ = "convertidor_header_aliases"

    header_norm: Mapped[str] = mapped_column(String(120), primary_key=True)
    field_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
