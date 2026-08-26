from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CenefaOfertadetAlias(Base):
    """Qué familia de mecánica es un OFERTADET que el motor no reconoce.

    El Convertidor deduce la familia del texto de OFERTADET ("M x N",
    "Combo /  N  unidades por $X"...). Cuando gestión inventa un tipo nuevo,
    `familia_de_ofertadet` devuelve None: la fila pierde la mecánica --sin
    cocarda, sin "Comprando N", sin unidad-- y lo único que queda es el aviso
    `ofertadet_desconocido`.

    Acá se guarda la respuesta una vez que una persona la confirmó. Desde ese
    momento ese OFERTADET lo resuelve el código, igual que los que están
    hardcodeados, solo que aprendido -- y no se le vuelve a preguntar a Tinín
    por el mismo texto nunca más.

    "sin_mecanica" es una respuesta tan válida como las otras tres: significa
    "esto no anuncia nada" (es lo que corresponde a Precio fijo o % descuento),
    y guardarla es lo que hace que el aviso deje de aparecer.

    Mismo patrón que ConvertidorHeaderAlias, para las columnas.
    """

    __tablename__ = "cenefa_ofertadet_aliases"

    # El texto de OFERTADET normalizado (ver _norm en convertidor.py): sin
    # tildes, sin espacios y en minúscula, así "M x N" y "m×n" son el mismo.
    ofertadet_norm: Mapped[str] = mapped_column(String(120), primary_key=True)
    # combo | mxn | segunda | sin_mecanica -- ver FAMILIAS_MECANICA.
    familia: Mapped[str] = mapped_column(String(20), nullable=False)
    # El texto tal cual vino, para poder mostrarlo en pantalla sin normalizar.
    ofertadet_display: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    confirmado_por: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
