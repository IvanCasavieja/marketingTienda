from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RrssValidacion(Base):
    """Una corrida de "Validación de RRSS": un mailing original contra un
    lote de placas de redes sociales.

    Se guarda para poder volver a mirarla (historial), pero SIN los archivos
    originales: el PDF del mailing pesa varios MB y las placas de 2250 px otro
    tanto, y la base tiene poca cuota. Lo que queda es lo que hace falta para
    revisar el resultado sin abrir nada aparte: las páginas del mailing ya
    renderizadas, una vista chica de cada placa y los recortes de cada
    diferencia. Ver rrss/validador.py."""

    __tablename__ = "rrss_validaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_mailing: Mapped[str] = mapped_column(String(255), nullable=False)
    # en_proceso | completada
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="en_proceso")
    # Los legales que se exigieron en esta corrida (ver validador.CONFIG_DEFECTO).
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Lo que CatTi leyó del mailing: productos, cajas y recortes.
    mailing: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Lo que solo se ve mirando el lote entero (adaptaciones, CTA); se completa al cerrar.
    resumen: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RrssValidacionPagina(Base):
    """Una página del mailing, ya renderizada (JPEG)."""

    __tablename__ = "rrss_validacion_paginas"

    id: Mapped[int] = mapped_column(primary_key=True)
    validacion_id: Mapped[int] = mapped_column(
        ForeignKey("rrss_validaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    ancho: Mapped[int] = mapped_column(Integer, nullable=False)
    alto: Mapped[int] = mapped_column(Integer, nullable=False)
    imagen: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class RrssValidacionImagen(Base):
    """Una placa validada: qué leyó CatTi, contra qué producto se comparó y
    cada diferencia con sus recortes."""

    __tablename__ = "rrss_validacion_imagenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    validacion_id: Mapped[int] = mapped_column(
        ForeignKey("rrss_validaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    ancho: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alto: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    formato: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    # ok | avisos | diferencias | sin_match | error
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    resultado: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Vista chica de la placa (JPEG) para mostrarla junto al mailing.
    vista: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
