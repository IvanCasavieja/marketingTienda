"""cotizacion_service.py — cotización del dólar BROU, actualizada todos los días a las 8am.

Se usa para convertir precios entre UYU y USD en el gráfico comparativo de
/precios: un producto en dólares no se puede comparar visualmente contra uno
en pesos sin pasarlos a una moneda común.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.cotizacion_dolar import CotizacionDolar

logger = logging.getLogger(__name__)

MONTEVIDEO = ZoneInfo("America/Montevideo")

# Portlet público que BROU usa para renderizar la tabla de cotizaciones en su propio
# sitio (brou.com.uy/cotizaciones) — no hay una API oficial documentada, esta es la
# misma URL que usan varios proyectos open source de terceros para lo mismo.
_BROU_URL = (
    "https://www.brou.com.uy/c/portal/render_portlet"
    "?p_l_id=20593&p_p_id=cotizacionfull_WAR_broutmfportlet_INSTANCE_otHfewh1klyS"
)

_HORA_CHEQUEO = 8  # 8am hora de Montevideo


async def fetch_brou_usd() -> tuple[float, float]:
    """Devuelve (compra, venta) del dólar BROU (fila "Dólar", no "Dólar eBROU")."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_BROU_URL, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    for row in soup.select("table tbody tr"):
        moneda_el = row.select_one("p.moneda")
        if not moneda_el or moneda_el.get_text(strip=True) != "Dólar":
            continue
        valores = row.select("p.valor")
        if len(valores) < 2:
            continue
        compra = float(valores[0].get_text(strip=True).replace(",", "."))
        venta = float(valores[1].get_text(strip=True).replace(",", "."))
        return compra, venta

    raise ValueError("No se encontró la fila 'Dólar' en la tabla de cotizaciones BROU")


async def actualizar_cotizacion_hoy() -> CotizacionDolar:
    """Consulta BROU y guarda (o actualiza) la cotización del día de hoy."""
    compra, venta = await fetch_brou_usd()
    hoy = datetime.now(MONTEVIDEO).date()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CotizacionDolar).where(CotizacionDolar.fecha == hoy))
        registro = result.scalar_one_or_none()
        if registro:
            registro.compra = compra
            registro.venta = venta
        else:
            registro = CotizacionDolar(fecha=hoy, compra=compra, venta=venta, fuente="brou")
            db.add(registro)
        await db.commit()
        await db.refresh(registro)

    logger.info("cotizacion_service: BROU dólar compra=%.2f venta=%.2f (%s)", compra, venta, hoy)
    return registro


async def get_cotizacion_actual() -> CotizacionDolar | None:
    """La cotización guardada más reciente. Si no hay ninguna para hoy, la busca
    y la guarda en el momento — así el gráfico nunca se queda sin conversión por
    depender exclusivamente de que el loop diario ya haya corrido."""
    hoy = datetime.now(MONTEVIDEO).date()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CotizacionDolar).where(CotizacionDolar.fecha == hoy))
        registro = result.scalar_one_or_none()
        if registro:
            return registro

    try:
        return await actualizar_cotizacion_hoy()
    except Exception as exc:
        logger.warning("cotizacion_service: no se pudo obtener la cotización de hoy — %s", exc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CotizacionDolar).order_by(CotizacionDolar.fecha.desc()).limit(1)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Loop diario — a diferencia de auto_sync/watchlist (cada N horas desde el
# último run), esto necesita correr a una hora fija del día.
# ---------------------------------------------------------------------------

async def run_cotizacion_check_loop() -> None:
    """Loop perpetuo. Arranca con FastAPI y corre en background."""
    while True:
        await _sleep_hasta_proximo_chequeo()
        try:
            await actualizar_cotizacion_hoy()
        except Exception as exc:
            logger.error("cotizacion_service: error actualizando cotización — %s", exc, exc_info=True)
            # Reintentar en 1h en vez de esperar hasta mañana — un fallo puntual
            # (BROU caído, timeout) no debería dejar la cotización desactualizada todo el día.
            await asyncio.sleep(3_600)


async def _sleep_hasta_proximo_chequeo() -> None:
    ahora = datetime.now(MONTEVIDEO)
    proximo = ahora.replace(hour=_HORA_CHEQUEO, minute=0, second=0, microsecond=0)
    if proximo <= ahora:
        proximo += timedelta(days=1)
    espera = (proximo - ahora).total_seconds()
    logger.info("cotizacion_service: próximo chequeo BROU en %.1fh (%s)", espera / 3600, proximo.isoformat())
    await asyncio.sleep(espera)
