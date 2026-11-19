"""Entregas por fases: la agencia (o el diseñador) sube versiones de una pieza
y quien corresponde las aprueba o las devuelve con correcciones (0067).

Pedido de Ivan (15/11/2026): "Una tarea tiene fase 1, fase 2, fase 3…; se
entrega, se aprueba o vuelve con correcciones, la agencia devuelve con las
correcciones aplicadas, puede volver otra vez, hasta que se aprueba". Como
las tarjetas de Trello con la agencia, pero adentro de la tarea de la acción.

Cómo se arma:

- `calendario_entregas`: que una tarea LLEVA entregas. Una fila por tarea, con
  el tipo de pieza, el pedido a la agencia (el brief, según el tipo) y la
  cadena ordenada de aprobadores. Lleva además un resumen (en qué fase va, a
  quién le toca) que se recalcula en cada cambio: es lo que leen el tablero,
  "Mis tareas" y el calendario sin recorrer todas las versiones.
- `calendario_fases`: "Boceto", "Arte final", "Adaptaciones"... en orden. Se
  trabaja una por vez: la siguiente arranca cuando se aprueba la anterior.
- `calendario_versiones`: cada ronda de una fase. Ronda 1, y si vuelve con
  cambios, ronda 2...
- `calendario_version_imagenes`: hasta 4 por versión, en la base (como los
  archivos de cenefas, ver cenefa_job.py), con su miniatura.
- `calendario_marcas`: un pin numerado sobre un punto de una imagen, con su
  texto. Es un ítem que la agencia tilda cuando lo corrigió.
- `calendario_decisiones`: lo que decidió cada aprobador sobre una versión.

**Cuánto ocupa.** La base es Supabase gratis: 500 MB para TODA la plataforma,
y no se va a pagar más (15/11/2026). Por eso:

- Las imágenes se comprimen en el navegador antes de subir: lado mayor 1600
  px, JPEG 0,75, y una miniatura de 320 px. Medido el 15/11/2026 con
  imágenes de prueba: una gráfica plana (cenefa) pesó 46 KB, una foto de
  1600x1067 247 KB, y sus miniaturas 6 y 17 KB. Hasta 4 por versión y 2 MB
  como mucho cada una (lo controla el servidor).
- Los bytes se borran (la grande y la miniatura): los de las versiones que
  no son la final, a los 30 días de terminada la acción; los de la final (la
  aprobada de la última fase), a los 120. Las versiones, decisiones y marcas
  quedan siempre (ver purgar_imagenes_viejas).
- Antes de guardar, el freno general (app/services/espacio.py): si la base
  pasa de BASE_TOPE_MB (400), la subida se rechaza.

Con un uso razonable de Tienda Inglesa —25 tareas con entregas por mes, 2
fases, 1,5 rondas por fase y 1,5 imágenes por versión— son unas 110 imágenes
por mes: entre 6 MB (si fueran todas gráficas planas) y 30 MB (todas fotos),
unos 18 MB con una mezcla normal. Como todo vence, lo guardado NO crece con
el tiempo: en régimen quedan unos 3,5 meses de subidas (las no finales viven
~2,5 meses desde que se suben, la final ~5,5), o sea entre 20 y 100 MB, unos
60 con la mezcla normal. Si el uso se duplica, el doble; el freno de 400 MB
cuida que nunca le quite lugar al resto.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalendarioEntrega(Base):
    """Que una tarea lleva entregas, con qué se le pide a la agencia y quiénes
    aprueban. Quien entrega es el responsable de la tarea (`asignado_a_id`)."""

    __tablename__ = "calendario_entregas"

    tarea_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_tareas.id", ondelete="CASCADE"), primary_key=True
    )
    # 'cenefa' | 'mailing' | 'banner' | 'redes' | 'otro'
    tipo_pieza: Mapped[str] = mapped_column(String(20), nullable=False)
    # El pedido a la agencia: los campos del formulario de su tipo de pieza
    # (ver CAMPOS_DEL_BRIEF en app/services/entregas.py).
    brief: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Ids de usuario, en el orden en que aprueban (promo → marca → comercial).
    # Una lista y no una tabla, como los destinatarios de un aviso: se lee
    # siempre entera y nadie consulta "las cadenas de tal persona" (eso sale
    # del resumen de abajo).
    aprobadores: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # El resumen. Se recalcula en cada cambio (ver `recalcular`), en la misma
    # transacción: 'produccion' (le toca a la agencia, ronda nueva), 'revision'
    # (hay una versión esperando a un aprobador), 'cambios' (volvió con
    # correcciones: le toca a la agencia) o 'aprobada' (todas las fases).
    momento: Mapped[str] = mapped_column(String(20), nullable=False, default="produccion")
    fase_actual_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # La última ronda de la fase actual (0 = todavía no se entregó nada).
    ronda: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # A quién le toca decidir, cuando hay una versión en revisión.
    aprobador_de_turno_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # El tablero de tarjetas (0070), estilo Trello: Ingresado, En proceso,
    # Esperando feedback, Finalizado y Archivado. La columna sale del momento
    # (ver entregas.columna_de) y de estas fechas, que son lo único que el
    # momento no dice:
    # - cuándo la arrancó quien entrega (Ingresado → En proceso). También se
    #   pone sola con la primera entrega.
    iniciada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # - cuándo quedó aprobada la última fase (Finalizado). Se vacía si vuelve
    #   a haber algo para entregar (le agregaron una fase).
    finalizada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # - cuándo pasó a Archivado: a mano, o sola a los ARCHIVAR_TARJETAS_DIAS
    #   de finalizada (entonces `archivada_por_id` queda en null).
    archivada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archivada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # - cuándo alguien la sacó del archivo a mano: los días para que se
    #   archive sola vuelven a contar desde ahí (si no, se volvería a
    #   archivar en el acto).
    desarchivada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # - la columna a la que la llevó alguien del equipo a mano (0075, "libre,
    #   como Trello"): Ingresado, En proceso o Esperando feedback. Manda sobre
    #   la que dicen las entregas hasta que pasa algo de verdad (una entrega,
    #   una decisión). Finalizado a mano no va acá: es darla por aprobada.
    columna_manual: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class CalendarioFase(Base):
    """Una fase de la tarea. Se trabaja una por vez y en orden."""

    __tablename__ = "calendario_fases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tarea_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    # 'pendiente' | 'en-curso' | 'aprobada'
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    aprobada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Si la fase la abrió una devolución (0072): lo que hay que cambiar y
    # quién lo pidió. Pedido de Ivan (17/11/2026): después de aprobada, la
    # pieza se tiene que poder volver para atrás con un texto, y cada vuelta
    # suma una fase más (Entrega 2, Entrega 3...), sin tope.
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    abierta_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarioVersion(Base):
    """Una ronda de una fase: lo que subió quien entrega, y cómo terminó."""

    __tablename__ = "calendario_versiones"
    __table_args__ = (UniqueConstraint("fase_id", "ronda", name="uq_calendario_versiones_fase_ronda"),)

    # Lo genera el front (ve-...): si la subida se corta y se reintenta, no
    # quedan dos versiones iguales.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fase_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_fases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Repetido de la fase, para las consultas por tarea.
    tarea_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ronda: Mapped[int] = mapped_column(Integer, nullable=False)
    subida_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    # El original en WeTransfer, Smash... Solo http/https. Desde el 19/11/2026
    # la IA intenta bajarlo en segundo plano (app/services/materiales.py).
    link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Las marcas que quien entrega dice que corrigió en esta ronda (ids).
    corregidas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 'revision' | 'aprobada' | 'cambios'
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="revision")
    decidida_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarioVersionImagen(Base):
    """Una imagen de una versión. Los bytes van `deferred`: listar imágenes no
    los trae, solo pedir una."""

    __tablename__ = "calendario_version_imagenes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_versiones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 'image/jpeg' | 'image/png' | 'image/webp'
    tipo_mime: Mapped[str] = mapped_column(String(20), nullable=False)
    # La imagen grande y su miniatura. Las dos quedan en NULL cuando vencen
    # (ver purgar_imagenes_viejas); la fila queda, con lo que pesaba.
    datos: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    tipo_mime_miniatura: Mapped[str] = mapped_column(String(20), nullable=False, default="image/jpeg")
    miniatura: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    # Lo que pesaba la grande: queda después de la purga, para medir.
    tamano: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purgada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarioMarca(Base):
    """Un pin numerado sobre un punto de una imagen, con lo que hay que
    cambiar. `x` e `y` van de 0 a 1 (relativos al ancho y al alto), así el pin
    cae en el mismo lugar se vea la imagen del tamaño que se vea.

    'cambio' sale de "Pedir cambios": la agencia lo tilda al reentregar.
    'ajuste' salía de "Aprobado con cambios" (la versión quedaba aprobada y
    esto anotado para el archivo final): esa decisión se sacó el 19/11/2026 y
    ya no se crean marcas de este tipo. Las que hay quedan como historia (no
    hace falta migrar nada: la columna es un texto)."""

    __tablename__ = "calendario_marcas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_versiones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    imagen_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_version_imagenes.id", ondelete="CASCADE"), nullable=False
    )
    # Repetido, para "lo que falta corregir de esta tarea" en una consulta.
    tarea_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # El número que se ve en el pin, dentro de su versión (1, 2, 3...).
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    # 'cambio' (las nuevas, siempre) | 'ajuste' (solo las de antes del 19/11/2026)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False, default="cambio")
    autor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    corregida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # La versión en la que la agencia dijo que la corrigió (null en las
    # viejas que se tildaron sueltas, cuando existían los ajustes).
    corregida_en_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corregida_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarioDecision(Base):
    """Lo que decidió un aprobador sobre una versión. Una por lugar de la
    cadena: `aprobador_id` es a quién le tocaba, `decidido_por_id` quién la
    tomó (el mismo, o alguien con `calendario.tareas` como respaldo)."""

    __tablename__ = "calendario_decisiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_versiones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    aprobador_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decidido_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # El lugar en la cadena cuando se decidió (0 = el primero).
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 'aprobada' | 'cambios'. Las de antes del 19/11/2026 pueden ser
    # 'aprobada-con-cambios': se leen como aprobadas (ver reglas.APRUEBAN).
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    # Lo que ve la agencia: el comentario y las marcas son justamente para ella.
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Una nota SOLO para el equipo (0069), como los comentarios internos de
    # Basecamp: "ojo que comercial todavía no confirmó el precio". Una cuenta
    # externa nunca la recibe, ni en la tarea ni en los avisos.
    nota_interna: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarioComentario(Base):
    """Un comentario en una tarjeta del tablero (0073).

    Pedido de Ivan (17/11/2026): "en las tarjetas de los tableros deberíamos
    tener una opción de poner comentario como tiene Trello en un costado, para
    así poder explicar cambios y cosas así". Los ve y los escribe cualquiera
    que ve la tarjeta: el equipo de Tienda y el tablero (la agencia) al que va.
    """

    __tablename__ = "calendario_comentarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tarea_id: Mapped[str] = mapped_column(
        ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    autor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
