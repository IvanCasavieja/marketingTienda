"""El freno de espacio de la base, para todo lo que guarda archivos.

La base de producción es un Postgres gratis de 500 MB para TODA la plataforma
(calendario, cenefas, precios, fotos, piezas). Si se llena, deja de aceptar
escrituras y se cae todo, no solo lo que la llenó. Por eso, antes de guardar
una imagen se mira cuánto ocupa la base entera: pasado BASE_TOPE_MB (400 por
defecto, con margen para el resto) se rechaza la subida con un mensaje para la
persona y queda un error en el log, en vez de llenarla.
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

MENSAJE_SIN_LUGAR = (
    "La base de Core Tienda está casi llena y por ahora no se pueden subir más imágenes. "
    "Avisale a quien administra la plataforma."
)


def entra(ocupado_bytes: int, nuevo_bytes: int, tope_mb: int) -> bool:
    """Si `nuevo_bytes` entran sin pasar el tope. Con tope 0 o menos, sin tope."""
    return tope_mb <= 0 or ocupado_bytes + nuevo_bytes <= tope_mb * 1024 * 1024


async def hay_lugar(db: AsyncSession, nuevo_bytes: int) -> bool:
    """Si la base entera tiene lugar para `nuevo_bytes` más. Si no se puede
    medir (otra base, sin permiso), no frena: el tope propio de cada cosa sigue."""
    try:
        ocupado = (await db.execute(text("SELECT pg_database_size(current_database())"))).scalar_one()
    except Exception as exc:  # pragma: no cover - depende de la base
        logger.warning("espacio: no se pudo medir la base: %s", exc)
        return True
    if entra(int(ocupado), nuevo_bytes, settings.BASE_TOPE_MB):
        return True
    logger.error(
        "espacio: la base ocupa %.0f MB y el tope es %d MB: se rechazó una subida de %d KB",
        ocupado / 1024 / 1024, settings.BASE_TOPE_MB, nuevo_bytes // 1024,
    )
    return False
