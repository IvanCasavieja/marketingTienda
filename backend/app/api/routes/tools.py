import logging
import re
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.uploads import read_limited as _read_limited
from app.models.user import User
from app.models.cenefa_template import CenefaTemplate
from app.services.cenefas.data_engine import generate_template_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])

_BUILTIN_TEMPLATES = [
    {"slug": "a4",      "name": "Cenefa A4",   "format_name": "A4",     "filename": "Base cenefa A4 1.pptx"},
    {"slug": "pinchos", "name": "Pinchos",      "format_name": "Pinchos","filename": "Base pinchos 1.pptx"},
    {"slug": "black",   "name": "Cenefas 3xA4", "format_name": "3xA4",  "filename": "Bases cenefas BLACK 1.pptx"},
]


def _safe_filename(name: str) -> str:
    """El nombre del template es texto libre cargado por el usuario y termina
    reflejado sin escapar en el header Content-Disposition — una comilla ahí
    rompe el parámetro filename= y permite manipular la respuesta. Sacamos
    comillas, backslashes y cualquier caracter de control (CR/LF incluidos)."""
    cleaned = re.sub(r'[\x00-\x1f\x7f"\\]', "", name)
    return cleaned.strip() or "template"


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
# El endpoint síncrono de generación (POST /cenefas/generate) se retiró —
# tanto Redexpres como Rompe Precios generan ahora vía el pipeline de jobs
# async (POST /tools/cenefas/v2/jobs), que además deja el paso de preview +
# reposicionar antes del render final. El motor viejo (generate_pptx_bytes /
# render_engine.py) queda sin referencias pero no se borra.

@router.get("/cenefas/template")
async def download_cenefa_template(
    destino: str = Query("redexpres", description="redexpres | rompe_precios"),
    current_user: User = Depends(require_permission("cenefas.view")),
):
    xlsx_bytes = generate_template_bytes(destino)
    filename = "plantilla_rompe_precios.xlsx" if destino == "rompe_precios" else "plantilla_redexpres.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Template CRUD (v1)
# ---------------------------------------------------------------------------

@router.get("/cenefas/builtin-templates")
async def list_builtin_templates(
    current_user: User = Depends(require_permission("cenefas.view")),
):
    return [
        {"slug": t["slug"], "name": t["name"], "format_name": t["format_name"]}
        for t in _BUILTIN_TEMPLATES
    ]


@router.get("/cenefas/templates")
async def list_templates(
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CenefaTemplate)
        .where(CenefaTemplate.is_active == True)
        .order_by(CenefaTemplate.created_at.desc())
    )
    return [
        {
            "id": t.id,
            "name": t.name,
            "format_name": t.format_name,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in result.scalars().all()
    ]


@router.post("/cenefas/templates", status_code=201)
async def create_template(
    name: str = Form(...),
    format_name: str = Form(default=""),
    file: UploadFile = File(..., description="Plantilla PPTX"),
    current_user: User = Depends(require_permission("cenefas.import")),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="El archivo debe ser .pptx")
    data = await _read_limited(file, "template PPTX")
    tmpl = CenefaTemplate(
        name=name.strip(),
        format_name=format_name.strip(),
        file_bytes=data,
        created_by=current_user.id,
    )
    db.add(tmpl)
    await db.flush()
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "format_name": tmpl.format_name,
        "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
    }


@router.delete("/cenefas/templates/{template_id}", status_code=204)
async def delete_template_v1(
    template_id: int,
    current_user: User = Depends(require_permission("cenefas.delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CenefaTemplate).where(
            CenefaTemplate.id == template_id,
            CenefaTemplate.is_active == True,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template no encontrado")
    if tmpl.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="No tenés permiso para eliminar el template de otro usuario")
    tmpl.is_active = False


@router.get("/cenefas/templates/{template_id}/download")
async def download_template_v1(
    template_id: int,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CenefaTemplate).where(
            CenefaTemplate.id == template_id,
            CenefaTemplate.is_active == True,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template no encontrado")
    return Response(
        content=tmpl.file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(tmpl.name)}.pptx"'},
    )
