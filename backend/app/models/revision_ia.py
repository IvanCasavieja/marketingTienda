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
    # [{id, tipo, texto, gravedad, imagenId, x, y, archivo, pagina, origen,
    #   estado, marcaId, numero, por, fecha}] — ver `limpiar_observaciones` en
    # el servicio. `archivo`/`pagina`/`origen` (19/11/2026): de qué archivo
    # del ZIP o del link es; una observación de antes no los trae.
    observaciones: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Lo del ZIP y el link (0080, 19/11/2026): {"revisados": [{nombre, origen,
    # paginas}], "noSePudoAbrir": [texto], "ignorados": [nombre]}. Es lo que
    # el aprobador tiene que ver cuando un link no se pudo abrir. Null en las
    # revisiones de antes y cuando no hubo ZIP ni link.
    materiales: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Si se ve hecho lo que se pidió en la ronda anterior (0082, 19/11/2026):
    # [{marcaId, numero, veredicto ('hecho' | 'falta' | 'dudoso'), nota}], una
    # por marca de esa ronda (ver `limpiar_cambios_pedidos` en el servicio).
    # Null si no había nada que controlar (la versión no venía después de una
    # ronda que volvió con marcas), si la IA no llegó a mirar (falló o no
    # había imágenes) y en las revisiones de antes del 19/11/2026. Vacía, en
    # cambio, es que miró y no dijo nada que sirviera de ninguna marca.
    cambios_pedidos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalendarioControlPrevio(Base):
    """El control de la IA ANTES de entregar (0086, Ivan 20/11/2026: "que a
    la agencia, cuando va a subir los archivos, la IA le diga 'che, pará, acá
    faltan estas cositas de los cambios'"). Ver
    app/services/revision_ia.py (controlar_antes_de_entregar).

    Es la misma revisión que se haría al entregar, pero sobre las imágenes
    que la agencia todavía no mandó: se guarda entera (observaciones y
    cambios pedidos), con la huella de esas imágenes. Si después entrega
    exactamente esas, la revisión de la versión sale de acá y no se le paga
    dos veces a la IA (`usado_en_version_id`). A la agencia se le muestra
    solo el veredicto de los cambios pedidos."""
    __tablename__ = "calendario_controles_previos"
    __table_args__ = (
        Index("ix_calendario_controles_previos_tarea", "tarea_id", "created_at"),
        Index("ix_calendario_controles_previos_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tarea_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False
    )
    # La fase en curso y la ronda que se iba a entregar: si al entregar ya no
    # son esas (alguien decidió algo en el medio), no se reusa.
    fase_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_fases.id", ondelete="CASCADE"), nullable=False
    )
    ronda: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # sha256 de las imágenes, en orden (revision_ia.huella_de).
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    # 'pendiente' | 'lista' | 'error' | 'tope', como en CalendarioRevisionIA.
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Como en CalendarioRevisionIA, pero `imagenId` va como "previa:N" (la
    # imagen N de las que se iban a entregar): al reusarlo pasa a ser el id de
    # la imagen guardada (revision_ia.observaciones_de_la_version).
    observaciones: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cambios_pedidos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    # La versión cuya revisión salió de este control (no se pagó dos veces).
    usado_en_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("calendario_versiones.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
