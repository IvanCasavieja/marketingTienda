"""Rutas /facturacion — dashboard de presupuesto/canjes y el flujo de subir
una factura PDF, dejar que DogTi la lea, y revisar/confirmar antes de que
se guarde (ver app/services/facturacion/)."""
import logging
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.rate_limit import limiter
from app.core.uploads import read_limited
from app.models.facturacion_documento import FacturacionDocumento
from app.models.user import User
from app.services.facturacion import documentos as documentos_service
from app.services.facturacion import dogti_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/facturacion", tags=["facturacion"])


async def _get_documento_or_404(db: AsyncSession, documento_id: int) -> FacturacionDocumento:
    documento = await db.get(FacturacionDocumento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="No se encontró ese documento")
    return documento


@router.post("/documentos/upload")
@limiter.limit("5/minute")
async def upload_documento(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("facturacion.upload")),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "factura.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    file_bytes = await read_limited(file, "PDF")
    documento = await documentos_service.crear_documento_y_extraer(
        db, filename, file.content_type or "application/pdf", file_bytes, current_user.id,
    )
    await db.commit()
    await db.refresh(documento)
    return documentos_service.documento_to_dict(documento)


@router.get("/documentos/{documento_id}")
async def get_documento(
    documento_id: int,
    _: User = Depends(require_permission("facturacion.upload")),
    db: AsyncSession = Depends(get_db),
):
    documento = await _get_documento_or_404(db, documento_id)
    return documentos_service.documento_to_dict(documento)


@router.get("/documentos/{documento_id}/pdf")
async def get_documento_pdf(
    documento_id: int,
    _: User = Depends(require_permission("facturacion.upload")),
    db: AsyncSession = Depends(get_db),
):
    documento = await _get_documento_or_404(db, documento_id)
    return Response(content=documento.file_bytes, media_type=documento.content_type or "application/pdf")


class ConfirmarDocumentoRequest(BaseModel):
    tipo: str = Field(description="movimiento | canje")
    tipo_movimiento: str = Field(default="salida", description="entrada | salida — solo aplica si tipo=movimiento")
    monto: float
    moneda: str = "UYU"
    concepto: str = Field(min_length=1, max_length=300)
    proveedor_marca: str | None = None
    numero_factura: str | None = None
    fecha: date
    estado: str | None = Field(default=None, description="pendiente | activo | cerrado — solo canje")
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None

    @field_validator("tipo")
    @classmethod
    def _validar_tipo(cls, v: str) -> str:
        if v not in ("movimiento", "canje"):
            raise ValueError("tipo debe ser 'movimiento' o 'canje'")
        return v

    @field_validator("tipo_movimiento")
    @classmethod
    def _validar_tipo_movimiento(cls, v: str) -> str:
        if v not in ("entrada", "salida"):
            raise ValueError("tipo_movimiento debe ser 'entrada' o 'salida'")
        return v


@router.post("/documentos/{documento_id}/confirmar")
async def confirmar_documento(
    documento_id: int,
    payload: ConfirmarDocumentoRequest,
    current_user: User = Depends(require_permission("facturacion.upload")),
    db: AsyncSession = Depends(get_db),
):
    documento = await _get_documento_or_404(db, documento_id)
    try:
        registro = documentos_service.confirmar_documento(
            db, documento, payload.tipo, payload.model_dump(), current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"tipo": payload.tipo, "id": registro.id}


@router.post("/documentos/{documento_id}/descartar")
async def descartar_documento(
    documento_id: int,
    _: User = Depends(require_permission("facturacion.upload")),
    db: AsyncSession = Depends(get_db),
):
    documento = await _get_documento_or_404(db, documento_id)
    try:
        documentos_service.descartar_documento(documento)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"status": documento.status}


@router.get("/dashboard")
async def dashboard(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_permission("facturacion.view")),
    db: AsyncSession = Depends(get_db),
):
    return await documentos_service.obtener_dashboard(db, limit, offset)


class DogtiHistorialItem(BaseModel):
    role: str
    content: str


class DogtiConsultarRequest(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2000)
    contexto: str | None = None
    historial: list[DogtiHistorialItem] = []


@router.post("/dogti/consultar")
@limiter.limit("15/minute")
async def dogti_consultar(
    request: Request,
    payload: DogtiConsultarRequest,
    current_user: User = Depends(require_permission("ai.dogti")),
    db: AsyncSession = Depends(get_db),
):
    try:
        resumen = await documentos_service.obtener_dashboard(db, limit=1, offset=0)
        result = await dogti_agent.consultar(
            payload.mensaje,
            [h.model_dump() for h in payload.historial],
            payload.contexto,
            db,
            current_user.id,
            resumen_dashboard=resumen,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("dogti_consultar: error — %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude procesar tu consulta en este momento")

    await db.commit()
    return {"respuesta": result["respuesta"]}
