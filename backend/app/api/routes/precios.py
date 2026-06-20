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

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
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

    offset = (page - 1) * page_size
    items_result = await db.execute(
        base.order_by(Producto.nombre).offset(offset).limit(page_size)
    )
    items = items_result.scalars().all()

    return PreciosListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ProductoOut.model_validate(p) for p in items],
    )


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
