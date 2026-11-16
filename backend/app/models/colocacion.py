"""La foto de colocación: los locales muestran cómo quedó la cartelería.

Hoy los locales reciben cenefas y afiches y nadie sabe si los pusieron. Desde
la ficha de una acción del calendario, quien la edita le pide una foto a los
locales; cada local la saca con el teléfono y la sube; promo la aprueba o la
devuelve con un comentario. Tres tablas, de la más general a la más pesada:

- `colocacion_pedidos`: el pedido, uno por acción. A qué tipo de local se le
  pide (los de Redexpres son 'redex'), hasta cuándo y qué fotografiar.
- `colocacion_locales`: lo que le toca a cada local de ese pedido y en qué
  estado está (pendiente → enviada → aprobada, o devuelta).
- `colocacion_fotos`: las fotos, con los bytes adentro. Van en su propia tabla
  y NO viajan en /calendario/datos (que se consulta cada 15 s): se piden una
  por una, cuando alguien las mira.

El local es un nombre (`local_nombre`), igual que en `local_asignaciones`: un
local puede tener más de un login y quien tenga cualquiera de ellos ve y sube
lo de ese local.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.core.database import Base


class ColocacionPedido(Base):
    """El pedido de foto de una acción del calendario. Uno por acción: para
    sumar o sacar locales se cambia este, no se hace otro."""

    __tablename__ = "colocacion_pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    barra_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_barras.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # 'redex' | 'tienda': qué locales (local_asignaciones.tipo). Sale del mundo
    # de la acción (ver TIPO_DE_LOCAL_POR_MUNDO en services/colocacion.py) y
    # se guarda: si mañana cambia el mapeo, un pedido viejo sigue siendo de
    # los locales a los que se les pidió.
    tipo_local: Mapped[str] = mapped_column(String(20), nullable=False)
    # Hasta cuándo hay tiempo. Pasado este día, el local que no tiene foto
    # aprobada ni enviada figura como atrasado.
    limite: Mapped[date] = mapped_column(Date, nullable=False)
    # "Cenefas en cabecera 3 y 4": qué fotografiar.
    indicacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Cuándo se le avisó a quien pidió que ya mandaron todos. Un aviso solo,
    # no uno por foto (serían 60): ver _avisar_si_estan_todas.
    aviso_completo_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class ColocacionLocal(Base):
    """Lo que le toca a un local en un pedido: su estado y, si se la
    devolvieron, por qué."""

    __tablename__ = "colocacion_locales"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("colocacion_pedidos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    local_nombre: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # 'pendiente' | 'enviada' | 'aprobada' | 'devuelta'. "Atrasada" no se
    # guarda: depende del día de hoy, se calcula al mostrarlo.
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente", server_default="pendiente")
    # El comentario de la última devolución ("no se ve la cabecera 4").
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cuándo mandó la última foto: dice si la mandó a tiempo.
    enviada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revisado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revisado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("pedido_id", "local_nombre", name="uq_colocacion_local"),
    )


class ColocacionFoto(Base):
    """Una foto que subió un local, ya achicada en su teléfono, con su
    miniatura. Los bytes van `deferred`: listar fotos (para el tablero, para
    contar cuántas lleva un local) no los trae; solo el endpoint que la sirve
    los pide, a mano y de a una."""

    __tablename__ = "colocacion_fotos"

    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(
        ForeignKey("colocacion_locales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subida_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 'image/jpeg' | 'image/png' | 'image/webp', según los bytes y no según lo
    # que dijo el navegador.
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    tipo_miniatura: Mapped[str] = mapped_column(String(20), nullable=False)
    ancho: Mapped[int] = mapped_column(Integer, nullable=False)
    alto: Mapped[int] = mapped_column(Integer, nullable=False)
    # Lo que ocupan las dos juntas, en bytes. Se guarda para sumar cuánto
    # ocupa la tabla sin leer los bytes de cada foto (ver el tope en
    # services/colocacion.py).
    peso: Mapped[int] = mapped_column(Integer, nullable=False)
    # La foto estaba cuando la devolvieron. Se sigue mostrando (para que el
    # local vea qué le devolvieron) hasta que sube la nueva, y ahí se borra.
    devuelta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    datos: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    miniatura: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
