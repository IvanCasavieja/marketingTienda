import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CenefaGrupoUnificado(Base):
    """Un grupo de SKU que comparten UN cartel: "Coca-Cola Light o Zero 2.25 L".

    Hasta 08/2026 esto se guardaba en `sku_descripciones` usando el código
    COMBINADO como si fuera un SKU ("63009 / 211797"). Eso alcanza para que el
    mismo Excel vuelva a resolver igual, y falla para todo lo demás: si mañana
    la promo trae dos de esos tres SKU, o los mismos tres en otro orden, esa
    clave no matchea y el grupo se pierde.

    Guardar la LISTA permite lo que hacía falta de verdad: detectar que la
    promo de hoy trae un SUBCONJUNTO de un grupo conocido. Ese caso no se puede
    resolver reusando la descripción guardada -- menciona productos que hoy no
    están en oferta, y un cartel de góndola no puede anunciar algo que no se
    vende a ese precio. Hay que reescribirla con los que sí vinieron, y para
    eso hacen falta las descripciones INDIVIDUALES de cada SKU, que siguen
    viviendo en `sku_descripciones` y ya no se pisan con el texto del grupo.
    """

    __tablename__ = "cenefa_grupos_unificados"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nombre corto de la línea de producto, como lo redactó Tinín o el equipo.
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    # El texto de cartel que sirve para TODOS los SKU de la lista.
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    # SKU normalizados (ver normalize_sku en convertidor.py). El orden no
    # significa nada: lo que importa es el conjunto.
    skus: Mapped[list] = mapped_column(ARRAY(String(60)), nullable=False)

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
