from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from app.core.deps import get_current_user
from app.models.user import User
from app.services.cenefas_service import generate_pptx_bytes

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/cenefas/generate")
async def generate_cenefas(
    excel: UploadFile = File(..., description="Archivo Excel con hoja 'Cenefas'"),
    template: UploadFile = File(..., description="Plantilla PPTX base"),
    vigencia: str = Form(...),
    aclaracion: str = Form(...),
    otra_alcohol: str = Form(default="Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
    current_user: User = Depends(get_current_user),
):
    if not excel.filename or not excel.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="El Excel debe ser .xlsx o .xlsm")
    if not template.filename or not template.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="La plantilla debe ser .pptx")

    excel_bytes = await excel.read()
    template_bytes = await template.read()

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

    filename = "cenefas_output.pptx"
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
