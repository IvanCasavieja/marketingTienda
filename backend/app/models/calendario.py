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
    # De qué negocio es (0060): 'tienda_inglesa', 'redexpres'... Las claves
    # están en app/core/mundos.py. Cada mundo es un calendario aparte.
    mundo: Mapped[str] = mapped_column(
        String(32), nullable=False, default="tienda_inglesa", server_default="tienda_inglesa", index=True
    )
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
    # Un control que la acción trae sola (0077): hoy solo 'lanzar', en
    # Redexpres (ver app/services/controles_redexpres.py; Cierre y los de FDS
    # se sacaron en la 0083). Le llega a todo el equipo del mundo además de
    # `destinatarios`.
    control: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarioTarea(Base):
    """Una tarea de una acción, asignada a una persona (0060).

    Pedido de Ivan (12/11/2026): quien lidera el equipo abre una acción y
    "crea subtareas, y esas subtareas van a estar asignadas a determinadas
    personas", que se enteran por la campanita. Una tarea puede colgar de otra
    (`parent_id`): tarea → subtarea → sub-subtarea, y no más hondo.

    Es una fila aparte por lo mismo que las piezas: dos personas tildando dos
    tareas de la misma acción no se pisan."""

    __tablename__ = "calendario_tareas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    barra_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_barras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=True, index=True
    )
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'pendiente' | 'en-proceso' | 'hecha'
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    asignado_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    vence: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Quién la hace (0070). Pedido de Ivan (16/11/2026): los banners los hace
    # Publicis (usa la plataforma), algunos mailings otra agencia que no la
    # usa, los rompeprecios del finde los diseñadores de Tienda. Entonces:
    # - 'agencia': una agencia de la plataforma. `agencia` es el nombre de su
    #   empresa, como `users.empresa`: la tarjeta es de la agencia, la ven y la
    #   trabajan todas sus cuentas (ver externos.es_tarea_propia).
    # - 'fuera': una agencia que no usa la plataforma. `agencia` es su nombre y
    #   quien carga sus entregas es la persona del equipo asignada.
    # - 'tienda': la gente de Tienda Inglesa (la persona asignada).
    para: Mapped[str] = mapped_column(String(8), nullable=False, default="tienda", server_default="tienda")
    agencia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # El tipo de tarea ('banners', 'cenefas'... ver app/services/tipos_de_tarea.py)
    # y lo que se tildó de él (["Header", "Slider"]). Con tipo, la tarea es una
    # pieza: tiene su tarjeta en el tablero y se llama "<Acción> - <Tipo>".
    tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    opciones: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Los datos de más del tipo: el CTA de un banner, cuántos bloques lleva
    # un mailing ({"cta": "Ver ofertas", "bloques": 5}).
    detalles: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # De dónde sale `vence` cuando vino de una plantilla (0065): 'inicio' o
    # 'fin' de la acción, más `ancla_dias` (negativo = antes). Mientras esté,
    # si la acción se mueve de fecha la tarea se mueve con ella. Si alguien le
    # cambia el vencimiento a mano, se vacía: lo manual se respeta.
    ancla: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ancla_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # De qué plantilla salió (sin FK: borrar la plantilla no toca las tareas
    # ya creadas). Sirve para no sugerir otra vez una plantilla ya usada.
    plantilla_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class CalendarioPlantilla(Base):
    """Una plantilla de tareas de un mundo (0065).

    Cada tipo de acción lleva casi siempre las mismas tareas (el brief a la
    agencia, las entregas, la aprobación, las cenefas a los locales, el
    retiro), y cargarlas a mano en cada acción era repetir lo mismo cada vez.
    Una plantilla las guarda con su vencimiento RELATIVO (N días antes o
    después del inicio o del fin de la acción), y al aplicarla en una acción
    se crean con la fecha ya calculada.

    Las tareas van en una lista y no en una tabla, como los destinatarios de
    un aviso: una plantilla se lee y se guarda siempre entera, y nadie
    consulta "las tareas de plantilla de tal persona"."""

    __tablename__ = "calendario_plantillas"

    # Lo genera el front (pl-...), como el de las barras: un reintento del
    # mismo guardado no duplica la plantilla.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mundo: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    # La categoría de acción (la `banda`, "MEGA EVENTO") a la que va. Con una,
    # la ficha de una acción de esa categoría la sugiere. Null = de cualquiera.
    categoria: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{id, parentId, titulo, descripcion, asignadoA, ancla, dias, para, agencia}, ...]
    # `para`/`agencia` (0070): si la tarea es para la agencia, al aplicar la
    # plantilla le nace sola su tarjeta.
    tareas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
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


class CalendarioRevisionMundo(Base):
    """La última revisión (del contador de arriba) que tocó cada mundo.

    Con esto /datos contesta "sin cambios" a quien mira un mundo donde no
    cambió nada, aunque en otro sí (migración 0063)."""

    __tablename__ = "calendario_revision_mundo"

    mundo: Mapped[str] = mapped_column(String(32), primary_key=True)
    rev: Mapped[int] = mapped_column(BigInteger, nullable=False)
