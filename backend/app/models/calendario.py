"""El calendario, una fila por barra y con fechas reales.

Hasta la 0057 el calendario se guardaba como un documento por mes
(`calendario_meses`), y eso traía dos problemas de fondo:

- **Una acción no podía cruzar de mes.** Cada barra era "del día X al día Y"
  de SU mes, así que algo que arranca el 25/09 y termina el 5/10 quedaba
  recortado a fin de mes y había que cargarlo dos veces, con sus piezas dos
  veces.
- **Dos personas se pisaban.** Cada cambio subía el mes entero, y ganaba el
  último que guardaba: el cambio del otro se perdía sin que nadie se enterara.

Acá cada acción, campaña de Retail Media o banner cargado a mano es una fila,
con `desde` y `hasta` como fechas de verdad, y cada cambio toca solo lo que
cambió: la barra, una pieza, un aviso. El mes pasa a ser una vista que arma el
front con las barras que lo tocan.

Lo que NO se guarda porque se deriva: los headers que bajan de Retail Media y
de las acciones con pieza Header, el conteo del header y el cronograma de
envíos. Se recalculan en el front con esto.
"""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalendarioBarra(Base):
    """Una acción del calendario comercial, una campaña de Retail Media o un
    banner del header cargado a mano."""

    __tablename__ = "calendario_barras"

    # Lo genera el front (br-...), así la barra existe en pantalla antes de que
    # conteste el servidor. Los de antes de la 0057 se conservaron tal cual, y
    # con ellos los avisos viejos siguen apuntando a su acción.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 'comercial' | 'retail' | 'header' | 'envio'
    seccion: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # El tipo de acción ("MEGA EVENTO"), el formato de Retail Media ("CARRUSEL"),
    # la posición del header ("pos-3") o el canal de un envío suelto ("email").
    banda: Mapped[str] = mapped_column(Text, nullable=False)
    # En qué renglón de su banda va. Se conserva para que una acción que cruza
    # de mes quede a la misma altura en los dos.
    carril: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    desde: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hasta: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Solo en los envíos sueltos (0058): lo que en un envío de una acción lleva
    # su pieza. "Mailing digital" / "Recordatorio" / "Envío masivo" / "Push app",
    # la hora 'HH:MM' en que sale, y el estado (pendiente → publicado).
    formato: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hora: Mapped[str | None] = mapped_column(String(5), nullable=True)
    estado: Mapped[str | None] = mapped_column(String(20), nullable=True)

    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actualizado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class CalendarioPieza(Base):
    """Una pieza de una acción: el header de la home, el mailing impreso, el
    envío de WhatsApp. Es una fila aparte para que dos personas moviendo el
    estado de dos piezas de la misma acción no se pisen."""

    __tablename__ = "calendario_piezas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    barra_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_barras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 'web-home' | 'web-landing' | 'fisico' | 'email' | 'whatsapp' | 'push'
    area: Mapped[str] = mapped_column(String(20), nullable=False)
    formato: Mapped[str] = mapped_column(String(100), nullable=False)
    # 'pendiente' | 'en-proceso' | 'aprobado' | 'publicado'
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    # Vigencia propia. Sin ella la pieza dura lo que su acción. En las piezas
    # de envío, `desde` es el día en que sale.
    desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    hora: Mapped[str | None] = mapped_column(String(5), nullable=True)
    en_sharepoint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # El orden en que se agregaron, que es el que muestra la ficha.
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class CalendarioAviso(Base):
    """Un aviso que alguien configuró a mano en la ficha de una acción.

    Pedido de Ivan (28/09/2026): los avisos no se generan solos. "Cuando
    realmente nos llegue una notificación, es porque alguien la configuró y
    porque realmente vale la pena". Por eso no hay ninguno por defecto: el que
    carga la acción elige cuántos días antes y a quién.

    Se guarda la anticipación, no la fecha: si la acción se corre, el aviso se
    corre con ella."""

    __tablename__ = "calendario_avisos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    barra_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_barras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dias_antes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Ids de usuario. Una lista y no una tabla: nadie consulta "los avisos de
    # tal persona", y el aviso se lee siempre entero.
    destinatarios: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarioPosicionesRM(Base):
    """Qué posiciones del header tiene Retail Media en un mes. Por defecto
    4, 5 y 6; un mes sin fila usa esas."""

    __tablename__ = "calendario_posiciones_rm"

    # 'YYYY-MM'
    clave: Mapped[str] = mapped_column(String(7), primary_key=True)
    posiciones: Mapped[list] = mapped_column(JSONB, nullable=False)
    actualizado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )


class CalendarioRevision(Base):
    """Un contador que sube con cada cambio del calendario, en la misma
    transacción que el cambio.

    Es lo que usa el front para enterarse de lo que hicieron los demás sin
    bajarse todo cada vez: pregunta "¿sigue en la 41?" y si la respuesta es sí,
    no viaja nada más. Una sola fila, id = 1."""

    __tablename__ = "calendario_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rev: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
