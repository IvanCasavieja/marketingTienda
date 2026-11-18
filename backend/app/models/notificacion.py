from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, SmallInteger, false, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # "precio_cambio" — abierto a más tipos a futuro
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    leida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    watchlist_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("watchlist_items.id", ondelete="SET NULL"), nullable=True
    )
    # Origen genérico (más allá de watchlist) para poder deduplicar y filtrar
    # sin agregar una FK nueva por cada feature que empiece a notificar —
    # ej. origen_tipo="campaign_alert", origen_ref="google_ads:12345:roas_baja".
    origen_tipo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    origen_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Por mail (0079): cada aviso nuevo nace pendiente de salir por mail (el
    # default es del modelo: los de antes de la 0079 quedaron en false). Lo
    # manda app/services/avisos_por_mail.py, al minuto.
    mail_pendiente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=false())
    mail_enviado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mail_intentos: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
