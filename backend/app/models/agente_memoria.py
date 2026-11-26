"""La memoria de los agentes del Escuadrón Lechuza (0092).

Ivan (25/11/2026): "necesito que estos agentes puedan ser alimentados de
información… que cuando nosotros contestamos esos correos les podamos
enseñar… y que cuestionen nuestras decisiones". Cada nota es algo que el
agente aprendió (de un mail, de un dato, de su propio análisis), con de dónde
salió. Antes de cada tarea la lee entera; cuando algo deja de valer no se
borra: se retira (activo=False) y queda la nota nueva.

Vive en la base (y no en el cuaderno del repo, que es público) porque habla
del negocio y de los clientes. `ambito` separa de qué es: hoy, `clientes_vip`
(Valentina).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgenteMemoria(Base):
    __tablename__ = "agente_memoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agente: Mapped[str] = mapped_column(String(40), nullable=False)
    ambito: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    tema: Mapped[str] = mapped_column(String(120), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    # De dónde salió: «mail de Ivan del 26/11», «búsqueda: calendario comercial UY», «análisis de octubre».
    fuente: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
