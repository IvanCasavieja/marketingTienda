"""Las validaciones de RRSS duran un día (26/11/2026).

Ivan, al ver que ocupaban 73 MB de la base: «no tiene sentido que mantengamos
historial de validaciones». Una validación (las páginas del mailing ya
renderizadas, la vista chica de cada placa y los recortes de cada diferencia)
queda RRSS_RETENCION_HORAS horas (24), terminada o no: lo justo para terminar
de revisarla y volver a abrirla si se cerró la pestaña. Después se borra
entera. Mismo molde que la purga de cenefas (services/cenefas/jobs.py).

Después de borrar, las tablas se compactan (services/espacio.py, compactar):
si no, Postgres guarda el lugar para sí y la base sigue «llena» para el freno
y para la cuota de Supabase. El lazo se acuerda de lo que le falta compactar
(`pendientes`) y lo vuelve a intentar en la pasada siguiente:

- una tabla que se está usando no se compacta, para no trabar a quien la
  usa, y queda para la próxima; lo mismo si compactar falla;
- lo recién borrado se compacta enseguida y otra vez en la pasada siguiente:
  VACUUM FULL se guarda las filas que todavía podría ver una transacción
  empezada antes del borrado, en cualquier base del servidor. Con una así
  abierta, la compactación «andaba» y el lugar no volvía (visto el
  26/11/2026 contra Postgres). Una hora después ya no queda ninguna;
- el lazo arranca con las tres pendientes: si el proceso anterior borró y no
  llegó a compactar (estaban en uso, o se reinició), el lugar vuelve igual.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.rrss_validacion import RrssValidacion
from app.services.espacio import MB, TablaEnUso, compactar

logger = logging.getLogger(__name__)

# Las tablas de una validación: lo que se compacta después de borrar.
TABLAS = ("rrss_validacion_imagenes", "rrss_validacion_paginas", "rrss_validaciones")


async def purgar_validaciones_vencidas(horas: int, pendientes: set[str] | None = None) -> int:
    """Una pasada: borra las validaciones creadas hace más de `horas` horas y
    compacta. Devuelve cuántas borró. Con 0 (o menos) no borra nada: es la
    llave para apagarla, y un corte en «ahora» se llevaría también las de hoy.

    `pendientes` es la memoria del lazo (ver arriba): las tablas que quedaron
    por compactar de antes. Se compactan junto con las de esta pasada y, al
    terminar, queda adentro lo que hay que volver a intentar en la próxima.
    Sin ella, se compacta solo si se borró algo."""
    if horas <= 0:
        return 0
    if pendientes is None:
        pendientes = set()
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
    ahora = (pendientes | set(TABLAS)) if borradas else set(pendientes)
    pendientes.clear()
    if borradas:
        # Otra vez en la próxima pasada: lo recién borrado puede quedar
        # adentro si había una transacción más vieja abierta (ver arriba).
        pendientes.update(TABLAS)
    for tabla in TABLAS:
        if tabla not in ahora:
            continue
        try:
            antes, despues = await compactar(tabla)
            logger.info("purga_rrss: %s compactada de %.1f a %.1f MB", tabla, antes / MB, despues / MB)
        except TablaEnUso:
            pendientes.add(tabla)
            logger.info("purga_rrss: %s se está usando; se compacta en la próxima pasada", tabla)
        except Exception as exc:
            pendientes.add(tabla)
            logger.error("purga_rrss: no se pudo compactar %s (se reintenta en la próxima pasada) -- %s", tabla, exc)
    return borradas


async def run_purga_rrss_loop() -> None:
    """Loop perpetuo, como el de cenefas: una pasada al arrancar (así el
    primer deploy ya borra todo el historial viejo) y después una por hora:
    con 24 horas de retención, una por día dejaba validaciones hasta 48.
    Arranca con las tres tablas pendientes de compactar (ver arriba)."""
    pendientes = set(TABLAS)
    while True:
        try:
            borradas = await purgar_validaciones_vencidas(settings.RRSS_RETENCION_HORAS, pendientes)
            if borradas:
                logger.info("purga_rrss: %d validación(es) borradas", borradas)
        except Exception as exc:
            logger.error("purga_rrss: falló la pasada -- %s", exc, exc_info=True)
        await asyncio.sleep(3600)
