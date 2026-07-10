from sqlalchemy import String, Integer, Numeric, ForeignKey, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from decimal import Decimal
from app.core.database import Base


class AIUsageLog(Base):
    """Un registro por cada llamada real a un proveedor de IA (Anthropic/OpenAI/Groq),
    para tener visibilidad de costo/tokens por feature y por usuario — ver
    app/core/ai_pricing.py para el cálculo de estimated_cost_usd."""
    __tablename__ = "ai_usage_logs"
    __table_args__ = (
        Index("ix_ai_usage_logs_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    feature: Mapped[str] = mapped_column(String(50), nullable=False)  # "debate" | "don_tino_home" | "don_tino_precios"
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # "anthropic" | "openai" | "groq"
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
