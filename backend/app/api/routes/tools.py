import logging
import pathlib
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.cenefa_template import CenefaTemplate
from app.services.cenefas_service import generate_pptx_bytes, generate_template_bytes

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


async def _read_limited(file: UploadFile, label: str = "archivo") -> bytes:
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"El {label} supera el límite de 50 MB ({len(data) // (1024*1024)} MB recibidos)"
        )
    return data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])

_STATIC_DIR = pathlib.Path(__file__).parent.parent.parent / "static" / "cenefa_templates"

_BUILTIN_TEMPLATES = [
    {"slug": "a4",      "name": "Cenefa A4",   "format_name": "A4",     "filename": "Base cenefa A4 1.pptx"},
    {"slug": "pinchos", "name": "Pinchos",      "format_name": "Pinchos","filename": "Base pinchos 1.pptx"},
    {"slug": "black",   "name": "Cenefas 3xA4", "format_name": "3xA4",  "filename": "Bases cenefas BLACK 1.pptx"},
]



# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@router.post("/cenefas/generate")
async def generate_cenefas(
    excel: UploadFile = File(..., description="Archivo Excel con hoja 'Cenefas'"),
    template: UploadFile | None = File(None, description="Plantilla PPTX personalizada"),
    template_id: int | None = Form(None, description="ID de template guardado"),
    builtin_slug: str | None = Form(None, description="Slug de plantilla predeterminada"),
    vigencia: str = Form(default=""),
    aclaracion: str = Form(default=""),
    otra_alcohol: str = Form(default="Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
    banco: str = Form(default=""),
    margin_cm: float = Form(default=0.0),
    desc_margin_cm: float = Form(default=1.0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not excel.filename or not excel.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="El Excel debe ser .xlsx o .xlsm")

    if template_id is not None:
        result = await db.execute(
            select(CenefaTemplate).where(
                CenefaTemplate.id == template_id,
                CenefaTemplate.is_active == True,
            )
        )
        tmpl_record = result.scalar_one_or_none()
        if not tmpl_record:
            raise HTTPException(status_code=404, detail="Template no encontrado")
        template_bytes = tmpl_record.file_bytes
    elif builtin_slug is not None:
        tmpl_meta = next((t for t in _BUILTIN_TEMPLATES if t["slug"] == builtin_slug), None)
        if not tmpl_meta:
            raise HTTPException(status_code=400, detail="Plantilla predeterminada no encontrada")
        path = _STATIC_DIR / tmpl_meta["filename"]
        if not path.exists():
            raise HTTPException(status_code=500, detail="Archivo de plantilla predeterminada no encontrado en el servidor")
        template_bytes = path.read_bytes()
    elif template is not None and template.filename:
        if not template.filename.lower().endswith(".pptx"):
            raise HTTPException(status_code=400, detail="La plantilla debe ser .pptx")
        template_bytes = await _read_limited(template, "template PPTX")
    else:
        raise HTTPException(
            status_code=400,
            detail="Debés seleccionar una plantilla predeterminada, una guardada, o subir un archivo PPTX"
        )

    excel_bytes = await _read_limited(excel, "Excel")

    try:
        pptx_bytes = generate_pptx_bytes(
            excel_bytes=excel_bytes,
            template_bytes=template_bytes,
            vigencia=vigencia,
            aclaracion=aclaracion,
            otra_alcohol=otra_alcohol,
            banco=banco,
            margin_cm=margin_cm,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Columna faltante en el Excel: {e}")
    except Exception as e:
        logger.error("Cenefas generation error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al generar el archivo PPTX")

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="cenefas_output.pptx"'},
    )


@router.get("/cenefas/template")
async def download_cenefa_template(
    current_user: User = Depends(get_current_user),
):
    xlsx_bytes = generate_template_bytes()
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="plantilla_cenefas.xlsx"'},
    )


# ---------------------------------------------------------------------------
# Template CRUD (v1)
# ---------------------------------------------------------------------------

@router.get("/cenefas/builtin-templates")
async def list_builtin_templates(
    current_user: User = Depends(get_current_user),
):
    return [
        {"slug": t["slug"], "name": t["name"], "format_name": t["format_name"]}
        for t in _BUILTIN_TEMPLATES
    ]


@router.get("/cenefas/templates")
async def list_templates(
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    tmpl.is_active = False


@router.get("/cenefas/templates/{template_id}/download")
async def download_template_v1(
    template_id: int,
    current_user: User = Depends(get_current_user),
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
        headers={"Content-Disposition": f'attachment; filename="{tmpl.name}.pptx"'},
    )
