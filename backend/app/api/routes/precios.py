"""
precios.py — búsqueda EN VIVO de precios de supermercados uruguayos.

  GET  /precios/buscar-vivo        — búsqueda sincrónica (no SSE)
  GET  /precios/buscar-vivo-stream — búsqueda SSE cadena por cadena
  POST /precios/ia/consultar       — Doña Tina responde preguntas o filtra resultados por lenguaje natural
  POST /precios/ia/reporte         — Doña Tina genera un reporte escrito del gráfico
  GET  /precios/cotizacion-dolar   — cotización BROU del día, para convertir el gráfico entre UYU/USD
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_permission, client_ip as _client_ip
from app.core.rate_limit import limiter
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.ai_usage_service import resumir_usage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/precios", tags=["precios"])


@router.get("/buscar-vivo")
@limiter.limit("20/minute")
async def buscar_vivo(
    request: Request,
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    """Búsqueda EN VIVO de un producto — no usa la base de datos, golpea las
    APIs de Ta-Ta, El Dorado, GDU, FarmaShop y Botiga en paralelo."""
    db.add(AuditLog(
        user_id=current_user.id, action="precios.search",
        details={"query": q}, ip_address=_client_ip(request),
    ))
    import asyncio
    loop = asyncio.get_running_loop()
    try:
        from app.services.scraper.live_search import buscar_todas_cached
        resultados = await asyncio.wait_for(
            loop.run_in_executor(None, buscar_todas_cached, q),
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
@limiter.limit("20/minute")
async def buscar_vivo_stream(
    request: Request,
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    cadenas: Optional[str] = Query(
        None,
        description="Cadenas a consultar, separadas por coma. Si se omite, se usan las cadenas por defecto (LOi queda afuera salvo que se la seleccione a propósito).",
    ),
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    """Búsqueda EN VIVO con SSE — devuelve resultados cadena por cadena en cuanto
    cada una termina. Evita el timeout de 30s de Render free tier porque los headers
    HTTP (incluyendo CORS) se envían con el primer byte, antes de que cualquier
    cadena termine.

    Al margen de esa transmisión progresiva por cadena, el resultado FINAL que se
    marca como relevante para el frontend pasa por dos pasadas de Doña Tina una vez
    que terminaron TODAS las cadenas con el término original:
      1) generar_sinonimos_busqueda + un reintento SOLO en las cadenas que no
         encontraron nada -- score_match no puede arreglar que "perfume" no
         encuentre perfumes reales si sus nombres dicen "EDT"/"EDP"/"PARFUM" (ver
         docstring de esa función); es un problema de vocabulario de búsqueda, no
         de relevancia de resultados ya traídos.
      2) filtrar_relevancia_automatica sobre el conjunto ya ensanchado -- acá sí es
         relevancia real: que "Refrigerador JAMES" no pase para una búsqueda de
         lavarropas, aunque la marca coincida.
    Ambas fail-open: si Claude falla en cualquiera de las dos, se sigue con lo que
    ya se tenía en vez de romper la búsqueda entera."""
    # Se loguea la intención de búsqueda ACA, antes de cualquier ramificación
    # (barcode/stream normal/corte de conexión) -- viaja en el commit
    # implícito de get_db() o en el explícito que ya tiene esta función más
    # abajo, lo que ocurra primero, así que no hace falta un commit propio.
    db.add(AuditLog(
        user_id=current_user.id, action="precios.search",
        details={"query": q, "cadenas": cadenas}, ip_address=_client_ip(request),
    ))
    import asyncio, json, threading
    from app.services.scraper.live_search import buscar_todas_streaming_cached, _DATA_DIR, _CADENAS_DEFAULT, _CADENAS_TODAS
    from app.services.dona_tina_precios import filtrar_relevancia_automatica, generar_sinonimos_busqueda

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

    # "GDU" es una fuente paraguas (Disco/Devoto/Géant) -- cada producto vuelve
    # etiquetado con su tienda real, "GDU" como string nunca aparece en un item
    # (mismo caso especial que ya maneja el frontend en cadenasSinResultado).
    _GDU_MIEMBROS = {"Disco", "Devoto", "Geant"}

    def _cadena_sin_resultados(cadena: str, items_totales: list[dict]) -> bool:
        if cadena == "GDU":
            return not any(it["tienda"] in _GDU_MIEMBROS for it in items_totales)
        return not any(it["tienda"] == cadena for it in items_totales)

    def _record_a_dict(r) -> dict:
        return {
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

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run_search():
        try:
            for cadena, records, error in buscar_todas_streaming_cached(search_term, _DATA_DIR, cadenas_seleccionadas):
                try:
                    items = [_record_a_dict(r) for r in records if r.nombre and r.precio]
                    payload: dict = {"cadena": cadena, "items": items}
                    if error:
                        payload["error"] = error
                    # Se manda el dict crudo (no pre-serializado) -- generate() necesita
                    # los items en Python para acumularlos y correr el filtro final de
                    # Doña Tina antes de mandar el evento "done".
                    loop.call_soon_threadsafe(queue.put_nowait, payload)
                    logger.info("buscar_vivo_stream: %s OK — %d items para '%s'", cadena, len(items), q)
                except Exception as chain_exc:
                    logger.error("buscar_vivo_stream: error serializando %s — %s", cadena, chain_exc, exc_info=True)
                    fallback = {"cadena": cadena, "items": [], "error": f"Error interno: {chain_exc}"}
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
        items_totales: list[dict] = []
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
                # Todas las cadenas terminaron con el término original -- antes de
                # revisar relevancia, se detectan las cadenas que no encontraron NADA
                # y se les da una segunda chance con sinónimos (ver
                # generar_sinonimos_busqueda: "perfume" no encuentra perfumes reales
                # si el catálogo los nombra "EDT"/"EDP"). Solo se ensanchan esas
                # cadenas puntuales, nunca las 15 de nuevo -- no tiene sentido
                # repetir una búsqueda que ya encontró algo con el término tal cual.
                cadenas_pedidas = cadenas_seleccionadas or _CADENAS_DEFAULT
                cadenas_pobres = [c for c in cadenas_pedidas if _cadena_sin_resultados(c, items_totales)]
                if cadenas_pobres:
                    try:
                        sinonimos = await generar_sinonimos_busqueda(search_term, db, current_user.id)
                    except Exception as exc:
                        logger.warning("buscar_vivo_stream: fallo generando sinónimos para '%s' — %s", q, exc)
                        sinonimos = []
                    if sinonimos:
                        logger.info(
                            "buscar_vivo_stream: ensanchando %s con sinónimos %s para '%s'",
                            cadenas_pobres, sinonimos, q,
                        )

                        async def _buscar_sinonimo(termino_alt: str) -> list[dict]:
                            try:
                                resultado = await asyncio.to_thread(
                                    lambda: list(buscar_todas_streaming_cached(termino_alt, _DATA_DIR, cadenas_pobres))
                                )
                            except Exception as exc:
                                logger.warning("buscar_vivo_stream: fallo ensanchando con '%s' — %s", termino_alt, exc)
                                return []
                            return [
                                _record_a_dict(r)
                                for _, records, _ in resultado
                                for r in records
                                if r.nombre and r.precio
                            ]

                        # En paralelo -- ensanchar con 3 sinónimos no debería tardar
                        # 3 veces más que ensanchar con uno solo.
                        for extra in await asyncio.gather(*(_buscar_sinonimo(s) for s in sinonimos)):
                            items_totales.extend(extra)

                # Con el conjunto ya ensanchado, Doña Tina revisa la relevancia real
                # (no cadena por cadena: la decisión de si "Refrigerador JAMES"
                # corresponde a una búsqueda de lavarropas es la misma sin importar
                # de qué sitio vino). Fail-open: si la IA falla, se manda todo sin
                # filtrar antes que romper la búsqueda entera.
                try:
                    filtro = await filtrar_relevancia_automatica(search_term, items_totales, db, current_user.id)
                    await db.commit()  # persiste el ai_usage_log acumulado
                    indices = set(filtro["indices_mantener"])
                    items_filtrados = [it for i, it in enumerate(items_totales) if i in indices]
                    conteo_por_marca = filtro["conteo_por_marca"]
                except Exception as exc:
                    logger.error("buscar_vivo_stream: fallo el filtro de Doña Tina para '%s' — %s", q, exc, exc_info=True)
                    items_filtrados = items_totales
                    conteo_por_marca = {}
                yield "data: " + json.dumps({
                    "done": True,
                    "items_filtrados": items_filtrados,
                    "conteo_por_marca": conteo_por_marca,
                }) + "\n\n"
                break
            items_totales.extend(msg.get("items") or [])
            yield f"data: {json.dumps(msg)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Doña Tina + IA sobre los resultados — stateless, no persiste nada ni dispara
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
@limiter.limit("15/minute")
async def ia_consultar(
    request: Request,
    payload: ConsultarRequest,
    current_user: User = Depends(require_permission("ai.dona_tina")),
    db: AsyncSession = Depends(get_db),
):
    if not payload.items:
        return {"tipo": "respuesta", "mantener": None, "respuesta": "No hay productos para analizar todavía."}

    from app.services.dona_tina_precios import responder_consulta

    try:
        resultado = await responder_consulta(
            payload.termino,
            [it.model_dump() for it in payload.items],
            payload.mensaje,
            db, current_user.id,
        )
    except Exception as exc:
        logger.error("ia_consultar: error para '%s' — %s", payload.termino, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude procesar el pedido en este momento")

    usage_items = resultado.pop("usage_items", [])
    resultado["usage"] = resumir_usage(usage_items)
    return resultado


@router.post("/ia/reporte")
@limiter.limit("15/minute")
async def ia_reporte(
    request: Request,
    payload: ReporteRequest,
    current_user: User = Depends(require_permission("ai.dona_tina")),
    db: AsyncSession = Depends(get_db),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="No hay productos seleccionados para el reporte")

    from app.services.dona_tina_precios import generar_reporte

    try:
        reporte, usage_items = await generar_reporte(
            [it.model_dump() for it in payload.items],
            payload.nuestro_precio,
            payload.nuestra_moneda,
            db, current_user.id,
        )
        return {"reporte": reporte, "usage": resumir_usage(usage_items)}
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
