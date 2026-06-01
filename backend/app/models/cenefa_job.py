import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CenefaJob(Base):
    __tablename__ = "cenefa_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_group_id: Mapped[int] = mapped_column(
        ForeignKey("team_groups.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cenefa_templates_v2.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # pending | running | done | error
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # a4 | a3 | 3xa4 | pinchos
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    # pptx | pdf | png
    export_type: Mapped[str] = mapped_column(String(20), nullable=False, default="pptx")
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Lista de errores detectados por validation_engine
    validation_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
