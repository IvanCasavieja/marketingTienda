"""Las validaciones de RRSS duran un día (26/11/2026).

Ivan, al ver que ocupaban 73 MB de la base: «no tiene sentido que mantengamos
historial de validaciones». Una validación (las páginas del mailing ya
renderizadas, la vista chica de cada placa y los recortes de cada diferencia)
queda RRSS_RETENCION_HORAS horas (24), terminada o no: lo justo para terminar
de revisarla y volver a abrirla si se cerró la pestaña. Después se borra
entera. Mismo molde que la purga de cenefas (services/cenefas/jobs.py).

Después de borrar, las tablas se compactan (services/espacio.py, compactar):
si no, Postgres guarda el lugar para sí y la base sigue «llena» para el freno
y para la cuota de Supabase.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.rrss_validacion import RrssValidacion
from app.services.espacio import MB, compactar

logger = logging.getLogger(__name__)

# Las tablas de una validación: lo que se compacta después de borrar.
TABLAS = ("rrss_validacion_imagenes", "rrss_validacion_paginas", "rrss_validaciones")


async def purgar_validaciones_vencidas(horas: int) -> int:
    """Una pasada: borra las validaciones creadas hace más de `horas` horas y
    compacta las tablas si borró alguna. Devuelve cuántas borró. Con 0 (o
    menos) no borra nada: es la llave para apagarla, y un corte en «ahora»
    se llevaría también las de hoy."""
    if horas <= 0:
        return 0
    corte = datetime.now(timezone.utc) - timedelta(hours=horas)
    async with AsyncSessionLocal() as db:
        # Un solo DELETE en la base: las páginas y las placas se van con su
        # validación (ON DELETE CASCADE, migración 0055) y ningún archivo viaja
        # hasta acá. Una sin fecha no puede probar que es de hoy: se va.
        r = await db.execute(
            delete(RrssValidacion)
            .where(or_(RrssValidacion.created_at < corte, RrssValidacion.created_at.is_(None)))
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    borradas = r.rowcount or 0
    if borradas:
        for tabla in TABLAS:
            try:
                antes, despues = await compactar(tabla)
                logger.info("purga_rrss: %s compactada de %.1f a %.1f MB", tabla, antes / MB, despues / MB)
            except Exception as exc:
                logger.error("purga_rrss: no se pudo compactar %s -- %s", tabla, exc)
    return borradas


async def run_purga_rrss_loop() -> None:
    """Loop perpetuo, como el de cenefas: una pasada al arrancar (así el
    primer deploy ya borra todo el historial viejo) y después una por hora:
    con 24 horas de retención, una por día dejaba validaciones hasta 48."""
    while True:
        try:
            borradas = await purgar_validaciones_vencidas(settings.RRSS_RETENCION_HORAS)
            if borradas:
                logger.info("purga_rrss: %d validación(es) borradas", borradas)
        except Exception as exc:
            logger.error("purga_rrss: falló la pasada -- %s", exc, exc_info=True)
        await asyncio.sleep(3600)
