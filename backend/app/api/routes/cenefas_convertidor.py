"""Rutas /tools/cenefas/convertidor/ — Convertidor de Excel de gestión.

Sin jobs asíncronos ni Redis: parsear un Excel y hacer lookups de SKU es
rápido, a diferencia de renderizar PPTX — no hay razón para repetir acá el
patrón de jobs del generador de Cenefas."""
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.rate_limit import limiter
from app.core.uploads import read_limited
from app.models.sku_descripcion import SkuDescripcion
from app.models.user import User
from app.services.cenefas.convertidor import (
    ConvertidorParseError,
    build_output_workbook,
    match_rows,
    parse_input_excel,
    upsert_sku_descripcion,
)
from app.services.cenefas.convertidor_ai import (
    _ROWS_MAX_PER_REQUEST,
    detectar_grupos_unificables,
    generar_descripciones,
)
from app.services.cenefas import tinin_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/cenefas/convertidor", tags=["cenefas-convertidor"])


@router.post("/preview")
@limiter.limit("20/minute")
async def preview(
    request: Request,
    excel: UploadFile = File(...),
    destino: str = Form(default="redexpres"),
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    excel_bytes = await read_limited(excel, "Excel")
    # Tinín solo entra a clasificar columnas de fecha sin alias reconocido si
    # el usuario tiene el permiso de ese agente específico (misma separación
    # ai.don_tino/ai.dona_tina/ai.tinin/ai.triada que el resto de la IA acá) —
    # sin el permiso, esas columnas simplemente quedan sin reconocer, como si
    # no hubiera IA disponible en este ambiente.
    allow_ai = bool(settings.ANTHROPIC_API_KEY) and (
        current_user.is_superuser or "ai.tinin" in (current_user.permissions or [])
    )
    try:
        parsed, learned_aliases_count = await parse_input_excel(
            excel_bytes, excel.filename or "",
            db=db, current_user_id=current_user.id, allow_ai=allow_ai,
        )
    except ConvertidorParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("convertidor preview parse error: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error al parsear el archivo: {e}")

    rows, learned_count, ma_pairs = await match_rows(parsed, db, current_user.id, destino)
    if learned_count or learned_aliases_count:
        await db.commit()
    matched = sum(1 for r in rows if r["matched"])
    return {
        "rows": rows,
        "total": len(rows),
        "matched_count": matched,
        "unmatched_count": len(rows) - matched,
        "learned_count": learned_count,
        "ma_pairs": ma_pairs,
    }


@router.get("/descripciones")
async def listar_descripciones(
    q: str | None = Query(None, description="Busca por SKU o descripción"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Diccionario — vista de consulta/búsqueda sobre el catálogo compartido
    que alimentan el Convertidor y Tinín. No hay alta manual acá: las
    entradas nacen de un import del Convertidor o de una corrección puntual
    (esta misma pantalla reusa el PATCH de descripciones para editar)."""
    stmt = select(SkuDescripcion)
    count_stmt = select(func.count()).select_from(SkuDescripcion)
    if q:
        like = f"%{q.strip()}%"
        filtro = or_(SkuDescripcion.sku.ilike(like), SkuDescripcion.descripcion.ilike(like))
        stmt = stmt.where(filtro)
        count_stmt = count_stmt.where(filtro)

    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(
        stmt.order_by(SkuDescripcion.descripcion).offset(offset).limit(limit)
    )
    items = result.scalars().all()
    return {
        "items": [
            {"sku": i.sku, "descripcion": i.descripcion, "updated_at": i.updated_at.isoformat() if i.updated_at else None}
            for i in items
        ],
        "total": total,
    }


class DescripcionUpdate(BaseModel):
    descripcion: str = Field(min_length=1, max_length=300)

    @field_validator("descripcion")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


@router.patch("/descripciones/{sku:path}")
async def update_descripcion(
    sku: str,
    payload: DescripcionUpdate,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    try:
        sku_norm = await upsert_sku_descripcion(db, sku, payload.descripcion, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"sku": sku_norm, "descripcion": payload.descripcion}


class ConvertidorRowIn(BaseModel):
    row_id:                int
    codigo:                str
    nombre_articulo:       str = ""
    descripcion:           str = ""
    moneda:                str = "$"
    precio_anterior:       float | None = None
    precio_anterior_raw:   str = ""
    precio:                float | None = None
    precio_raw:            str = ""
    oferta:                str = ""
    oferta_det:            str = ""
    descripcion_web:       str = ""
    comprador:             str = ""
    descuento:             str = ""
    descuento_det:         str = ""
    vigencia:              str = ""
    aclaracion1:            str = ""
    aclaracion2:            str = ""
    aclaracion3:            str = ""
    es_fiambre_kg:          bool = False


class ExportRequest(BaseModel):
    rows: list[ConvertidorRowIn]
    destino: str = "redexpres"


@router.post("/export")
async def export(
    payload: ExportRequest,
    _: User = Depends(require_permission("cenefas.view")),
):
    """Arma el Excel final exclusivamente a partir de lo que mandó el
    browser (no vuelve a leer la base) — lo que se ve en el grid es
    exactamente lo que se descarga, sin depender de si el debounce del
    último PATCH ya disparó o no."""
    xlsx_bytes = build_output_workbook([r.model_dump() for r in payload.rows], payload.destino)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="convertidor_cenefas.xlsx"'},
    )


class GenerarDescripcionItem(BaseModel):
    row_id: int
    codigo: str
    nombre_articulo: str = ""
    descripcion_web: str = ""
    es_fiambre_kg: bool = False


class GenerarDescripcionesRequest(BaseModel):
    rows: list[GenerarDescripcionItem]


@router.post("/descripciones/generar-ia")
@limiter.limit("5/minute")
async def generar_descripciones_ia(
    request: Request,
    payload: GenerarDescripcionesRequest,
    current_user: User = Depends(require_permission("ai.tinin")),
    db: AsyncSession = Depends(get_db),
):
    """Genera sugerencias de descripción con Claude para filas sin match —
    nunca escribe en el catálogo acá, eso lo hace el PATCH existente cuando
    el usuario aprueba una sugerencia desde el modal de revisión."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="La generación con IA no está configurada en este ambiente")
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No hay productos para generar")

    truncated = len(payload.rows) > _ROWS_MAX_PER_REQUEST
    items = [r.model_dump() for r in payload.rows[:_ROWS_MAX_PER_REQUEST]]

    try:
        result = await generar_descripciones(items, db, current_user.id)
    except Exception as exc:
        logger.error("generar_descripciones_ia: error — %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude generar las descripciones en este momento")

    await db.commit()  # persiste el ai_usage_log acumulado en generar_descripciones
    return {
        "suggestions": result["suggestions"],
        "failed_row_ids": result["failed_row_ids"],
        "requested_count": len(payload.rows),
        "processed_count": len(items),
        "truncated": truncated,
    }


class UnificarCategoriasItem(BaseModel):
    row_id: int
    codigo: str
    nombre_articulo: str = ""
    descripcion: str = ""


class UnificarCategoriasRequest(BaseModel):
    rows: list[UnificarCategoriasItem]


@router.post("/categorias/unificar-ia")
@limiter.limit("5/minute")
async def unificar_categorias_ia(
    request: Request,
    payload: UnificarCategoriasRequest,
    current_user: User = Depends(require_permission("ai.tinin")),
    db: AsyncSession = Depends(get_db),
):
    """Le pide a Tinín que agrupe variantes de la misma línea de producto (distinto
    peso, sabor, al agua/al aceite, etc.) entre TODAS las filas del Excel cargado, y
    proponga una descripción de cartel unificada por grupo. Nunca escribe nada -- al
    aprobar un grupo puntual desde el modal, el frontend combina esas filas en una sola
    (código = todos los SKUs unidos con " - ") y guarda vía el mismo PATCH
    /descripciones/{sku} que ya usa la edición manual y la fusión M/A (ver
    ConvertidorGrid.tsx: commitUnificacion) -- no hace falta un endpoint de confirmación
    aparte, mismo criterio que commitMerge."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="La generación con IA no está configurada en este ambiente")
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No hay productos para analizar")

    items = [r.model_dump() for r in payload.rows]
    try:
        result = await detectar_grupos_unificables(items, db, current_user.id)
    except Exception as exc:
        logger.error("unificar_categorias_ia: error — %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude analizar los productos en este momento")

    await db.commit()  # persiste el ai_usage_log acumulado en detectar_grupos_unificables
    return result


class TininHistorialItem(BaseModel):
    role: str
    content: str


class TininConsultarRequest(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2000)
    contexto: str | None = None
    historial: list[TininHistorialItem] = []


@router.post("/tinin/consultar")
@limiter.limit("15/minute")
async def tinin_consultar(
    request: Request,
    payload: TininConsultarRequest,
    current_user: User = Depends(require_permission("ai.tinin")),
    db: AsyncSession = Depends(get_db),
):
    """Chat de Tinín — guía sobre templates/destinos/flujo de generación, y
    puede guardar una descripción en el catálogo compartido si se lo piden
    explícitamente. No dispara generación de cenefas (ver tinin_agent.py)."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="El asistente no está configurado en este ambiente")

    try:
        result = await tinin_agent.consultar(
            payload.mensaje,
            [h.model_dump() for h in payload.historial],
            payload.contexto,
            db,
            current_user.id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("tinin_consultar: error — %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude procesar tu consulta en este momento")

    await db.commit()  # persiste el ai_usage_log acumulado + cualquier descripción guardada por la tool
    return {"respuesta": result["respuesta"]}
