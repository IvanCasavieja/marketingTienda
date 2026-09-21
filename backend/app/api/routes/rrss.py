"""Rutas /rrss — Validación de redes sociales con CatTi.

El flujo es de a pasos, no una sola request: se sube el mailing (se lee una
vez), después las placas de a una y al final se cierra el lote. Una sola
request con 30 placas de 2250 px pesaría decenas de MB y tardaría minutos;
de a una el usuario ve avanzar cada placa a medida que se valida, y un
archivo roto no tira abajo al resto. Ver app/services/rrss/.
"""
import io
import logging

import anthropic
from PIL import Image
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.rate_limit import limiter
from app.core.uploads import read_limited
from app.models.rrss_validacion import RrssValidacion, RrssValidacionImagen, RrssValidacionPagina
from app.models.user import User
from app.services.ai_usage_service import log_ai_usage
from app.services.rrss import catti, comparador, imagenes, validador

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rrss", tags=["rrss"])

_MAX_IMAGENES_POR_VALIDACION = 150
_MAX_BYTES_PLACA = 25 * 1024 * 1024
_MAX_BYTES_MAILING = 30 * 1024 * 1024
_TIPOS_PLACA = {"image/jpeg", "image/png", "image/webp"}


async def _get_validacion_or_404(db: AsyncSession, validacion_id: int) -> RrssValidacion:
    v = await db.get(RrssValidacion, validacion_id)
    if v is None:
        raise HTTPException(status_code=404, detail="No se encontró esa validación")
    return v


def _exigir_dueno(v: RrssValidacion, user: User) -> None:
    """Cualquiera con rrss.view puede MIRAR una validación (el historial es del
    equipo), pero solo quien la creó -o un superusuario- puede modificarla o
    borrarla."""
    if not user.is_superuser and v.creado_por_id != user.id:
        raise HTTPException(status_code=403, detail="Solo quien creó la validación puede modificarla")


def _imagen_a_dict(i: RrssValidacionImagen) -> dict:
    return {
        "id": i.id, "orden": i.orden, "nombre_archivo": i.nombre_archivo,
        "ancho": i.ancho, "alto": i.alto, "formato": i.formato, "estado": i.estado,
        **i.resultado,
        "vista": imagenes.data_uri(i.vista) if i.vista else None,
    }


async def _paginas(db: AsyncSession, validacion_id: int) -> list[RrssValidacionPagina]:
    res = await db.execute(
        select(RrssValidacionPagina).where(RrssValidacionPagina.validacion_id == validacion_id)
        .order_by(RrssValidacionPagina.numero)
    )
    return list(res.scalars())


async def _detalle(db: AsyncSession, v: RrssValidacion) -> dict:
    res = await db.execute(
        select(RrssValidacionImagen).where(RrssValidacionImagen.validacion_id == v.id)
        .order_by(RrssValidacionImagen.orden, RrssValidacionImagen.id)
    )
    autor = await db.get(User, v.creado_por_id) if v.creado_por_id else None
    return {
        "id": v.id, "nombre_mailing": v.nombre_mailing, "estado": v.estado,
        "config": v.config, "mailing": v.mailing, "resumen": v.resumen,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "usuario": autor.full_name if autor else None,
        "paginas": [
            {"numero": p.numero, "ancho": p.ancho, "alto": p.alto, "imagen": imagenes.data_uri(p.imagen)}
            for p in await _paginas(db, v.id)
        ],
        "imagenes": [_imagen_a_dict(i) for i in res.scalars()],
    }


@router.get("/config")
async def get_config(_: User = Depends(require_permission("rrss.view"))):
    """Los legales que se exigen por defecto en cada placa."""
    return validador.CONFIG_DEFECTO


@router.post("/validaciones")
@limiter.limit("10/minute")
async def crear_validacion(
    request: Request,
    mailing: UploadFile = File(...),
    legal_bases: str | None = Form(None),
    legal_alcohol: str = Form(""),
    current_user: User = Depends(require_permission("rrss.validate")),
    db: AsyncSession = Depends(get_db),
):
    """Sube el mailing original: lo renderiza, CatTi lo lee y ubica cada
    producto, y queda abierta una validación a la que después se suman placas."""
    datos = await read_limited(mailing, "mailing")
    if len(datos) > _MAX_BYTES_MAILING:
        raise HTTPException(status_code=400, detail="El mailing supera los 30 MB")
    config = {
        "legal_bases": (validador.CONFIG_DEFECTO["legal_bases"] if legal_bases is None else legal_bases).strip()[:300],
        "legal_alcohol": legal_alcohol.strip()[:300],
    }

    try:
        preparado = await validador.preparar_mailing(datos, mailing.content_type or "", mailing.filename or "")
    except imagenes.ArchivoInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except catti.LecturaFallida as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except anthropic.APIError as exc:
        logger.error("rrss: error de la API leyendo el mailing — %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude leer el mailing en este momento")

    v = RrssValidacion(
        nombre_mailing=(mailing.filename or "mailing")[:255], estado="en_proceso",
        config=config, mailing=preparado.mailing, creado_por_id=current_user.id,
    )
    db.add(v)
    await db.flush()
    for numero, pagina in enumerate(preparado.paginas):
        db.add(RrssValidacionPagina(
            validacion_id=v.id, numero=numero, ancho=pagina.width, alto=pagina.height,
            imagen=imagenes.jpeg(pagina, 80),
        ))
    await log_ai_usage(
        db, current_user.id, catti.FEATURE, catti.PROVEEDOR, catti._MODEL, preparado.tokens_in, preparado.tokens_out,
    )
    await db.commit()
    await db.refresh(v)
    return await _detalle(db, v)


@router.post("/validaciones/{validacion_id}/imagenes")
@limiter.limit("240/minute")
async def validar_imagen(
    request: Request,
    validacion_id: int,
    archivo: UploadFile = File(...),
    orden: int = Form(0),
    current_user: User = Depends(require_permission("rrss.validate")),
    db: AsyncSession = Depends(get_db),
):
    """Valida UNA placa contra el mailing de esta validación."""
    v = await _get_validacion_or_404(db, validacion_id)
    _exigir_dueno(v, current_user)
    if v.estado != "en_proceso":
        raise HTTPException(status_code=400, detail="Esta validación ya está cerrada")

    total = await db.scalar(
        select(func.count()).select_from(RrssValidacionImagen).where(RrssValidacionImagen.validacion_id == v.id)
    )
    if (total or 0) >= _MAX_IMAGENES_POR_VALIDACION:
        raise HTTPException(status_code=400, detail=f"Máximo {_MAX_IMAGENES_POR_VALIDACION} placas por validación")
    if archivo.content_type not in _TIPOS_PLACA:
        raise HTTPException(status_code=400, detail=f"'{archivo.filename}' no es una imagen JPG, PNG o WebP")
    datos = await read_limited(archivo, "archivo")
    if len(datos) > _MAX_BYTES_PLACA:
        raise HTTPException(status_code=400, detail=f"'{archivo.filename}' supera los 25 MB")

    # las páginas ya renderizadas, para recortar el lado del mailing
    paginas = [Image.open(io.BytesIO(p.imagen)).convert("RGB") for p in await _paginas(db, v.id)]

    r = await validador.validar_placa(datos, archivo.filename or "placa", v.mailing, paginas, v.config)
    fila = RrssValidacionImagen(
        validacion_id=v.id, orden=orden, nombre_archivo=(archivo.filename or "placa")[:255],
        ancho=r.ancho, alto=r.alto, formato=r.formato, estado=r.estado,
        resultado=r.resultado, vista=r.vista,
    )
    db.add(fila)
    if r.tokens_in or r.tokens_out:
        await log_ai_usage(db, current_user.id, catti.FEATURE, catti.PROVEEDOR, catti._MODEL, r.tokens_in, r.tokens_out)
    await db.commit()
    await db.refresh(fila)
    return _imagen_a_dict(fila)


@router.post("/validaciones/{validacion_id}/cerrar")
async def cerrar_validacion(
    validacion_id: int,
    current_user: User = Depends(require_permission("rrss.validate")),
    db: AsyncSession = Depends(get_db),
):
    """Termina el lote: agrupa las adaptaciones de cada producto y revisa lo
    que solo se ve mirando el conjunto (formatos que faltan, CTA mezclados)."""
    v = await _get_validacion_or_404(db, validacion_id)
    _exigir_dueno(v, current_user)
    res = await db.execute(
        select(RrssValidacionImagen).where(RrssValidacionImagen.validacion_id == v.id)
        .order_by(RrssValidacionImagen.orden, RrssValidacionImagen.id)
    )
    filas = list(res.scalars())
    leidas = [
        {
            "id": i.id, "nombre_archivo": i.nombre_archivo, "formato": i.formato,
            "match_indice": (i.resultado.get("match") or {}).get("indice"),
            "lectura": i.resultado["lectura"],
        }
        for i in filas if i.estado != "error" and i.resultado.get("lectura")
    ]
    chequeos = comparador.chequeos_del_lote(leidas, v.mailing["productos"])
    v.resumen = validador.resumir_lote([i.estado for i in filas], chequeos)
    v.estado = "completada"
    await db.commit()
    return {"resumen": v.resumen}


@router.get("/validaciones")
async def listar_validaciones(
    _: User = Depends(require_permission("rrss.view")),
    db: AsyncSession = Depends(get_db),
):
    """El historial: una fila por validación, con sus contadores."""
    I = RrssValidacionImagen
    res = await db.execute(
        select(
            RrssValidacion.id, RrssValidacion.nombre_mailing, RrssValidacion.estado, RrssValidacion.created_at,
            User.full_name,
            func.count(I.id),
            func.count(I.id).filter(I.estado == "ok"),
            func.count(I.id).filter(I.estado.in_(("diferencias", "avisos"))),
            func.count(I.id).filter(I.estado == "sin_match"),
            func.count(I.id).filter(I.estado == "error"),
        )
        .outerjoin(I, I.validacion_id == RrssValidacion.id)
        .outerjoin(User, User.id == RrssValidacion.creado_por_id)
        .group_by(RrssValidacion.id, User.full_name)
        .order_by(RrssValidacion.created_at.desc())
        .limit(200)
    )
    return [
        {
            "id": r[0], "nombre_mailing": r[1], "estado": r[2],
            "created_at": r[3].isoformat() if r[3] else None, "usuario": r[4],
            "total": r[5], "ok": r[6], "con_diferencias": r[7], "sin_match": r[8], "error": r[9],
        }
        for r in res.all()
    ]


@router.get("/validaciones/{validacion_id}")
async def get_validacion(
    validacion_id: int,
    _: User = Depends(require_permission("rrss.view")),
    db: AsyncSession = Depends(get_db),
):
    return await _detalle(db, await _get_validacion_or_404(db, validacion_id))


@router.delete("/validaciones/{validacion_id}")
async def borrar_validacion(
    validacion_id: int,
    current_user: User = Depends(require_permission("rrss.validate")),
    db: AsyncSession = Depends(get_db),
):
    v = await _get_validacion_or_404(db, validacion_id)
    _exigir_dueno(v, current_user)
    await db.delete(v)  # las páginas y las placas se van en cascada
    await db.commit()
    return {"ok": True}
