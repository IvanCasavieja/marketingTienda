"""
watchlist.py — listas de monitoreo de precios + notificaciones.

  GET    /watchlist                        — listas propias + compartidas conmigo, con sus items
  POST   /watchlist                         — crear lista
  GET    /watchlist/{id}                    — detalle (dueño o colaborador)
  PATCH  /watchlist/{id}                    — editar fecha_fin/estado (solo dueño)
  DELETE /watchlist/{id}                    — eliminar lista (cascade a items + historial, solo dueño)
  POST   /watchlist/{id}/items              — agregar producto a una lista (solo dueño)
  DELETE /watchlist/items/{item_id}         — sacar un producto de una lista (solo dueño)
  GET    /watchlist/{id}/historial          — historial de precios acumulado (dueño o colaborador)
  GET    /watchlist/{id}/compartidos        — usuarios con los que está compartida (solo dueño)
  POST   /watchlist/{id}/compartir          — compartir con un usuario (solo dueño)
  DELETE /watchlist/{id}/compartir/{uid}    — revocar (dueño, o el propio colaborador)
  GET    /watchlist/usuarios-compartibles   — usuarios activos disponibles para compartir
  GET    /notificaciones                    — recientes del usuario
  GET    /notificaciones/no-leidas/count    — para el badge del bell
  POST   /notificaciones/{id}/marcar-leida
  POST   /notificaciones/marcar-todas-leidas
"""
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.watchlist_item import WatchlistItem
from app.models.watchlist_precio_historial import WatchlistPrecioHistorial
from app.models.watchlist_share import WatchlistShare
from app.models.notificacion import Notificacion

logger = logging.getLogger(__name__)
router = APIRouter(tags=["watchlist"])


# ── Listas de monitoreo ───────────────────────────────────────────────────────

class CrearWatchlistRequest(BaseModel):
    nombre: str
    fecha_fin: Optional[date] = None


class ActualizarWatchlistRequest(BaseModel):
    fecha_fin: Optional[date] = None
    estado: Optional[str] = None


class CompartirRequest(BaseModel):
    user_id: int


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


def _watchlist_to_dict(l: Watchlist, *, es_propia: bool, compartida_por: str | None, items: list[WatchlistItem]) -> dict:
    return {
        "id": l.id,
        "nombre": l.nombre,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "fecha_inicio": l.fecha_inicio.isoformat() if l.fecha_inicio else None,
        "fecha_fin": l.fecha_fin.isoformat() if l.fecha_fin else None,
        "estado": l.estado,
        "es_propia": es_propia,
        "compartida_por": compartida_por,
        "items": [_item_to_dict(it) for it in items],
    }


def _shared_with_me(user_id: int):
    """EXISTS correlacionado — a diferencia de un JOIN, no multiplica filas de
    Watchlist cuando una lista tiene más de un colaborador."""
    return exists().where(WatchlistShare.watchlist_id == Watchlist.id, WatchlistShare.user_id == user_id)


async def _get_watchlist_accesible(db: AsyncSession, watchlist_id: int, user_id: int) -> Watchlist | None:
    """Dueño o colaborador — para endpoints de solo lectura (detalle, historial)."""
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            (Watchlist.user_id == user_id) | _shared_with_me(user_id),
        )
    )
    return result.scalar_one_or_none()


@router.get("/watchlist")
async def listar_watchlists(
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watchlist, User.full_name)
        .join(User, User.id == Watchlist.user_id)
        .where((Watchlist.user_id == current_user.id) | _shared_with_me(current_user.id))
        .order_by(Watchlist.created_at)
    )
    filas = result.all()
    if not filas:
        return []

    listas = [(l, dueño_nombre) for l, dueño_nombre in filas]
    ids = [l.id for l, _ in listas]

    items_result = await db.execute(select(WatchlistItem).where(WatchlistItem.watchlist_id.in_(ids)))
    items_por_lista: dict[int, list[WatchlistItem]] = {}
    for item in items_result.scalars().all():
        items_por_lista.setdefault(item.watchlist_id, []).append(item)

    return [
        _watchlist_to_dict(
            l,
            es_propia=(l.user_id == current_user.id),
            compartida_por=None if l.user_id == current_user.id else dueño_nombre,
            items=items_por_lista.get(l.id, []),
        )
        for l, dueño_nombre in listas
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

    lista = Watchlist(
        user_id=current_user.id,
        nombre=nombre,
        fecha_inicio=datetime.now().date(),
        fecha_fin=payload.fecha_fin,
    )
    db.add(lista)
    await db.commit()
    await db.refresh(lista)
    return _watchlist_to_dict(lista, es_propia=True, compartida_por=None, items=[])


@router.get("/watchlist/usuarios-compartibles")
async def usuarios_compartibles(
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    """Usuarios activos disponibles para compartir una lista — proyección
    mínima (sin permisos/rol), a diferencia de GET /admin/users que exige
    permiso de panel de administrador y no todo usuario que comparte listas
    lo tiene."""
    result = await db.execute(
        select(User.id, User.email, User.full_name)
        .where(User.is_active == True, User.id != current_user.id)
        .order_by(User.full_name)
    )
    return [{"id": uid, "email": email, "full_name": full_name} for uid, email, full_name in result.all()]


@router.get("/watchlist/{watchlist_id}")
async def obtener_watchlist(
    watchlist_id: int,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    lista = await _get_watchlist_accesible(db, watchlist_id, current_user.id)
    if not lista:
        raise HTTPException(status_code=404, detail="Lista no encontrada")

    dueño_result = await db.execute(select(User.full_name).where(User.id == lista.user_id))
    dueño_nombre = dueño_result.scalar_one_or_none()

    items_result = await db.execute(select(WatchlistItem).where(WatchlistItem.watchlist_id == lista.id))
    items = items_result.scalars().all()

    return _watchlist_to_dict(
        lista,
        es_propia=(lista.user_id == current_user.id),
        compartida_por=None if lista.user_id == current_user.id else dueño_nombre,
        items=items,
    )


@router.patch("/watchlist/{watchlist_id}")
async def actualizar_watchlist(
    watchlist_id: int,
    payload: ActualizarWatchlistRequest,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == current_user.id)
    )
    lista = result.scalar_one_or_none()
    if not lista:
        raise HTTPException(status_code=404, detail="Lista no encontrada")

    if payload.estado is not None:
        if payload.estado not in ("activa", "finalizada"):
            raise HTTPException(status_code=400, detail="Estado inválido")
        lista.estado = payload.estado
    if "fecha_fin" in payload.model_fields_set:
        lista.fecha_fin = payload.fecha_fin

    await db.commit()
    await db.refresh(lista)

    items_result = await db.execute(select(WatchlistItem).where(WatchlistItem.watchlist_id == lista.id))
    items = items_result.scalars().all()
    return _watchlist_to_dict(lista, es_propia=True, compartida_por=None, items=items)


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


@router.get("/watchlist/{watchlist_id}/historial")
async def historial_watchlist(
    watchlist_id: int,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    """Historial de precios acumulado de todos los productos de la lista —
    fuente de datos para el Excel de una lista finalizada. Dueño o colaborador."""
    lista = await _get_watchlist_accesible(db, watchlist_id, current_user.id)
    if not lista:
        raise HTTPException(status_code=404, detail="Lista no encontrada")

    result = await db.execute(
        select(WatchlistPrecioHistorial, WatchlistItem.nombre, WatchlistItem.tienda)
        .join(WatchlistItem, WatchlistItem.id == WatchlistPrecioHistorial.watchlist_item_id)
        .where(WatchlistItem.watchlist_id == watchlist_id)
        .order_by(WatchlistItem.nombre, WatchlistPrecioHistorial.checked_at)
    )
    return [
        {
            "producto": nombre,
            "tienda": tienda,
            "precio": h.precio,
            "moneda": h.moneda,
            "checked_at": h.checked_at.isoformat() if h.checked_at else None,
        }
        for h, nombre, tienda in result.all()
    ]


@router.get("/watchlist/{watchlist_id}/compartidos")
async def listar_compartidos(
    watchlist_id: int,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    lista_result = await db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == current_user.id)
    )
    if not lista_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Lista no encontrada")

    result = await db.execute(
        select(User.id, User.email, User.full_name)
        .join(WatchlistShare, WatchlistShare.user_id == User.id)
        .where(WatchlistShare.watchlist_id == watchlist_id)
        .order_by(User.full_name)
    )
    return [{"id": uid, "email": email, "full_name": full_name} for uid, email, full_name in result.all()]


@router.post("/watchlist/{watchlist_id}/compartir", status_code=201)
async def compartir_watchlist(
    watchlist_id: int,
    payload: CompartirRequest,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    lista_result = await db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == current_user.id)
    )
    if not lista_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Lista no encontrada")

    if payload.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No podés compartir la lista con vos mismo")

    usuario_result = await db.execute(select(User).where(User.id == payload.user_id, User.is_active == True))
    if not usuario_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    ya_compartida = await db.execute(
        select(WatchlistShare).where(
            WatchlistShare.watchlist_id == watchlist_id, WatchlistShare.user_id == payload.user_id
        )
    )
    if ya_compartida.scalar_one_or_none():
        return {"ok": True}

    db.add(WatchlistShare(watchlist_id=watchlist_id, user_id=payload.user_id))
    await db.commit()
    return {"ok": True}


@router.delete("/watchlist/{watchlist_id}/compartir/{user_id}", status_code=204)
async def dejar_de_compartir(
    watchlist_id: int,
    user_id: int,
    current_user: User = Depends(require_permission("precios.search")),
    db: AsyncSession = Depends(get_db),
):
    """El dueño puede revocarle el acceso a cualquiera; un colaborador solo
    puede sacarse a sí mismo (dejar de ver una lista que le compartieron)."""
    lista_result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    lista = lista_result.scalar_one_or_none()
    if not lista:
        raise HTTPException(status_code=404, detail="Lista no encontrada")

    es_dueño = lista.user_id == current_user.id
    if not es_dueño and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="No tenés permiso para modificar este acceso")

    result = await db.execute(
        select(WatchlistShare).where(WatchlistShare.watchlist_id == watchlist_id, WatchlistShare.user_id == user_id)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="No estaba compartida con ese usuario")

    await db.delete(share)
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
            "origen_tipo": n.origen_tipo,
            "origen_ref": n.origen_ref,
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
