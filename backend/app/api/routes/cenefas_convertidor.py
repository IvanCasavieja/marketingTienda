"""Rutas /tools/cenefas/convertidor/ — Convertidor de Excel de gestión.

Sin jobs asíncronos ni Redis: parsear un Excel y hacer lookups de SKU es
rápido, a diferencia de renderizar PPTX — no hay razón para repetir acá el
patrón de jobs del generador de Cenefas."""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.uploads import read_limited
from app.models.sku_descripcion import SkuDescripcion
from app.models.user import User
from app.services.cenefas.convertidor import (
    ConvertidorParseError,
    build_output_workbook,
    match_rows,
    normalize_sku,
    parse_input_excel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/cenefas/convertidor", tags=["cenefas-convertidor"])


@router.post("/preview")
async def preview(
    excel: UploadFile = File(...),
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    excel_bytes = await read_limited(excel, "Excel")
    try:
        parsed = parse_input_excel(excel_bytes)
    except ConvertidorParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("convertidor preview parse error: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error al parsear el archivo: {e}")

    rows = await match_rows(parsed, db)
    matched = sum(1 for r in rows if r["matched"])
    return {
        "rows": rows,
        "total": len(rows),
        "matched_count": matched,
        "unmatched_count": len(rows) - matched,
    }


class DescripcionUpdate(BaseModel):
    descripcion: str = Field(min_length=1, max_length=300)

    @field_validator("descripcion")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


@router.patch("/descripciones/{sku}")
async def update_descripcion(
    sku: str,
    payload: DescripcionUpdate,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Upsert vía ON CONFLICT DO UPDATE — evita una condición de carrera real
    si dos personas completan el mismo SKU sin match al mismo tiempo."""
    sku_norm = normalize_sku(sku)
    if not sku_norm:
        raise HTTPException(status_code=400, detail="SKU inválido")
    if not payload.descripcion:
        raise HTTPException(status_code=422, detail="La descripción no puede quedar vacía")

    stmt = pg_insert(SkuDescripcion).values(
        sku=sku_norm,
        descripcion=payload.descripcion,
        updated_by_id=current_user.id,
    ).on_conflict_do_update(
        index_elements=["sku"],
        set_={
            "descripcion": payload.descripcion,
            "updated_by_id": current_user.id,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
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


class ExportRequest(BaseModel):
    rows: list[ConvertidorRowIn]


@router.post("/export")
async def export(
    payload: ExportRequest,
    _: User = Depends(require_permission("cenefas.view")),
):
    """Arma el Excel final exclusivamente a partir de lo que mandó el
    browser (no vuelve a leer la base) — lo que se ve en el grid es
    exactamente lo que se descarga, sin depender de si el debounce del
    último PATCH ya disparó o no."""
    xlsx_bytes = build_output_workbook([r.model_dump() for r in payload.rows])
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="convertidor_cenefas.xlsx"'},
    )
