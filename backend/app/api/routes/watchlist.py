"""
watchlist.py — listas de monitoreo de precios + notificaciones.

  GET    /watchlist                        — listas del usuario con sus items
  POST   /watchlist                         — crear lista
  DELETE /watchlist/{id}                    — eliminar lista (cascade a items + historial)
  POST   /watchlist/{id}/items              — agregar producto a una lista
  DELETE /watchlist/items/{item_id}         — sacar un producto de una lista
  GET    /notificaciones                    — recientes del usuario
  GET    /notificaciones/no-leidas/count    — para el badge del bell
  POST   /notificaciones/{id}/marcar-leida
  POST   /notificaciones/marcar-todas-leidas
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.watchlist_item import WatchlistItem
from app.models.watchlist_precio_historial import WatchlistPrecioHistorial
from app.models.notificacion import Notificacion

logger = logging.getLogger(__name__)
router = APIRouter(tags=["watchlist"])


# ── Listas de monitoreo ───────────────────────────────────────────────────────

class CrearWatchlistRequest(BaseModel):
    nombre: str


class AgregarItemRequest(BaseModel):
    tienda: str
    sku: Optional[str] = None
    nombre: str
    termino_busqueda: str
    url: str
    precio: float
    moneda: str
    # Ta-Ta/ElDorado/GDU tienen precio distinto por sucursal — sin esto el
    # chequeo diario no puede saber cuál sucursal seguir (ver watchlist_service.py).
    sucursal_id: Optional[str] = None
    sucursal_nombre: Optional[str] = None


def _item_to_dict(item: WatchlistItem) -> dict:
    return {
        "id": item.id,
        "watchlist_id": item.watchlist_id,
        "tienda": item.tienda,
        "sku": item.sku,
        "nombre": item.nombre,
        "termino_busqueda": item.termino_busqueda,
        "url": item.url,
        "precio_actual": item.precio_actual,
        "moneda": item.moneda,
        "sucursal_id": item.sucursal_id,
        "sucursal_nombre": item.sucursal_nombre,
        "ultimo_chequeo": item.ultimo_chequeo.isoformat() if item.ultimo_chequeo else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("/watchlist")
async def listar_watchlists(
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id).order_by(Watchlist.created_at)
    )
    listas = result.scalars().all()
    if not listas:
        return []

    items_result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.watchlist_id.in_([l.id for l in listas]))
    )
    items_por_lista: dict[int, list[WatchlistItem]] = {}
    for item in items_result.scalars().all():
        items_por_lista.setdefault(item.watchlist_id, []).append(item)

    return [
        {
            "id": l.id,
            "nombre": l.nombre,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "items": [_item_to_dict(it) for it in items_por_lista.get(l.id, [])],
        }
        for l in listas
    ]


@router.post("/watchlist", status_code=201)
async def crear_watchlist(
    payload: CrearWatchlistRequest,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    nombre = payload.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre de la lista no puede estar vacío")

    lista = Watchlist(user_id=current_user.id, nombre=nombre)
    db.add(lista)
    await db.commit()
    await db.refresh(lista)
    return {"id": lista.id, "nombre": lista.nombre, "created_at": lista.created_at.isoformat(), "items": []}


@router.delete("/watchlist/{watchlist_id}", status_code=204)
async def eliminar_watchlist(
    watchlist_id: int,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == current_user.id)
    )
    lista = result.scalar_one_or_none()
    if not lista:
        raise HTTPException(status_code=404, detail="Lista no encontrada")

    await db.delete(lista)
    await db.commit()


@router.post("/watchlist/{watchlist_id}/items", status_code=201)
async def agregar_item(
    watchlist_id: int,
    payload: AgregarItemRequest,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == current_user.id)
    )
    lista = result.scalar_one_or_none()
    if not lista:
        raise HTTPException(status_code=404, detail="Lista no encontrada")

    item = WatchlistItem(
        watchlist_id=watchlist_id,
        tienda=payload.tienda,
        sku=payload.sku,
        nombre=payload.nombre,
        termino_busqueda=payload.termino_busqueda,
        url=payload.url,
        precio_actual=payload.precio,
        moneda=payload.moneda,
        sucursal_id=payload.sucursal_id,
        sucursal_nombre=payload.sucursal_nombre,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_to_dict(item)


@router.delete("/watchlist/items/{item_id}", status_code=204)
async def eliminar_item(
    item_id: int,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WatchlistItem)
        .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
        .where(WatchlistItem.id == item_id, Watchlist.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Producto no encontrado en tus listas")

    await db.delete(item)
    await db.commit()


# ── Notificaciones ────────────────────────────────────────────────────────────

@router.get("/notificaciones")
async def listar_notificaciones(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notificacion)
        .where(Notificacion.user_id == current_user.id)
        .order_by(Notificacion.created_at.desc())
        .limit(50)
    )
    notifs = result.scalars().all()
    return [
        {
            "id": n.id,
            "tipo": n.tipo,
            "mensaje": n.mensaje,
            "leida": n.leida,
            "watchlist_item_id": n.watchlist_item_id,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifs
    ]


@router.get("/notificaciones/no-leidas/count")
async def contar_no_leidas(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notificacion).where(Notificacion.user_id == current_user.id, Notificacion.leida == False)
    )
    return {"count": len(result.scalars().all())}


@router.post("/notificaciones/{notif_id}/marcar-leida")
async def marcar_leida(
    notif_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notificacion).where(Notificacion.id == notif_id, Notificacion.user_id == current_user.id)
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")

    notif.leida = True
    await db.commit()
    return {"ok": True}


@router.post("/notificaciones/marcar-todas-leidas")
async def marcar_todas_leidas(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notificacion)
        .where(Notificacion.user_id == current_user.id, Notificacion.leida == False)
        .values(leida=True)
    )
    await db.commit()
    return {"ok": True}
