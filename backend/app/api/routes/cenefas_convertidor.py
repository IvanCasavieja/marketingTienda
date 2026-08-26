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
from app.models.convertidor_header_alias import ConvertidorHeaderAlias
from app.services.cenefas.variables import LEGAL_ALCOHOL, es_alcohol
from app.services.cenefas.convertidor import (
    _INPUT_ALIASES,
    _norm,
    ConvertidorParseError,
    build_output_workbook,
    grupos_para_skus,
    guardar_grupo_unificado,
    detectar_fila_headers,
    leer_filas,
    listar_hojas,
    match_rows,
    parse_input_excel,
    upsert_sku_descripcion,
)
from app.services.cenefas.convertidor_ai import (
    _CAMPOS_SUGERIBLES,
    detectar_alcohol,
    _ROWS_MAX_PER_REQUEST,
    detectar_grupos_unificables,
    sugerir_campos_de_columnas,
    generar_descripciones,
)
from app.services.cenefas import tinin_agent
from app.services.cenefas import conocimiento as saber
from app.services.cenefas.convertidor_variables import VARIABLES_MAPEABLES
from app.services.cenefas.variables import ORDEN_EXPORT
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
    hoja: int | None = Form(default=None, description="Índice de la hoja a convertir (0-based). Sin esto, la primera."),
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
            mapeo=mapeo, valores=valores, hoja=hoja,
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

    Lleva las 31 variables (lo que se exporta) más el contexto del export de
    gestión, que no se exporta pero sí se usa para recalcular los warnings
    server-side: el coloreado del Excel final no confía en el array que
    mandó el browser.

    OJO: `extra="ignore"`. Una variable que falte acá se descarta en silencio
    al exportar, aunque el grid la muestre llena. Ya pasó con tipoOferta: 13
    filas la tenían y el Excel salía sin esa columna. Por eso al final del
    módulo hay un chequeo que compara estos campos contra ORDEN_EXPORT y
    revienta al importar si se desincronizan.
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

    # -- las 31 variables --------------------------------------------------
    codigo:               str = ""
    descripcion:          str = ""
    mecanica:             str = ""
    tipoOferta:           str = ""
    tipoOfertaComprando:  str = ""
    unidad:               str = ""
    precioRegular:        str = ""
    decimalPrecioRegular: str = ""
    precioOferta:         str = ""
    decimalPrecioOferta:  str = ""
    promoOferta:          str = ""
    decimalPromoOferta:   str = ""
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
        # El motivo de cada fallo, para que la pantalla pueda decir QUÉ pasó en
        # vez de "completalos a mano" a secas.
        "errores": result.get("errores", []),
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
    # Las filas que la persona tiene en pantalla. Sin esto Tinín contesta a
    # ciegas: ante "por qué esta fila está marcada" solo puede tirar hipótesis.
    # Se acotan acá y se recortan de nuevo en el agente (ver _bloque_filas).
    filas: list[dict] = Field(default_factory=list, max_length=200)


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
            filas=payload.filas,
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

    Devuelve TODAS las hojas, cada una con sus columnas. Un boceto real trae
    varias y son listados distintos: el export crudo de gestión, el "Frente"
    curado a mano y el "Dorso". Hasta 08/2026 se leía la primera y punto, así
    que un archivo de tres hojas se convertía por la que no era y nadie se
    enteraba hasta mirar el resultado.

    Una hoja que no se puede leer no rompe el pedido: viaja con su `error` y
    las demás se devuelven igual. Solo se falla si NINGUNA sirve.
    """
    excel_bytes = await read_limited(excel, "Excel")
    try:
        nombres = listar_hojas(excel_bytes, excel.filename or "")
    except Exception as e:
        logger.error("convertidor columnas: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"No pude leer el archivo: {e}")

    def _columnas_de(filas: list, header_idx: int) -> list[dict]:
        header = filas[header_idx]
        muestras = filas[header_idx + 1: header_idx + 6]
        salida = []
        for i, celda in enumerate(header):
            nombre = str(celda).strip() if celda is not None else ""
            if not nombre:
                continue
            valores = [
                str(f[i]).strip() for f in muestras
                if i < len(f) and f[i] is not None and str(f[i]).strip()
            ]
            salida.append({"nombre": nombre, "muestras": valores[:3]})
        return salida

    hojas_out: list[dict] = []
    for indice, nombre_hoja in enumerate(nombres):
        try:
            filas = leer_filas(excel_bytes, excel.filename or "", indice)
        except Exception as e:
            hojas_out.append({
                "indice": indice, "nombre": nombre_hoja, "columnas": [],
                "total_filas": 0, "error": f"No pude leer la hoja: {e}",
            })
            continue

        header_idx = detectar_fila_headers(filas)
        if header_idx is None:
            hojas_out.append({
                "indice": indice, "nombre": nombre_hoja, "columnas": [],
                "total_filas": 0,
                "error": "No encontré una columna 'CODIGO' reconocible en las primeras filas",
            })
            continue

        # Filas con algo escrito, no la distancia hasta el final de la hoja:
        # openpyxl reporta como usadas las filas que solo tienen formato, y una
        # hoja vacía con estilos aparecía con cientos de filas fantasma.
        con_datos = sum(
            1 for f in filas[header_idx + 1:]
            if any(v is not None and str(v).strip() for v in f)
        )
        hojas_out.append({
            "indice": indice, "nombre": nombre_hoja,
            "columnas": _columnas_de(filas, header_idx),
            "total_filas": con_datos, "error": None,
        })

    utiles = [h for h in hojas_out if h["error"] is None]
    if not utiles:
        raise HTTPException(
            status_code=400,
            detail="No encontré una columna 'CODIGO' reconocible en ninguna hoja "
                   "— verificá que sea el export crudo de gestión.",
        )

    # La sugerida es la primera que TRAE FILAS: en los bocetos reales la última
    # hoja suele estar vacía (solo encabezados) y no sirve para arrancar.
    con_filas = [h for h in utiles if h["total_filas"] > 0]
    sugerida = (con_filas or utiles)[0]

    return {
        "hojas": hojas_out,
        "hoja_sugerida": sugerida["indice"],
        # Compat: lo que el front leía cuando solo existía una hoja.
        "columnas": sugerida["columnas"],
        "variables_mapeables": list(VARIABLES_MAPEABLES),
        "total_filas": sugerida["total_filas"],
    }


# ---------------------------------------------------------------------------
# Bebidas con alcohol que no se nombran por tipo
# ---------------------------------------------------------------------------


class AlcoholItem(BaseModel):
    row_id: int
    codigo: str = ""
    descripcion: str = ""
    nombre_articulo: str = ""


class DetectarAlcoholRequest(BaseModel):
    rows: list[AlcoholItem]


@router.post("/alcohol/detectar-ia")
@limiter.limit("5/minute")
async def detectar_alcohol_ia(
    request: Request,
    payload: DetectarAlcoholRequest,
    current_user: User = Depends(require_permission("ai.tinin")),
    db: AsyncSession = Depends(get_db),
):
    """Bebidas con alcohol entre las filas que el chequeo por TIPO no reconoció.

    Solo se le pregunta por lo que `es_alcohol()` dejó pasar: una cerveza ya está
    resuelta por código, gratis y sin margen de error, y no tiene sentido gastar
    una llamada en confirmarla.

    Devuelve sugerencias. La leyenda no se agrega sola."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="La detección con IA no está configurada en este ambiente")
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No hay filas para revisar")

    # El filtro por tipo se aplica ACA y no en el cliente: es la misma funcion
    # que despues decide la leyenda al generar, asi que no puede haber dos
    # criterios distintos.
    pendientes = [
        r.model_dump() for r in payload.rows[:_ROWS_MAX_PER_REQUEST]
        if not es_alcohol(r.descripcion, r.nombre_articulo)
    ]
    ya_reconocidas = len(payload.rows) - len(pendientes)

    resultado = await detectar_alcohol(pendientes, db, current_user.id)
    await db.commit()
    return {
        "alcohol":         resultado["alcohol"],
        "errores":         resultado["errores"],
        "revisadas":       len(pendientes),
        "ya_reconocidas":  ya_reconocidas,
        "leyenda":         LEGAL_ALCOHOL,
    }


# ---------------------------------------------------------------------------
# Grupos unificados: varios SKU, un solo cartel
# ---------------------------------------------------------------------------


class GrupoUnificadoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str = Field(min_length=1, max_length=300)
    skus: list[str] = Field(min_length=2)


@router.post("/grupos-unificados", status_code=201)
async def crear_grupo_unificado(
    payload: GrupoUnificadoIn,
    current_user: User = Depends(require_permission("cenefas.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Guarda el grupo por su CONJUNTO de SKU, sin tocar las descripciones
    individuales de cada uno: esas son las que permiten rearmar el texto cuando
    mañana venga solo una parte del grupo."""
    try:
        grupo = await guardar_grupo_unificado(
            db, nombre=payload.nombre, descripcion=payload.descripcion,
            skus=payload.skus, user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(grupo.id), "nombre": grupo.nombre, "skus": grupo.skus}


@router.post("/grupos-unificados/buscar")
async def buscar_grupos_unificados(
    payload: dict,
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Grupos guardados que tocan los SKU de la grilla actual.

    Los `completo: false` son el caso que importa: la promo trae parte del
    grupo, así que su descripción guardada menciona productos que hoy no están
    en oferta y NO se puede reusar tal cual."""
    skus = [str(x) for x in (payload.get("skus") or [])][:500]
    grupos = await grupos_para_skus(db, skus)
    return {
        "grupos":    grupos,
        "parciales": [g for g in grupos if not g["completo"]],
    }


# ---------------------------------------------------------------------------
# Columnas sin reconocer: Tinín propone, la persona confirma
# ---------------------------------------------------------------------------
#
# Agregar un alias a mano cada vez que gestión inventa un nombre nuevo es una
# carrera que se pierde ("NOMBRE DE ARTICULO" con "de", "DESCRIPCIONES WEB" en
# plural, "precioOferta" como nombre de entrada...). Y una columna que no
# matchea se ignora EN SILENCIO, así que el problema aparece mucho después y
# disfrazado de otra cosa.
#
# Estas dos rutas cierran el circuito: la primera pregunta, la segunda aprende.


@router.post("/columnas/sugerir-ia")
@limiter.limit("5/minute")
async def sugerir_columnas_ia(
    request: Request,
    excel: UploadFile = File(...),
    current_user: User = Depends(require_permission("ai.tinin")),
    db: AsyncSession = Depends(get_db),
):
    """Las columnas que el sistema no reconoció, con la propuesta de Tinín.

    No aplica nada: devuelve sugerencias para confirmar. Lo que ya está
    aprendido en ConvertidorHeaderAlias no se vuelve a preguntar."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="La sugerencia con IA no está configurada en este ambiente")

    excel_bytes = await read_limited(excel, "Excel")
    try:
        filas = leer_filas(excel_bytes, excel.filename or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No pude leer el archivo: {e}")

    idx = detectar_fila_headers(filas)
    if idx is None:
        raise HTTPException(status_code=400, detail="No encontré una fila de encabezados reconocible")

    header = filas[idx]
    muestras_filas = filas[idx + 1: idx + 1 + _MUESTRAS_PARA_IA]

    # Solo las que NO resuelve el codigo. Las que ya matchean por nombre no
    # tienen nada que preguntar.
    candidatos: list[dict] = []
    for i, celda in enumerate(header):
        nombre = str(celda).strip() if celda is not None else ""
        if not nombre:
            continue
        norm = _norm(nombre)
        if norm in _INPUT_ALIASES:
            continue
        vals = [str(f[i]).strip() for f in muestras_filas
                if i < len(f) and f[i] is not None and str(f[i]).strip()]
        candidatos.append({"header_norm": norm, "header_display": nombre, "muestras": vals[:6]})

    if not candidatos:
        return {"sugerencias": [], "ya_aprendidas": [], "errores": [], "campos": _CAMPOS_SUGERIBLES}

    # Lo ya aprendido se informa aparte: sirve para que se vea POR QUE una
    # columna con nombre raro igual funciono, sin gastar una llamada a IA.
    aprendidas = {
        r.header_norm: r.field_name
        for r in (await db.execute(
            select(ConvertidorHeaderAlias)
            .where(ConvertidorHeaderAlias.header_norm.in_([c["header_norm"] for c in candidatos]))
        )).scalars().all()
    }
    pendientes = [c for c in candidatos if c["header_norm"] not in aprendidas]

    resultado = await sugerir_campos_de_columnas(pendientes, db, current_user.id)
    await db.commit()   # persiste el ai_usage_log
    return {
        "sugerencias":   resultado["sugerencias"],
        "ya_aprendidas": [
            {"header_norm": k, "header_display": next(
                (c["header_display"] for c in candidatos if c["header_norm"] == k), k),
             "campo": v}
            for k, v in aprendidas.items()
        ],
        "errores": resultado["errores"],
        "campos":  _CAMPOS_SUGERIBLES,
    }


class AliasConfirmado(BaseModel):
    header_norm: str = Field(min_length=1, max_length=120)
    # None = "esta columna no es ninguno de los campos". Se guarda igual: es una
    # respuesta valida y evita volver a preguntar por ese header.
    campo: str | None = None

    @field_validator("campo")
    @classmethod
    def _campo_conocido(cls, v: str | None) -> str | None:
        if v is not None and v not in _CAMPOS_SUGERIBLES:
            raise ValueError(f"Campo desconocido: {v!r}")
        return v


class ConfirmarAliasRequest(BaseModel):
    aliases: list[AliasConfirmado]


@router.post("/columnas/confirmar-alias")
async def confirmar_alias_columnas(
    payload: ConfirmarAliasRequest,
    current_user: User = Depends(require_permission("cenefas.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Guarda las confirmaciones. Desde acá en adelante esos encabezados los
    resuelve el código, igual que cualquier entrada de _INPUT_ALIASES, solo que
    aprendida en vez de hardcodeada — y no vuelven a pasar por IA nunca."""
    if not payload.aliases:
        raise HTTPException(status_code=400, detail="No hay nada que confirmar")

    stmt = pg_insert(ConvertidorHeaderAlias).values(
        [{"header_norm": a.header_norm, "field_name": a.campo} for a in payload.aliases]
    )
    await db.execute(stmt.on_conflict_do_update(
        index_elements=["header_norm"],
        set_={"field_name": stmt.excluded.field_name},
    ))
    await db.commit()
    return {"guardados": len(payload.aliases)}


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
    # Guardar un mapeo es una persona diciendo "esta columna es esta variable".
    # Es la fuente más confiable que tiene el agente, así que se anota. Queda
    # como propuesta hasta que alguien la apruebe.
    try:
        await saber.aprender_de_mapeo(db, payload.mapeo, payload.destino)
    except Exception as e:                       # aprender nunca rompe guardar
        logger.warning("no se pudo aprender del mapeo: %s", e)
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


# Guarda contra el desfasaje silencioso: ConvertidorRowIn enumera las variables
# a mano y `extra="ignore"` hace que una que falte se descarte sin ruido al
# exportar. Ya pasó con tipoOferta. Si vuelve a desincronizarse, esto falla al
# importar el módulo en vez de bajar un Excel al que le falta una columna.
_campos_modelo = set(ConvertidorRowIn.model_fields) | {"año"}
_faltan_en_modelo = set(ORDEN_EXPORT) - _campos_modelo
assert not _faltan_en_modelo, (
    f"ConvertidorRowIn quedó desincronizado de ORDEN_EXPORT: faltan {sorted(_faltan_en_modelo)}. "
    "Sin esos campos, el Excel del Convertidor sale sin esas columnas y nadie se entera."
)
