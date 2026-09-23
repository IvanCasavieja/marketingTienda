from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalendarioMes(Base):
    """Un mes del calendario, guardado entero como documento.

    El calendario nació guardando en localStorage: cada navegador tenía su
    copia y el servidor no sabía que existía ninguna acción. Así no se podía
    avisar nada con anticipación, que es justamente lo que se pidió (aviso 10
    días antes de cada acción).

    Se guarda el mes completo tal cual lo arma el front (`Mes` en
    frontend/lib/calendario/tipos.ts) en vez de descomponerlo en tablas: las
    bandas, las filas y las barras son una estructura anidada que sólo el
    calendario entiende, y partirla en cinco tablas no compra nada — nadie
    consulta "todas las barras de tal color". Lo único que el backend necesita
    leer de adentro son las acciones del calendario comercial y su fecha de
    inicio, y eso se recorre bien sobre el JSON.
    """

    __tablename__ = "calendario_meses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 'YYYY-MM'
    clave: Mapped[str] = mapped_column(String(7), unique=True, index=True, nullable=False)
    datos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    actualizado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
