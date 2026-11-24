"""adjuntos.py — los archivos del pedido de una tarea (0089).

  GET    /calendario/tareas/{id}/adjuntos  — los de la tarea y los de las tareas de las que cuelga
  POST   /calendario/tareas/{id}/adjuntos  — adjuntar (multipart: `archivos`, uno o varios)
  GET    /calendario/adjuntos/{id}?desde=  — bajarlo con su nombre (`desde`: la tarea en la que se ve)
  DELETE /calendario/adjuntos/{id}         — sacarlo

Pedido de Ivan (24/11/2026): "en el brief de las tareas deberíamos poder
adjuntar archivos, como el Excel por ejemplo". Qué se acepta y cuánto está en
app/services/adjuntos.py; la tabla, en app/models/adjuntos.py. Permisos, del
lado del servidor:

- Ve y baja quien ve la tarea (las mismas reglas que la tarjeta:
  `_tarea_y_barra` y `_puede_ver`), la agencia de esa pieza incluida. En una
  pieza se ven también los adjuntos de la tarea de la que cuelga: el Excel de
  «Nueva tarea» con sus piezas se sube una vez y le llega a cada agencia. Al
  bajar, `desde` dice en qué tarea se está mirando; el archivo tiene que ser
  de esa tarea o de una de las que cuelga. Otra agencia: el 404 de siempre.
- Adjunta y saca quien gestiona las tareas, y quien creó la tarea si pide
  piezas (ver adjuntos.puede_adjuntar). La agencia no adjunta al pedido.
"""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.calendario import _puede_gestionar_tareas, puede_pedir_piezas
from app.api.routes.entregas import _adjunto, _puede_ver, _tarea_y_barra
from app.core import externos
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.rate_limit import limiter
from app.models.adjuntos import CalendarioAdjunto
from app.models.calendario import CalendarioTarea
from app.models.user import User
from app.services import adjuntos as reglas
from app.services.espacio import MB, entra, hay_lugar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendario", tags=["calendario-adjuntos"])

_YA_NO_ESTA = "Ese archivo ya no está: lo sacaron del pedido."
_QUIEN_ADJUNTA = "Los archivos del pedido los suben y los sacan quien pidió la tarea y quien gestiona las tareas"
_LLENO = (
    "Los archivos adjuntos de todas las tareas ya ocupan el lugar que tienen en la base ({tope} MB). "
    "Sacá los de tareas que ya pasaron, o avisale a quien administra Core Tienda. El archivo no se guardó."
)
_BASE_LLENA = "La base está casi llena: avisale a quien administra Core Tienda. El archivo no se guardó."


def _puede_adjuntar(usuario: User, tarea: CalendarioTarea) -> bool:
    return reglas.puede_adjuntar(
        usuario.id, tarea.creado_por_id,
        gestiona=_puede_gestionar_tareas(usuario), pide=puede_pedir_piezas(usuario),
    )


async def lista_para(db: AsyncSession, tarea: CalendarioTarea, usuario: User) -> list[dict]:
    """Los adjuntos que ve `usuario` en `tarea` (también los usa la ficha de
    entregas)."""
    return await reglas.lista(
        db, tarea, usuario.id, gestiona=_puede_gestionar_tareas(usuario), pide=puede_pedir_piezas(usuario),
        externo=externos.es_externo(usuario),
    )


async def _tarea_visible(db: AsyncSession, tarea_id: str, usuario: User, *, bloquear: bool = False) -> CalendarioTarea:
    tarea, barra = await _tarea_y_barra(db, tarea_id, usuario, bloquear=bloquear)
    if not _puede_ver(usuario, barra.mundo, tarea):
        raise HTTPException(status_code=403, detail="No podés ver esta tarea")
    return tarea


@router.get("/tareas/{tarea_id}/adjuntos")
async def ver_adjuntos(
    tarea_id: str,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    tarea = await _tarea_visible(db, tarea_id, current_user)
    return {
        "adjuntos": await lista_para(db, tarea, current_user),
        "puedoAdjuntar": _puede_adjuntar(current_user, tarea),
    }


@router.post("/tareas/{tarea_id}/adjuntos", status_code=201)
@limiter.limit("20/minute")
async def adjuntar(
    request: Request,
    tarea_id: str,
    archivos: list[UploadFile] = File(...),
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Adjuntar uno o varios archivos al pedido. Se guardan todos o ninguno:
    si uno no se puede (tipo, peso, cuántos), se dice cuál y por qué."""
    # La tarea queda bloqueada hasta el final: dos subidas a la vez no pasan
    # juntas el tope de archivos por tarea.
    tarea = await _tarea_visible(db, tarea_id, current_user, bloquear=True)
    if not _puede_adjuntar(current_user, tarea):
        raise HTTPException(status_code=403, detail=_QUIEN_ADJUNTA)
    ya = (await db.execute(
        select(func.count()).select_from(CalendarioAdjunto).where(CalendarioAdjunto.tarea_id == tarea.id)
    )).scalar_one()
    if ya + len(archivos) > reglas.MAX_ADJUNTOS:
        quedan = max(0, reglas.MAX_ADJUNTOS - ya)
        raise HTTPException(
            status_code=422,
            detail=f"Hasta {reglas.MAX_ADJUNTOS} archivos por tarea, y ya tiene {ya}: "
                   + (f"podés sumar {quedan} más." if quedan else "sacá alguno para sumar otro."),
        )
    leidos: list[tuple[str, str, bytes]] = []
    for archivo in archivos:
        # Uno más que el máximo: alcanza para saber que se pasó sin leer un
        # archivo gigante entero.
        datos = await archivo.read(reglas.MAX_BYTES_ADJUNTO + 1)
        try:
            nombre, tipo = reglas.validar(archivo.filename, datos, reglas.MAX_BYTES_ADJUNTO)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        leidos.append((nombre, tipo, datos))

    nuevos = sum(len(d) for _, _, d in leidos)
    ocupan = (await db.execute(select(func.coalesce(func.sum(CalendarioAdjunto.tamano), 0)))).scalar_one()
    if not entra(ocupan, nuevos, settings.ADJUNTOS_TOPE_MB):
        logger.error(
            "adjuntos: los archivos del pedido ocupan %.1f MB y su tope es %d MB (ADJUNTOS_TOPE_MB): "
            "no se guardaron %.0f KB. No se borra nada.",
            ocupan / MB, settings.ADJUNTOS_TOPE_MB, nuevos / 1024,
        )
        raise HTTPException(status_code=507, detail=_LLENO.format(tope=settings.ADJUNTOS_TOPE_MB))
    if not await hay_lugar(db, nuevos):
        raise HTTPException(status_code=507, detail=_BASE_LLENA)

    for nombre, tipo, datos in leidos:
        db.add(CalendarioAdjunto(
            id=reglas.nuevo_id(), tarea_id=tarea.id, nombre=nombre, tipo_mime=tipo, tamano=len(datos), datos=datos,
            subido_por_id=current_user.id,
        ))
    await db.flush()
    adjuntos = await lista_para(db, tarea, current_user)
    await db.commit()
    return {"adjuntos": adjuntos, "puedoAdjuntar": True}


@router.get("/adjuntos/{adjunto_id}")
@limiter.limit("30/minute")
async def bajar_adjunto(
    request: Request,
    adjunto_id: str,
    desde: str | None = None,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """El archivo, con su nombre. Viaja con la sesión (la pantalla lo pide y
    arma la descarga), no con un link público. `desde`: la tarea en la que se
    está mirando (una pieza ve los de la tarea de la que cuelga); sin ella, la
    del archivo."""
    fila = (await db.execute(
        select(CalendarioAdjunto.tarea_id, CalendarioAdjunto.nombre, CalendarioAdjunto.tipo_mime)
        .where(CalendarioAdjunto.id == adjunto_id)
    )).first()
    if fila is None:
        raise HTTPException(status_code=404, detail=_YA_NO_ESTA)
    de_la_tarea, nombre, tipo = fila
    tarea = await _tarea_visible(db, desde or de_la_tarea, current_user)
    if de_la_tarea not in {t.id for t in await reglas.cadena_de(db, tarea)}:
        raise HTTPException(status_code=404, detail=_YA_NO_ESTA)
    datos = (await db.execute(
        select(CalendarioAdjunto.datos).where(CalendarioAdjunto.id == adjunto_id)
    )).scalar_one_or_none()
    if datos is None:
        raise HTTPException(status_code=404, detail=_YA_NO_ESTA)
    encabezados = {
        "Content-Disposition": _adjunto(nombre),
        # Se baja, no se abre en el navegador: que no adivine otro tipo.
        "X-Content-Type-Options": "nosniff",
        # Sin guardarlo en el navegador: uno que se sacó del pedido ya no se
        # baja, ni de lo que quedó guardado de antes.
        "Cache-Control": "private, no-store",
    }
    if tipo != "text/csv":
        # Ya viene comprimido (Excel, Word, PDF, imágenes, ZIP): que el GZip
        # de la app no lo vuelva a comprimir.
        encabezados["Content-Encoding"] = "identity"
    return Response(content=datos, media_type=tipo, headers=encabezados)


@router.delete("/adjuntos/{adjunto_id}")
async def sacar_adjunto(
    adjunto_id: str,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    de_la_tarea = (await db.execute(
        select(CalendarioAdjunto.tarea_id).where(CalendarioAdjunto.id == adjunto_id)
    )).scalar_one_or_none()
    if de_la_tarea is None:
        raise HTTPException(status_code=404, detail=_YA_NO_ESTA)
    tarea = await _tarea_visible(db, de_la_tarea, current_user, bloquear=True)
    if not _puede_adjuntar(current_user, tarea):
        raise HTTPException(status_code=403, detail=_QUIEN_ADJUNTA)
    await db.execute(delete(CalendarioAdjunto).where(CalendarioAdjunto.id == adjunto_id))
    await db.commit()
    return {"id": adjunto_id, "sacado": True}
