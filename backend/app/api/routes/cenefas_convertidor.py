"""Rutas /tools/cenefas/convertidor/ — Convertidor de Excel de gestión.

Sin jobs asíncronos ni Redis: parsear un Excel y hacer lookups de SKU es
rápido, a diferencia de renderizar PPTX — no hay razón para repetir acá el
patrón de jobs del generador de Cenefas."""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import client_ip as _client_ip, require_permission
from app.core.rate_limit import limiter
from app.core.uploads import read_limited
from app.models.audit_log import AuditLog
from app.models.convertidor_mapeo import ConvertidorMapeo
from app.models.sku_descripcion import SkuDescripcion
from app.models.user import User
from app.services.cenefas.convertidor import (
    ConvertidorParseError,
    build_output_workbook,
    detectar_fila_headers,
    leer_filas,
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
from app.services.cenefas.convertidor_variables import VARIABLES_MAPEABLES
from app.services.ai_usage_service import resumir_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/cenefas/convertidor", tags=["cenefas-convertidor"])


@router.post("/preview")
@limiter.limit("20/minute")
async def preview(
    request: Request,
    excel: UploadFile = File(...),
    mapeo_json: str = Form(default="{}", description='JSON {variable: nombre_de_columna} de la pantalla de mapeo'),
    valores_json: str = Form(default="{}", description='JSON {variable: texto_fijo} escrito a mano en la pantalla de mapeo'),
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    excel_bytes = await read_limited(excel, "Excel")
    try:
        mapeo = {str(k): str(v) for k, v in (json.loads(mapeo_json or "{}") or {}).items()}
        valores = {str(k): str(v) for k, v in (json.loads(valores_json or "{}") or {}).items()}
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="El mapeo de columnas no es un JSON válido")
    # Una variable fuera de la lista mapeable no tendría efecto (ver
    # construir_variables) -- se descarta acá para que el resultado no
    # dependa de qué mandó el cliente.
    mapeo = {k: v for k, v in mapeo.items() if k in VARIABLES_MAPEABLES}
    valores = {k: v for k, v in valores.items() if k in VARIABLES_MAPEABLES}
    # Las dos formas son excluyentes por variable: si llegaran las dos, gana
    # el valor escrito a mano, que es lo explícito para esta corrida.
    mapeo = {k: v for k, v in mapeo.items() if not str(valores.get(k, "")).strip()}
    # Tinín solo entra a clasificar columnas de fecha sin alias reconocido si
    # el usuario tiene el permiso de ese agente específico (misma separación
    # ai.don_tino/ai.dona_tina/ai.tinin/ai.triada que el resto de la IA acá) —
    # sin el permiso, esas columnas simplemente quedan sin reconocer, como si
    # no hubiera IA disponible en este ambiente.
    allow_ai = bool(settings.ANTHROPIC_API_KEY) and (
        current_user.is_superuser or "ai.tinin" in (current_user.permissions or [])
    )
    try:
        parsed, learned_aliases_count, _headers = await parse_input_excel(
            excel_bytes, excel.filename or "",
            db=db, current_user_id=current_user.id, allow_ai=allow_ai,
            mapeo=mapeo, valores=valores,
        )
    except ConvertidorParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("convertidor preview parse error: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error al parsear el archivo: {e}")

    rows, ma_pairs = await match_rows(parsed, db)
    if learned_aliases_count:
        await db.commit()
    matched = sum(1 for r in rows if r["matched"])
    return {
        "rows": rows,
        "total": len(rows),
        "matched_count": matched,
        "unmatched_count": len(rows) - matched,
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
    """Una fila tal como vuelve del grid.

    Lleva las 26 variables (lo que se exporta) más el contexto del export de
    gestión, que no se exporta pero sí se usa para recalcular los warnings
    server-side: el coloreado del Excel final no confía en el array que
    mandó el browser.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    row_id: int
    matched: bool = False

    # -- contexto de gestión (no se exporta) ------------------------------
    nombre_articulo:     str = ""
    comprador:           str = ""
    moneda:              str = "$"
    oferta_origen:       str = ""
    oferta_det:          str = ""
    descripcion_web:     str = ""
    precio_raw:          str = ""
    precio_anterior_raw: str = ""
    es_fiambre_kg:       bool = False
    warnings_mecanica:   list[str] = Field(default_factory=list)

    # -- las 26 variables --------------------------------------------------
    codigo:               str = ""
    descripcion:          str = ""
    mecanica:             str = ""
    precioRegular:        str = ""
    decimalPrecioRegular: str = ""
    precioOferta:         str = ""
    decimalPrecioOferta:  str = ""
    ofertaUno:            str = ""
    decimalPrecioUno:     str = ""
    ofertaDos:            str = ""
    decimalPrecioDos:     str = ""
    ofertaTres:           str = ""
    decimalPrecioTres:    str = ""
    ofertaCuatro:         str = ""
    decimalPrecioCuatro:  str = ""
    precioBanco:          str = ""
    decimalPrecioBanco:   str = ""
    banco:                str = ""
    vigencia:             str = ""
    aclaracionUno:        str = ""
    aclaracionDos:        str = ""
    aclaracionTres:       str = ""
    legales:              str = ""
    dia:                  str = ""
    mes:                  str = ""
    # La única variable con un carácter no ASCII. Pydantic no acepta "año"
    # como nombre de campo con tilde sin alias, así que el campo se llama
    # anio y el alias es el nombre real que viaja por la red.
    anio:                 str = Field(default="", alias="año")

    def to_export(self) -> dict:
        d = self.model_dump()
        d["año"] = d.pop("anio", "")
        return d


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
    xlsx_bytes = build_output_workbook([r.to_export() for r in payload.rows])
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
    return {"respuesta": result["respuesta"], "usage": resumir_usage(result["usage_items"])}


# ---------------------------------------------------------------------------
# Pantalla de mapeo
# ---------------------------------------------------------------------------

@router.post("/columnas")
@limiter.limit("20/minute")
async def columnas(
    request: Request,
    excel: UploadFile = File(...),
    _: User = Depends(require_permission("cenefas.view")),
):
    """Columnas del archivo subido, para armar la pantalla de mapeo.

    Se llama ANTES de convertir: la persona necesita ver qué columnas trae su
    archivo para decir a cuál corresponde cada variable. Devuelve también un
    par de valores de muestra por columna, que es lo que en la práctica
    permite reconocerla cuando el nombre no dice nada ("COMENTARIOS2").
    """
    excel_bytes = await read_limited(excel, "Excel")
    try:
        filas = leer_filas(excel_bytes, excel.filename or "")
    except Exception as e:
        logger.error("convertidor columnas: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"No pude leer el archivo: {e}")

    header_idx = detectar_fila_headers(filas)
    if header_idx is None:
        raise HTTPException(
            status_code=400,
            detail="No encontré una columna 'CODIGO' reconocible en las primeras filas "
                   "— verificá que sea el export crudo de gestión.",
        )

    header = filas[header_idx]
    muestras = filas[header_idx + 1: header_idx + 6]
    columnas_out = []
    for i, celda in enumerate(header):
        nombre = str(celda).strip() if celda is not None else ""
        if not nombre:
            continue
        valores = [
            str(f[i]).strip() for f in muestras
            if i < len(f) and f[i] is not None and str(f[i]).strip()
        ]
        columnas_out.append({"nombre": nombre, "muestras": valores[:3]})

    return {
        "columnas": columnas_out,
        "variables_mapeables": list(VARIABLES_MAPEABLES),
        "total_filas": max(len(filas) - header_idx - 1, 0),
    }


# ---------------------------------------------------------------------------
# Plantillas de mapeo
# ---------------------------------------------------------------------------

class MapeoUpsert(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    destino: str | None = Field(default=None, max_length=50)
    mapeo: dict[str, str] = Field(default_factory=dict)
    valores: dict[str, str] = Field(default_factory=dict)

    @field_validator("mapeo", "valores")
    @classmethod
    def _solo_mapeables(cls, v: dict[str, str]) -> dict[str, str]:
        # Una variable fuera de la lista no tendría efecto (construir_variables
        # solo aplica las mapeables), así que se rechaza en vez de guardarla y
        # dejar a alguien esperando que funcione.
        desconocidas = set(v) - set(VARIABLES_MAPEABLES)
        if desconocidas:
            raise ValueError(f"Variables no mapeables: {sorted(desconocidas)}")
        return {k: val for k, val in v.items() if val and val.strip()}


@router.get("/mapeos")
async def listar_mapeos(
    destino: str | None = Query(None, description="Filtra por mundo; los sin destino salen siempre"),
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ConvertidorMapeo).order_by(ConvertidorMapeo.nombre)
    if destino:
        # Los mapeos sin destino sirven para cualquier mundo, así que
        # aparecen siempre -- filtrarlos obligaría a duplicar el mismo mapeo
        # una vez por mundo.
        stmt = stmt.where(
            or_(ConvertidorMapeo.destino == destino, ConvertidorMapeo.destino.is_(None))
        )
    result = await db.execute(stmt)
    return [
        {
            "id": str(m.id), "nombre": m.nombre, "destino": m.destino,
            "mapeo": m.mapeo, "valores": m.valores or {},
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        }
        for m in result.scalars().all()
    ]


@router.post("/mapeos", status_code=201)
async def crear_mapeo(
    payload: MapeoUpsert,
    request: Request,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    nombre = payload.nombre.strip()
    # Mismo nombre + mismo destino se pisa en vez de duplicar: el gesto real
    # es "guardá esto como 'Mundo Hogar'", y a la segunda vez se espera
    # actualizar, no terminar con dos entradas iguales en el menú.
    existente = (await db.execute(
        select(ConvertidorMapeo).where(
            ConvertidorMapeo.nombre == nombre,
            ConvertidorMapeo.destino.is_(None) if payload.destino is None
            else ConvertidorMapeo.destino == payload.destino,
        )
    )).scalar_one_or_none()

    if existente is not None:
        existente.mapeo = payload.mapeo
        existente.valores = payload.valores
        accion = "cenefas.mapeo.update"
        m = existente
    else:
        m = ConvertidorMapeo(
            nombre=nombre, destino=payload.destino, mapeo=payload.mapeo,
            valores=payload.valores, created_by=current_user.id,
        )
        db.add(m)
        accion = "cenefas.mapeo.create"

    await db.flush()
    db.add(AuditLog(
        user_id=current_user.id, action=accion, resource="convertidor_mapeo",
        resource_id=str(m.id), details={"nombre": nombre, "destino": payload.destino},
        ip_address=_client_ip(request),
    ))
    await db.commit()
    return {"id": str(m.id), "nombre": m.nombre, "destino": m.destino,
            "mapeo": m.mapeo, "valores": m.valores or {}}


@router.delete("/mapeos/{mapeo_id}", status_code=204)
async def borrar_mapeo(
    mapeo_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    m = await db.get(ConvertidorMapeo, mapeo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Plantilla de mapeo no encontrada")
    db.add(AuditLog(
        user_id=current_user.id, action="cenefas.mapeo.delete", resource="convertidor_mapeo",
        resource_id=str(mapeo_id), details={"nombre": m.nombre}, ip_address=_client_ip(request),
    ))
    await db.delete(m)
    await db.commit()
