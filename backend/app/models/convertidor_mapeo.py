import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConvertidorMapeo(Base):
    """Plantilla de mapeo reutilizable del Convertidor.

    Guarda cómo se resuelve cada una de las variables que el Convertidor no
    puede deducir solo (ofertaUno..Cuatro, vigencia, aclaracionUno..Tres,
    legales). Las demás se resuelven por código y no viven acá.

    Cada variable se resuelve de una de dos formas, excluyentes:

    - `mapeo`   {variable: nombre_de_columna} -- sale de una columna del Excel.
    - `valores` {variable: texto_fijo}        -- se escribe a mano y se aplica
      a todas las filas. Hace falta porque el export de gestión no trae nunca
      vigencia ni legales: esos textos los escribe una persona.

    Es compartida por todo el equipo, no por usuario: el archivo de gestión
    de una campaña es el mismo para todos, y hacer que cada persona lo
    reconfigure por su cuenta es exactamente el trabajo repetido que esto
    viene a sacar.

    No hay FK a cenefa_destinos a propósito: un mapeo puede quedar asociado a
    un mundo que después se borra, y perder el mapeo por eso sería peor que
    dejarlo huérfano (sigue siendo reutilizable eligiéndolo a mano).
    """

    __tablename__ = "convertidor_mapeos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    # Slug del mundo al que aplica; NULL = sirve para cualquiera.
    destino: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # {variable_canonica: nombre_de_columna_del_excel}
    mapeo: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {variable_canonica: texto_fijo_para_todas_las_filas}
    valores: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
