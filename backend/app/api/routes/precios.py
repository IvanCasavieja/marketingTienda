"""
precios.py — búsqueda EN VIVO de precios de supermercados uruguayos.

  GET  /precios/buscar-vivo        — búsqueda sincrónica (no SSE)
  GET  /precios/buscar-vivo-stream — búsqueda SSE cadena por cadena
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

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
    _: User = Depends(require_permission("precios.search")),
):
    """Búsqueda EN VIVO con SSE — devuelve resultados cadena por cadena en cuanto
    cada una termina. Evita el timeout de 30s de Render free tier porque los headers
    HTTP (incluyendo CORS) se envían con el primer byte, antes de que cualquier
    cadena termine."""
    import asyncio, json, threading
    from app.services.scraper.live_search import buscar_todas_streaming, _DATA_DIR

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
            for cadena, records, error in buscar_todas_streaming(search_term, _DATA_DIR):
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
