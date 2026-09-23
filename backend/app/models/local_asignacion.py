from sqlalchemy import String, Integer, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class LocalAsignacion(Base):
    __tablename__ = "local_asignaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    local_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    # "redex" | "tienda" — separa las dos pestañas de sucursales en el panel de
    # usuarios. Hoy todas son de Redexpres; las de Tienda llegan más adelante.
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="redex", server_default="redex")

    __table_args__ = (
        UniqueConstraint("user_id", "local_nombre", name="uq_local_asignacion"),
    )
