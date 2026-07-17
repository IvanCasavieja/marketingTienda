import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CenefaTemplateV2(Base):
    __tablename__ = "cenefa_templates_v2"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # JSON completo del template: variables, components, rules
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Ej: ['a4', 'a3', 'pinchos']
    formats: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)
    # Destino: 'redexpres' | 'rompe_precios' | ... — string libre, sin enum,
    # para que un destino nuevo no requiera migración. Necesario porque dos
    # destinos pueden compartir el mismo id de formato (ej. "a4").
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # PPTX crudo del que se importó esta definición (si vino de un archivo
    # subido, no de un template armado a mano en el editor v2). El render
    # final lo usa como base para preservar el diseño de fondo/master/layout
    # del archivo original — ver component_renderer.render_template_to_pptx.
    source_pptx: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
