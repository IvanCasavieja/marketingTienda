import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CenefaConocimiento(Base):
    """Algo que el módulo de cenefas aprendió de cómo se lo usa.

    Hoy ese conocimiento vive en la cabeza de quien hizo la campaña: que en los
    listados de Fiambrería la columna se llama "PVP REGULAR", que la plantilla
    de Pinchos achica el precio, que tal aviso no le sirve a nadie. Cuando esa
    persona no está, se vuelve a tropezar con lo mismo.

    **Nada se activa solo.** Cada registro nace `propuesto`, con de dónde salió
    y cuántas veces se vio. Una persona lo aprueba, lo descarta o lo edita, y
    recién ahí (`activo`) entra al contexto del agente. Un agente que se
    auto-alimenta sin control aprende también los errores.

    La unicidad es `(tipo, clave)`: registrar lo mismo dos veces no crea un
    duplicado, sube `veces_visto`. Eso es lo que hace que la repetición valga
    como evidencia -- una columna que se llamó igual en cuatro listados es
    mucho más confiable que una que apareció una vez.
    """

    __tablename__ = "cenefa_conocimiento"
    __table_args__ = (
        UniqueConstraint("tipo", "clave", name="uq_cenefa_conocimiento_tipo_clave"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # alias_columna | plantilla | aviso | correccion | preferencia
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    # Identidad normalizada dentro del tipo.
    clave: Mapped[str] = mapped_column(String(200), nullable=False)
    # La frase que el agente lee. En castellano, una sola idea.
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    # Datos crudos de respaldo, para poder revisar de dónde salió.
    detalle: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict,
                                          server_default="{}")
    # revision_previa | mapeo | grilla | job | manual
    origen: Mapped[str] = mapped_column(String(60), nullable=False)
    # propuesto | activo | descartado | archivado
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="propuesto",
                                        server_default="propuesto")
    veces_visto: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                             server_default="1")
    visto_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                               server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(),
                                                 onupdate=func.now())
    decidido_por: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decidido_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
