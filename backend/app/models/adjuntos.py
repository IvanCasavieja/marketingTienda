"""Los archivos del pedido de una tarea (0089).

Pedido de Ivan (24/11/2026): "en el brief de las tareas deberíamos poder
adjuntar archivos, como el Excel por ejemplo". El Excel con los productos de
la acción, un PDF con referencias, el Word con los textos: van con la tarea y
los ve y los baja quien la hace (la agencia de esa pieza incluida).

- Se adjuntan al crear la tarea o la pieza («Nueva tarea», «Pedir una
  pieza») y después desde la ficha de la acción o desde la tarjeta, en «Lo
  que se pidió».
- Los adjuntos de una tarea los ven también las piezas que cuelgan de ella:
  así el Excel de «Nueva tarea» con sus piezas se sube una sola vez y le
  llega a cada agencia (como el detalle, que se copia en cada pieza).
- Adjunta y saca quien gestiona las tareas, y quien creó esa tarea si pide
  piezas (calendario.pedidos). La agencia no adjunta al pedido: entrega.

**Cuánto ocupa.** La base es Supabase gratis: 500 MB para TODO. Por eso
(ver app/services/adjuntos.py): hasta 10 MB por archivo, hasta 5 por tarea y
entre todos los adjuntos de la plataforma hasta ADJUNTOS_TOPE_MB (50 MB, en
app/core/config.py), además del freno de la base (BASE_TOPE_MB). Un Excel
de 1.000 productos pesa unos 140 KB. Si no entra, no se guarda y se dice
qué hacer: no se borra nada solo. Se van con su tarea (si alguien la borra,
o borra la acción).

Los bytes van `deferred`: listar no los trae, solo bajar uno.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalendarioAdjunto(Base):
    __tablename__ = "calendario_adjuntos"

    # Lo genera el servidor (ad-...).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tarea_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # El nombre con el que se subió ("Listado ciberlunes.xlsx"), sin la
    # carpeta: es con el que se baja.
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    # El tipo, según la extensión Y lo que tiene adentro (ver
    # app/services/adjuntos.py: validar).
    tipo_mime: Mapped[str] = mapped_column(String(100), nullable=False)
    # Lo que pesa, en bytes.
    tamano: Mapped[int] = mapped_column(Integer, nullable=False)
    datos: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    subido_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
