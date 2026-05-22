from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.cenefa_template import CenefaTemplate
from app.services.cenefas_service import generate_pptx_bytes

router = APIRouter(prefix="/tools", tags=["tools"])


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------

@router.get("/cenefas/templates")
async def list_cenefa_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        return []
    result = await db.execute(
        select(CenefaTemplate)
        .where(
            CenefaTemplate.team_group_id == current_user.team_group_id,
            CenefaTemplate.is_active == True,
        )
        .order_by(CenefaTemplate.created_at.desc())
    )
    templates = result.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "format_name": t.format_name,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in templates
    ]


@router.post("/cenefas/templates", status_code=status.HTTP_201_CREATED)
async def create_cenefa_template(
    name: str = Form(...),
    format_name: str = Form(default=""),
    file: UploadFile = File(..., description="Plantilla PPTX"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Unite a un equipo para guardar templates")
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="La plantilla debe ser .pptx")

    file_bytes = await file.read()
    tmpl = CenefaTemplate(
        team_group_id=current_user.team_group_id,
        created_by=current_user.id,
        name=name.strip(),
        format_name=format_name.strip(),
        file_bytes=file_bytes,
    )
    db.add(tmpl)
    await db.flush()
    await db.refresh(tmpl)
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "format_name": tmpl.format_name,
        "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
    }


@router.delete("/cenefas/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cenefa_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Unite a un equipo para gestionar templates")
    result = await db.execute(
        select(CenefaTemplate).where(
            CenefaTemplate.id == template_id,
            CenefaTemplate.team_group_id == current_user.team_group_id,
            CenefaTemplate.is_active == True,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template no encontrado")
    tmpl.is_active = False


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@router.post("/cenefas/generate")
async def generate_cenefas(
    excel: UploadFile = File(..., description="Archivo Excel con hoja 'Cenefas'"),
    template: UploadFile | None = File(None, description="Plantilla PPTX personalizada"),
    template_id: int | None = Form(None, description="ID de template guardado"),
    vigencia: str = Form(...),
    aclaracion: str = Form(default=""),
    otra_alcohol: str = Form(default="Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not excel.filename or not excel.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="El Excel debe ser .xlsx o .xlsm")

    # Resolve template bytes: saved template takes precedence over uploaded file
    if template_id is not None:
        if not current_user.team_group_id:
            raise HTTPException(status_code=400, detail="Unite a un equipo para usar templates guardados")
        result = await db.execute(
            select(CenefaTemplate).where(
                CenefaTemplate.id == template_id,
                CenefaTemplate.team_group_id == current_user.team_group_id,
                CenefaTemplate.is_active == True,
            )
        )
        tmpl_record = result.scalar_one_or_none()
        if not tmpl_record:
            raise HTTPException(status_code=404, detail="Template no encontrado")
        template_bytes = tmpl_record.file_bytes
    elif template is not None and template.filename:
        if not template.filename.lower().endswith(".pptx"):
            raise HTTPException(status_code=400, detail="La plantilla debe ser .pptx")
        template_bytes = await template.read()
    else:
        raise HTTPException(
            status_code=400,
            detail="Debés seleccionar un template guardado o subir un archivo PPTX"
        )

    excel_bytes = await excel.read()

    try:
        pptx_bytes = generate_pptx_bytes(
            excel_bytes=excel_bytes,
            template_bytes=template_bytes,
            vigencia=vigencia,
            aclaracion=aclaracion,
            otra_alcohol=otra_alcohol,
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Columna faltante en el Excel: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar: {e}")

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="cenefas_output.pptx"'},
    )
