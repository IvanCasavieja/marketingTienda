"""
precios.py — búsqueda EN VIVO de precios de supermercados uruguayos.

  GET  /precios/buscar-vivo        — búsqueda sincrónica (no SSE)
  GET  /precios/buscar-vivo-stream — búsqueda SSE cadena por cadena
  POST /precios/ia/consultar       — Don Tino responde preguntas o filtra resultados por lenguaje natural
  POST /precios/ia/reporte         — Don Tino genera un reporte escrito del gráfico
  GET  /precios/cotizacion-dolar   — cotización BROU del día, para convertir el gráfico entre UYU/USD
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/precios", tags=["precios"])


@router.get("/buscar-vivo")
async def buscar_vivo(
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    _: User = Depends(require_permission("precios.search")),
):
    """Búsqueda EN VIVO de un producto — no usa la base de datos, golpea las
    APIs de Ta-Ta, El Dorado, GDU, FarmaShop y Botiga en paralelo."""
    import asyncio
    loop = asyncio.get_running_loop()
    try:
        from app.services.scraper.live_search import buscar_todas
        resultados = await asyncio.wait_for(
            loop.run_in_executor(None, buscar_todas, q),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="La búsqueda tardó demasiado. Probá con menos palabras.")
    except Exception as exc:
        logger.error("buscar_vivo: error para '%s': %s", q, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno en búsqueda en vivo")

    items = []
    for records in resultados.values():
        for r in records:
            items.append({
                "tienda":          r.tienda,
                "nombre":          r.nombre,
                "precio":          r.precio,
                "precio_lista":    r.precio_lista,
                "sku":             r.sku,
                "barcode":         r.barcode,
                "marca":           r.marca,
                "url":             r.url,
                "sucursal_id":     r.sucursal_id,
                "sucursal_nombre": r.sucursal_nombre,
                "relevancia":      r.relevancia,
                "moneda":          r.moneda,
                "tienda_real":     r.tienda_real,
            })

    return {"query": q, "total": len(items), "items": items}


def _resolver_barcode(barcode: str) -> str | None:
    """Consulta Open Food Facts para obtener el nombre de un producto por EAN."""
    import requests as _req
    try:
        r = _req.get(
            f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json",
            headers={"User-Agent": "MarketingTienda/1.0"},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == 1:
                product = data.get("product", {})
                return (
                    product.get("product_name_es")
                    or product.get("product_name")
                    or product.get("generic_name_es")
                    or product.get("generic_name")
                )
    except Exception:
        pass
    return None


@router.get("/buscar-vivo-stream")
async def buscar_vivo_stream(
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    cadenas: Optional[str] = Query(
        None,
        description="Cadenas a consultar, separadas por coma. Si se omite, se usan las cadenas por defecto (LOi queda afuera salvo que se la seleccione a propósito).",
    ),
    _: User = Depends(require_permission("precios.search")),
):
    """Búsqueda EN VIVO con SSE — devuelve resultados cadena por cadena en cuanto
    cada una termina. Evita el timeout de 30s de Render free tier porque los headers
    HTTP (incluyendo CORS) se envían con el primer byte, antes de que cualquier
    cadena termine."""
    import asyncio, json, threading
    from app.services.scraper.live_search import buscar_todas_streaming, _DATA_DIR, _CADENAS_TODAS

    # Filtramos contra la lista real de cadenas soportadas — así un valor
    # desconocido o vacío nunca rompe la búsqueda, simplemente se ignora.
    cadenas_seleccionadas: Optional[list[str]] = None
    if cadenas:
        pedidas = {c.strip() for c in cadenas.split(",") if c.strip()}
        validas = [c for c in _CADENAS_TODAS if c in pedidas]
        if validas:
            cadenas_seleccionadas = validas

    # Si el término es puramente numérico, resolver barcode → nombre via Open Food Facts
    search_term = q.strip()
    if search_term.isdigit():
        nombre = await asyncio.get_event_loop().run_in_executor(
            None, _resolver_barcode, search_term
        )
        if nombre:
            search_term = nombre
        else:
            async def _not_found():
                payload = json.dumps({
                    "done": True,
                    "error": f"Código {search_term} no encontrado. Probá buscar por nombre del producto.",
                })
                yield f"data: {payload}\n\n"
            return StreamingResponse(_not_found(), media_type="text/event-stream")

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run_search():
        try:
            for cadena, records, error in buscar_todas_streaming(search_term, _DATA_DIR, cadenas_seleccionadas):
                try:
                    items = [
                        {
                            "tienda":          r.tienda,
                            "nombre":          r.nombre,
                            "precio":          r.precio,
                            "precio_lista":    r.precio_lista,
                            "sku":             r.sku,
                            "barcode":         r.barcode,
                            "marca":           r.marca,
                            "url":             r.url,
                            "sucursal_id":     r.sucursal_id,
                            "sucursal_nombre": r.sucursal_nombre,
                            "relevancia":      r.relevancia,
                            "moneda":          r.moneda,
                            "tienda_real":     r.tienda_real,
                        }
                        for r in records
                        if r.nombre and r.precio
                    ]
                    payload: dict = {"cadena": cadena, "items": items}
                    if error:
                        payload["error"] = error
                    loop.call_soon_threadsafe(queue.put_nowait, json.dumps(payload))
                    logger.info("buscar_vivo_stream: %s OK — %d items para '%s'", cadena, len(items), q)
                except Exception as chain_exc:
                    logger.error("buscar_vivo_stream: error serializando %s — %s", cadena, chain_exc, exc_info=True)
                    fallback = json.dumps({"cadena": cadena, "items": [], "error": f"Error interno: {chain_exc}"})
                    loop.call_soon_threadsafe(queue.put_nowait, fallback)
        except Exception as exc:
            logger.error("buscar_vivo_stream: error iterando cadenas para '%s' — %s", q, exc, exc_info=True)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    threading.Thread(target=_run_search, daemon=True).start()

    async def generate():
        # Heartbeat every 5s — prevents Render/proxy from closing the connection
        # during the 20-30s gap while El Dorado / Ta-Ta are resolving timeouts.
        deadline = loop.time() + 120.0
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.error("buscar_vivo_stream: timeout total para '%s'", q)
                yield 'data: {"done":true,"error":"timeout"}\n\n'
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=min(5.0, remaining))
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"  # SSE comment — browsers ignore, proxies see data
                continue
            if msg is None:
                yield 'data: {"done":true}\n\n'
                break
            yield f"data: {msg}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Don Tino + IA sobre los resultados — stateless, no persiste nada ni dispara
# scraping. Opera sobre los items que el frontend ya trajo con la búsqueda en
# vivo de ese momento.
# ---------------------------------------------------------------------------

class _ItemConPrecio(BaseModel):
    tienda: str
    nombre: str
    precio: float
    moneda: str


class ConsultarRequest(BaseModel):
    termino: str
    items: list[_ItemConPrecio]
    mensaje: str


class ReporteRequest(BaseModel):
    items: list[_ItemConPrecio]
    nuestro_precio: Optional[float] = None
    nuestra_moneda: Optional[str] = None


@router.post("/ia/consultar")
async def ia_consultar(
    payload: ConsultarRequest,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    if not payload.items:
        return {"tipo": "respuesta", "mantener": None, "respuesta": "No hay productos para analizar todavía."}

    from app.services.don_tino_precios import responder_consulta

    try:
        return await responder_consulta(
            payload.termino,
            [it.model_dump() for it in payload.items],
            payload.mensaje,
            db, current_user.id,
        )
    except Exception as exc:
        logger.error("ia_consultar: error para '%s' — %s", payload.termino, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude procesar el pedido en este momento")


@router.post("/ia/reporte")
async def ia_reporte(
    payload: ReporteRequest,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="No hay productos seleccionados para el reporte")

    from app.services.don_tino_precios import generar_reporte

    try:
        reporte = await generar_reporte(
            [it.model_dump() for it in payload.items],
            payload.nuestro_precio,
            payload.nuestra_moneda,
            db, current_user.id,
        )
        return {"reporte": reporte}
    except Exception as exc:
        logger.error("ia_reporte: error generando reporte — %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude generar el reporte en este momento")


@router.get("/cotizacion-dolar")
async def cotizacion_dolar(
    _: User = Depends(require_permission("precios.search")),
):
    """Cotización BROU del día — usada para convertir el gráfico comparativo entre UYU y USD."""
    from app.services.cotizacion_service import get_cotizacion_actual

    registro = await get_cotizacion_actual()
    if not registro:
        raise HTTPException(status_code=503, detail="No se pudo obtener la cotización del dólar")

    return {
        "fecha": registro.fecha.isoformat(),
        "compra": registro.compra,
        "venta": registro.venta,
        "fuente": registro.fuente,
    }
