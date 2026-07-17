from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MeridianChannelSummary(Base):
    """Última foto por canal del modelo de Marketing Mix (Meridian) — spend,
    ROI y % de contribución a la revenue, uno por canal. Se sobreescribe
    entera cada vez que se refitea el modelo (ver
    scripts/import_meridian_summary.py); no guarda historial de corridas.

    `reliable=False` marca que el modelo se fiteó con menos de 52 semanas de
    historia (ver meridian_mmm/fit_model.py) — debate_service.py no debe
    usar estos números como insight de negocio en ese caso, solo confirmar
    que el pipeline corre."""

    __tablename__ = "meridian_channel_summary"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    spend: Mapped[float] = mapped_column(Float, nullable=False)
    pct_of_spend: Mapped[float] = mapped_column(Float, nullable=False)
    incremental_outcome: Mapped[float] = mapped_column(Float, nullable=False)
    pct_of_contribution: Mapped[float] = mapped_column(Float, nullable=False)
    roi: Mapped[float] = mapped_column(Float, nullable=False)
    mroi: Mapped[float] = mapped_column(Float, nullable=False)
    reliable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("channel", name="uq_meridian_channel_summary_channel"),
    )
