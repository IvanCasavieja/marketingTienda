"""La revisión que hace la IA de una versión entregada, antes que el aprobador
(0068). La lógica está en app/services/revision_ia.py.

Una fila por versión, y nunca más de una: la clave es la versión. Así una
versión se manda a la IA una sola vez, aunque la subida se reintente o dos
procesos la agarren a la vez (el segundo choca contra la fila del primero). Es
lo que evita pagar dos veces por lo mismo.

Las observaciones van en una lista JSON y no en una tabla aparte: se leen
siempre todas juntas (son pocas, como mucho 10) y lo único que cambia después
es el estado de cada una (la descartaron, la hicieron marca), que se escribe
con la fila bloqueada.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalendarioRevisionIA(Base):
    __tablename__ = "calendario_revisiones_ia"
    # Para contar cuántas se hicieron hoy (el tope por día) sin recorrer todo.
    __table_args__ = (Index("ix_calendario_revisiones_ia_created", "created_at"),)

    version_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_versiones.id", ondelete="CASCADE"), primary_key=True
    )
    # 'pendiente' (la IA la está mirando) | 'lista' | 'error' (falló: no se
    # muestra nada) | 'tope' (no se mandó: ya se llegó al tope del día).
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    # Por qué terminó en error o en tope. Es para quien mira la base, no para
    # la pantalla: ahí un error no se muestra.
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # [{id, tipo, texto, gravedad, imagenId, x, y, estado, marcaId, numero,
    #   por, fecha}] — ver `limpiar_observaciones` en el servicio.
    observaciones: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
