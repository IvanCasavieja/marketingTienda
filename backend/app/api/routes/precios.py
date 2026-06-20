"""
precios.py — catálogo de precios de supermercados uruguayos.

Endpoints públicos (requieren JWT de usuario):
  GET  /precios              — lista paginada con filtros
  GET  /precios/tiendas      — tiendas disponibles
  GET  /precios/categorias   — categorías disponibles
  GET  /precios/{id}         — detalle de un producto

Endpoint de sincronización (requiere APP_SECRET_KEY en header X-Sync-Key):
  POST /precios/sync         — bulk upsert desde el scraper (INSERT ... ON CONFLICT)
"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.producto import Producto
from app.models.user import User
from app.schemas.precios import (
    ProductoOut, SyncPayload, SyncResult, PreciosListResponse,
    CompararResponse, CompararGrupo, CompararTiendaItem,
    PreciosStats, TiendaStats,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/precios", tags=["precios"])

_sync_key_scheme = APIKeyHeader(name="X-Sync-Key", auto_error=False)


async def _require_sync_key(key: Optional[str] = Depends(_sync_key_scheme)):
    if not key or key != settings.APP_SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sync key inválida")


# ---------------------------------------------------------------------------
# Sync endpoint — llamado por el scraper
# ---------------------------------------------------------------------------

@router.post("/sync", response_model=SyncResult, dependencies=[Depends(_require_sync_key)])
async def sync_productos(payload: SyncPayload, db: AsyncSession = Depends(get_db)):
    """Bulk upsert via PostgreSQL INSERT ... ON CONFLICT DO UPDATE.
    Un solo statement por batch — eficiente para 45k+ productos.
    """
    if not payload.productos:
        return SyncResult(upsertados=0, total_enviados=0)

    now = datetime.now(timezone.utc)
    rows = []
    for item in payload.productos:
        ts = None
        if item.actualizado_en:
            try:
                ts = datetime.fromisoformat(item.actualizado_en)
            except ValueError:
                ts = now
        rows.append({
            "tienda":        item.tienda,
            "url":           item.url,
            "nombre":        item.nombre,
            "precio":        item.precio,
            "precio_lista":  item.precio_lista,
            "sku":           item.sku,
            "barcode":       item.barcode,
            "marca":         item.marca,
            "categoria":     item.categoria,
            "actualizado_en": ts or now,
        })

    stmt = pg_insert(Producto).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["url"],
        set_={
            "tienda":        stmt.excluded.tienda,
            "nombre":        stmt.excluded.nombre,
            "precio":        stmt.excluded.precio,
            "precio_lista":  stmt.excluded.precio_lista,
            "sku":           stmt.excluded.sku,
            "barcode":       stmt.excluded.barcode,
            "marca":         stmt.excluded.marca,
            "categoria":     stmt.excluded.categoria,
            "actualizado_en": stmt.excluded.actualizado_en,
        },
    )

    await db.execute(stmt)
    logger.info("sync_productos: %d upsertados", len(rows))
    return SyncResult(upsertados=len(rows), total_enviados=len(payload.productos))


# ---------------------------------------------------------------------------
# Endpoints de lectura
# ---------------------------------------------------------------------------

@router.get("/tiendas", response_model=list[str])
async def listar_tiendas(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(Producto.tienda).distinct().order_by(Producto.tienda)
    )
    return [r[0] for r in rows.all()]


@router.get("/estadisticas", response_model=PreciosStats)
async def estadisticas_precios(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resumen estadístico del catálogo de precios por tienda."""
    from sqlalchemy import case, Integer, cast
    desc_expr = cast(
        case(
            (
                Producto.precio_lista.isnot(None) & (Producto.precio_lista > Producto.precio),
                1,
            ),
            else_=0,
        ),
        Integer,
    )
    rows = await db.execute(
        select(
            Producto.tienda,
            func.count().label("total"),
            func.sum(desc_expr).label("con_descuento"),
            func.avg(Producto.precio).label("precio_promedio"),
        ).group_by(Producto.tienda).order_by(Producto.tienda)
    )
    tiendas = []
    total_global = 0
    for tienda, total, con_desc, avg_precio in rows.all():
        tiendas.append(TiendaStats(
            tienda=tienda,
            total=total,
            con_descuento=int(con_desc or 0),
            precio_promedio=round(float(avg_precio), 2) if avg_precio else None,
        ))
        total_global += total
    return PreciosStats(total_productos=total_global, tiendas=tiendas)


@router.get("/categorias", response_model=list[str])
async def listar_categorias(
    tienda: Optional[str] = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Producto.categoria).distinct().where(Producto.categoria.isnot(None))
    if tienda:
        q = q.where(Producto.tienda == tienda)
    rows = await db.execute(q.order_by(Producto.categoria))
    return [r[0] for r in rows.all()]


@router.get("", response_model=PreciosListResponse)
async def listar_precios(
    tienda:     Optional[str]   = Query(None),
    categoria:  Optional[str]   = Query(None),
    marca:      Optional[str]   = Query(None),
    q:          Optional[str]   = Query(None, description="Búsqueda por nombre, SKU o barcode"),
    precio_min:    Optional[float] = Query(None),
    precio_max:    Optional[float] = Query(None),
    con_descuento: Optional[bool]  = Query(None, description="Solo productos con descuento activo"),
    sort_by:       Optional[str]   = Query(None, description="Campo de ordenamiento: nombre|precio|tienda|categoria"),
    sort_dir:      Optional[str]   = Query("asc", description="Dirección: asc|desc"),
    page:          int             = Query(1, ge=1),
    page_size:     int             = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base    = select(Producto)
    count_q = select(func.count()).select_from(Producto)

    filters = []
    if tienda:
        filters.append(Producto.tienda == tienda)
    if categoria:
        filters.append(Producto.categoria.ilike(f"%{categoria}%"))
    if marca:
        filters.append(Producto.marca.ilike(f"%{marca}%"))
    if q:
        like = f"%{q}%"
        filters.append(
            Producto.nombre.ilike(like) |
            Producto.sku.ilike(like)    |
            Producto.barcode.ilike(like)
        )
    if precio_min is not None:
        filters.append(Producto.precio >= precio_min)
    if precio_max is not None:
        filters.append(Producto.precio <= precio_max)
    if con_descuento:
        filters.append(
            Producto.precio_lista.isnot(None) &
            (Producto.precio_lista > Producto.precio)
        )

    for f in filters:
        base    = base.where(f)
        count_q = count_q.where(f)

    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    _sort_cols = {
        "nombre":    Producto.nombre,
        "precio":    Producto.precio,
        "tienda":    Producto.tienda,
        "categoria": Producto.categoria,
    }
    sort_col = _sort_cols.get(sort_by or "nombre", Producto.nombre)
    order_expr = sort_col.desc() if sort_dir == "desc" else sort_col.asc()

    offset = (page - 1) * page_size
    items_result = await db.execute(
        base.order_by(order_expr).offset(offset).limit(page_size)
    )
    items = items_result.scalars().all()

    return PreciosListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ProductoOut.model_validate(p) for p in items],
    )


@router.get("/comparar", response_model=CompararResponse)
async def comparar_precios(
    q:       Optional[str] = Query(None, description="Búsqueda por nombre o barcode"),
    barcode: Optional[str] = Query(None, description="Barcode exacto"),
    limit:   int           = Query(30, ge=1, le=100),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Compara el mismo producto (por barcode) en distintas tiendas.
    Agrupa productos con barcode compartido entre >=2 tiendas.
    """
    base = select(Producto).where(Producto.barcode.isnot(None), Producto.barcode != "")

    if barcode:
        base = base.where(Producto.barcode == barcode)
    elif q:
        like = f"%{q}%"
        base = base.where(
            Producto.nombre.ilike(like) | Producto.barcode.ilike(like)
        )
    else:
        return CompararResponse(grupos=[], total=0)

    result = await db.execute(base.order_by(Producto.barcode, Producto.tienda))
    rows = result.scalars().all()

    from collections import defaultdict
    by_barcode: dict[str, list] = defaultdict(list)
    for p in rows:
        by_barcode[p.barcode].append(p)

    grupos = []
    for bc, prods in by_barcode.items():
        tiendas_set = {p.tienda for p in prods}
        if len(tiendas_set) < 2:
            continue
        nombre_ref = next((p.nombre for p in prods if p.nombre), None)
        items = [
            CompararTiendaItem(
                tienda=p.tienda,
                precio=p.precio,
                precio_lista=p.precio_lista,
                url=p.url,
                nombre=p.nombre,
            )
            for p in sorted(prods, key=lambda x: x.tienda)
        ]
        grupos.append(CompararGrupo(
            barcode=bc,
            nombre_ref=nombre_ref,
            n_tiendas=len(tiendas_set),
            tiendas=items,
        ))

    grupos.sort(key=lambda g: -g.n_tiendas)
    grupos = grupos[:limit]
    return CompararResponse(grupos=grupos, total=len(grupos))


@router.get("/export.csv")
async def exportar_csv(
    tienda:     Optional[str]   = Query(None),
    categoria:  Optional[str]   = Query(None),
    marca:      Optional[str]   = Query(None),
    q:          Optional[str]   = Query(None),
    precio_min: Optional[float] = Query(None),
    precio_max: Optional[float] = Query(None),
    con_descuento: Optional[bool] = Query(None),
    limit:      int             = Query(10000, ge=1, le=50000),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exporta el catálogo filtrado como CSV."""
    base = select(Producto)
    filters = []
    if tienda:        filters.append(Producto.tienda == tienda)
    if categoria:     filters.append(Producto.categoria.ilike(f"%{categoria}%"))
    if marca:         filters.append(Producto.marca.ilike(f"%{marca}%"))
    if q:
        like = f"%{q}%"
        filters.append(
            Producto.nombre.ilike(like) | Producto.sku.ilike(like) | Producto.barcode.ilike(like)
        )
    if precio_min is not None: filters.append(Producto.precio >= precio_min)
    if precio_max is not None: filters.append(Producto.precio <= precio_max)
    if con_descuento:
        filters.append(Producto.precio_lista.isnot(None) & (Producto.precio_lista > Producto.precio))
    for f in filters:
        base = base.where(f)

    result = await db.execute(base.order_by(Producto.nombre).limit(limit))
    items = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["tienda","nombre","precio","precio_lista","sku","barcode","marca","categoria","url"])
    for p in items:
        writer.writerow([
            p.tienda, p.nombre, p.precio, p.precio_lista,
            p.sku, p.barcode, p.marca, p.categoria, p.url,
        ])

    filename = f"precios_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/scraper/status")
async def scraper_status(_: User = Depends(get_current_user)):
    """Estado del scheduler nocturno de scraping."""
    from app.services.scraper_sync import get_status
    return await get_status()


@router.post("/scraper/trigger", status_code=202)
async def scraper_trigger(_: User = Depends(get_current_user)):
    """Dispara un scraping manual inmediato (si no hay otro corriendo)."""
    from app.services.scraper_sync import trigger_manual
    launched = await trigger_manual()
    if not launched:
        raise HTTPException(status_code=409, detail="Ya hay un scraping en curso")
    return {"message": "Scraping iniciado"}


@router.get("/{producto_id}", response_model=ProductoOut)
async def obtener_precio(
    producto_id: int,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Producto).where(Producto.id == producto_id))
    prod = result.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return ProductoOut.model_validate(prod)
