from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CenefaDestino(Base):
    """Un "mundo" de cenefas: Redexpres, Rompe Precios, Parrilla y Vinos...

    Hasta 08/2026 los destinos eran una unión de strings hardcodeada en el
    frontend y en el backend, así que sumar uno nuevo ("Mega Rompe Precios")
    exigía tocar código y desplegar. Ahora son filas: el equipo los crea
    desde el selector de mundos.

    El destino no cambia cómo se procesa nada -- las variables, el Excel y el
    motor de render son los mismos para todos. Solo agrupa las plantillas de
    cada campaña para que el picker no mezcle diseños de mundos distintos.
    """

    __tablename__ = "cenefa_destinos"

    # El slug es la clave: es lo que queda guardado en
    # cenefa_templates_v2.category y lo que viaja en la URL (?destino=...).
    slug: Mapped[str] = mapped_column(String(50), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # Nombre de un ícono de lucide-react, de una lista corta que el frontend
    # conoce (ver ICONOS en DestinoModal.tsx). Se guarda el nombre, no el
    # componente: un ícono desconocido cae a uno por defecto en vez de romper.
    icono: Mapped[str] = mapped_column(String(40), nullable=False, default="Store")
    # Token de color de la paleta de Tailwind ya presente en el proyecto
    # (ej. "emerald", "rose"). Mismo criterio que el ícono.
    color: Mapped[str] = mapped_column(String(30), nullable=False, default="emerald")
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
