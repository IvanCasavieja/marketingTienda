"""Rutas /facturacion — dashboard de presupuesto/canjes y el flujo de subir
una factura PDF, dejar que DogTi la lea, y revisar/confirmar antes de que
se guarde (ver app/services/facturacion/)."""
import logging
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.rate_limit import limiter
from app.core.uploads import read_limited
from app.models.facturacion_cuenta import FacturacionCuenta
from app.models.facturacion_documento import FacturacionDocumento
from app.models.user import User
from app.services.facturacion import cuentas as cuentas_service
from app.services.facturacion import documentos as documentos_service
from app.services.facturacion import dogti_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/facturacion", tags=["facturacion"])


async def _get_documento_or_404(db: AsyncSession, documento_id: int) -> FacturacionDocumento:
    documento = await db.get(FacturacionDocumento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="No se encontró ese documento")
    return documento


async def _get_cuenta_or_404(db: AsyncSession, cuenta_id: int) -> FacturacionCuenta:
    cuenta = await db.get(FacturacionCuenta, cuenta_id)
    if cuenta is None:
        raise HTTPException(status_code=404, detail="No se encontró esa cuenta")
    return cuenta


@router.get("/cuentas")
async def listar_cuentas(
    incluir_inactivas: bool = Query(False),
    _: User = Depends(require_permission("facturacion.view")),
    db: AsyncSession = Depends(get_db),
):
    cuentas = await cuentas_service.listar_cuentas(db, incluir_inactivas)
    return [cuentas_service.cuenta_to_dict(c) for c in cuentas]


class CrearCuentaRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


@router.post("/cuentas")
async def crear_cuenta(
    payload: CrearCuentaRequest,
    _: User = Depends(require_permission("facturacion.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        cuenta = await cuentas_service.crear_cuenta(db, payload.nombre)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese nombre")
    return cuentas_service.cuenta_to_dict(cuenta)


class EditarCuentaRequest(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    # false = "eliminar" (soft-delete, ver FacturacionCuenta) -- nunca se
    # borra la fila, los movimientos/canjes ya cargados conservan su cuenta.
    activa: bool | None = None


@router.patch("/cuentas/{cuenta_id}")
async def editar_cuenta(
    cuenta_id: int,
    payload: EditarCuentaRequest,
    _: User = Depends(require_permission("facturacion.manage")),
    db: AsyncSession = Depends(get_db),
):
    cuenta = await _get_cuenta_or_404(db, cuenta_id)
    try:
        cuentas_service.editar_cuenta(cuenta, payload.nombre, payload.activa)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese nombre")
    await db.refresh(cuenta)
    return cuentas_service.cuenta_to_dict(cuenta)


_MAX_ARCHIVOS_POR_CARGA = 5  # tope conservador -- todo el lote corre dentro
# de una sola request HTTP (sin cola de jobs, ver docstring del router), y
# aunque las llamadas a Claude van en paralelo, un tope evita que alguien
# mande 30 PDFs de una y la request se cuelgue esperando o pegue timeout.


@router.post("/documentos/upload")
@limiter.limit("5/minute")
async def upload_documentos(
    request: Request,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(require_permission("facturacion.upload")),
    db: AsyncSession = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="No se recibió ningún archivo")
    if len(files) > _MAX_ARCHIVOS_POR_CARGA:
        raise HTTPException(status_code=400, detail=f"Máximo {_MAX_ARCHIVOS_POR_CARGA} archivos por carga")

    archivos: list[tuple[str, str, bytes]] = []
    for file in files:
        filename = file.filename or "factura.pdf"
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"'{filename}' no es un PDF")
        file_bytes = await read_limited(file, "PDF")
        archivos.append((filename, file.content_type or "application/pdf", file_bytes))

    documentos = await documentos_service.crear_documentos_y_extraer(db, archivos, current_user.id)
    await db.commit()
    for documento in documentos:
        await db.refresh(documento)
    return [documentos_service.documento_to_dict(d) for d in documentos]


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
    cuenta_id: int
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
    await _get_cuenta_or_404(db, payload.cuenta_id)  # 404 claro en vez de un IntegrityError de la FK
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
    presupuesto_cuenta_id: int | None = Query(None),
    canjes_cuenta_id: int | None = Query(None),
    _: User = Depends(require_permission("facturacion.view")),
    db: AsyncSession = Depends(get_db),
):
    return await documentos_service.obtener_dashboard(
        db, limit, offset, presupuesto_cuenta_id, canjes_cuenta_id,
    )


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
