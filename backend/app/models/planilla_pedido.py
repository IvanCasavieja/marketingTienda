from sqlalchemy import String, Boolean, DateTime, Integer, Text, UniqueConstraint, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.core.database import Base


class PlanillaPedido(Base):
    __tablename__ = "planilla_pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    local_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)

    # Ofertas
    a4_oferta_vertical: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cenefa_oferta_x3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pinchos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    afiche_54x74: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # VDS y Supremo
    cenefa_valle_del_sol: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cenefa_supremo_hogar: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Bombas
    bombas_3xa4: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bombas_a4: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bombas_74x54: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pinchos_bombas: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stickers
    sticker_valle_del_sol: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sticker_carne: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Otros items
    cenefas_preciazos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    afiche_super_ahorro: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pinchos_dias_expres: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hojas_amarillas: Mapped[str | None] = mapped_column(String(50), nullable=True)
    otros: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Estado
    confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("local_nombre", "year", "month", name="uq_planilla_local_periodo"),
    )
