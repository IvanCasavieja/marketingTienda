"""revision_ia.py — lo que encontró la IA en una versión, para quien la aprueba.

  GET   /calendario/versiones/{id}/revision-ia        — estado, observaciones y qué se ve hecho de
                                                        lo que se pidió (las marcas de la ronda
                                                        anterior, el pedido inicial o el comentario)
  PATCH /calendario/versiones/{id}/revision-ia/{obs}  — descartar una (o traerla de vuelta)

Convertir una observación en marca no tiene ruta propia: la marca se crea con
la decisión, como cualquier otra (POST /calendario/versiones/{id}/decision,
con `observacionIA` en la marca), y ahí la observación queda como "marca".

La revisión la hace app/services/revision_ia.py en segundo plano, después de
cada entrega. Quién la ve se decide acá, del lado del servidor
(`puede_ver_revision`): los aprobadores y quien gestiona las tareas, nunca
quien entrega la pieza.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.entregas import _nombres, _puede_ver, _tarea_y_barra, puede_ver_revision
from app.core.database import get_db
from app.core.deps import require_permission
from app.models.entregas import CalendarioEntrega, CalendarioVersion
from app.models.revision_ia import CalendarioRevisionIA
from app.models.user import User
from app.services import revision_ia

router = APIRouter(prefix="/calendario", tags=["calendario-entregas"])

_SOLO_APROBADORES = "Lo que encontró la IA lo ven solo quienes aprueban la pieza"


async def _version_visible(db: AsyncSession, version_id: str, usuario: User) -> CalendarioVersion:
    version = await db.get(CalendarioVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Esa versión ya no existe")
    tarea, barra = await _tarea_y_barra(db, version.tarea_id, usuario)
    if not _puede_ver(usuario, barra.mundo, tarea):
        raise HTTPException(status_code=403, detail="No podés ver esta tarea")
    entrega = await db.get(CalendarioEntrega, tarea.id)
    if entrega is None or not puede_ver_revision(usuario, entrega, tarea, version):
        raise HTTPException(status_code=403, detail=_SOLO_APROBADORES)
    return version


async def _json(db: AsyncSession, observaciones: list[dict]) -> list[dict]:
    nombres = await _nombres(db, [o.get("por") for o in observaciones])
    return [{**o, "porNombre": nombres.get(o.get("por"))} for o in observaciones]


@router.get("/versiones/{version_id}/revision-ia")
async def ver_revision(
    version_id: str,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """'pendiente' (la IA la está mirando: el front vuelve a preguntar en unos
    segundos), 'lista' (con las observaciones, aunque sean cero) o 'nada' (no
    se revisó, falló o se llegó al tope: no se muestra nada).

    Desde el 19/11/2026 cada observación dice de qué archivo es (`archivo`,
    `pagina`, `origen`: una del ZIP o del link no tiene `imagenId`), y viajan
    además `revisados`, `noSePudoAbrir` e `ignorados` (ver
    revision_ia.materiales_para_mostrar) y `cambiosPedidos`: si se ve hecho
    lo que pedía cada marca de la ronda anterior, [{marcaId, numero,
    veredicto: 'hecho' | 'falta' | 'dudoso', nota}] (desde el 21/11/2026,
    también `texto`: lo que pedía la marca; ver
    revision_ia.cambios_pedidos_para_mostrar).

    Desde el 21/11/2026 viaja además `puntosPedidos`: lo que se pidió sin
    marcas (en la primera ronda, cada punto del pedido inicial; si los
    cambios se pidieron solo con texto, cada pedido del comentario) y lo que
    dijo la IA de cada uno, como lo ve la agencia antes de mandar (si entregó
    las imágenes que controló, es lo mismo que vio):
    {inicial, puntos: [{numero, texto, veredicto, nota}]}, o null (ver
    revision_ia.puntos_pedidos_para_mostrar). Como todo lo de acá, solo para
    quien puede ver la revisión: la agencia nunca (lo suyo lo ve en el
    control antes de entregar)."""
    await _version_visible(db, version_id, current_user)
    fila = await db.get(CalendarioRevisionIA, version_id)
    out = revision_ia.para_mostrar(
        fila.estado if fila else None, fila.created_at if fila else None,
        fila.observaciones if fila else None, datetime.now(timezone.utc),
    )
    out["observaciones"] = await _json(db, out["observaciones"])
    out.update(revision_ia.materiales_para_mostrar(fila.materiales if fila else None, out["estado"]))
    cambios = fila.cambios_pedidos if fila else None
    out["cambiosPedidos"] = revision_ia.cambios_pedidos_para_mostrar(cambios, out["estado"])
    out["puntosPedidos"] = revision_ia.puntos_pedidos_para_mostrar(cambios, out["estado"])
    return out


class ObservacionCambio(BaseModel):
    descartada: bool


@router.patch("/versiones/{version_id}/revision-ia/{observacion_id}")
async def descartar_observacion(
    version_id: str,
    observacion_id: str,
    payload: ObservacionCambio,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Descartar una observación de la IA (o traerla de vuelta). Queda anotado
    quién la descartó: el siguiente de la cadena la ve descartada, no de nuevo.
    Solo mientras la versión espera una decisión."""
    version = await _version_visible(db, version_id, current_user)
    if version.estado != "revision":
        raise HTTPException(status_code=409, detail="Esta versión ya se decidió: recargá para ver cómo quedó")
    fila = await db.get(CalendarioRevisionIA, version_id, with_for_update=True)
    if fila is None or fila.estado != "lista":
        raise HTTPException(status_code=404, detail="La IA no dejó observaciones en esta versión")
    try:
        fila.observaciones = revision_ia.descartar(
            list(fila.observaciones or []), observacion_id, payload.descartada, current_user.id,
            datetime.now(timezone.utc),
        )
    except revision_ia.NoSePuede as exc:
        raise HTTPException(status_code=exc.codigo, detail=str(exc))
    await db.commit()
    obs = next(o for o in fila.observaciones if o["id"] == observacion_id)
    return (await _json(db, [obs]))[0]
