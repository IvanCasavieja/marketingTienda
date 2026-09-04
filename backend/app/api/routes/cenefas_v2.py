"""Rutas /tools/cenefas/v2/ — API del nuevo motor de componentes."""
import base64 as _b64
import io
import json
import logging
import pathlib
import re
import unicodedata
import uuid
from datetime import date
import zipfile

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission, client_ip as _client_ip
from app.core.uploads import read_limited
from app.models.audit_log import AuditLog
from app.models.cenefa_destino import CenefaDestino
from app.models.cenefa_job import CenefaJob
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.models.user import User
from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.component_renderer import _detect_slot_bands, _fit_text_to_box
from app.services.cenefas.jobs import (
    confirm_generation_job,
    get_job_result,
    peek_job_products,
    run_generation_job,
)
from app.services.cenefas import conocimiento as saber
from app.services.cenefas import informe as informe_service
from app.services.cenefas.layout_engine import FORMATS
from app.services.cenefas.rules_engine import evaluate_rules
from app.services.cenefas.validation_engine import build_summary, validate_products

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/cenefas/v2", tags=["cenefas-v2"])

_STATIC_DIR = pathlib.Path(__file__).parent.parent.parent / "static" / "cenefa_templates"

# Cache en memoria de las definiciones builtin (se parsean una sola vez al arrancar)
_builtin_definitions_cache: list | None = None

_BUILTIN_PPTX = {
    "a4": {
        "slug":      "a4",
        "name":      "Cenefa A4",
        "format_id": "a4",
        "file":      "Base cenefa A4 1.pptx",
    },
    "pinchos": {
        "slug":      "pinchos",
        "name":      "Pinchos",
        "format_id": "pinchos",
        "file":      "Base pinchos 1.pptx",
    },
    "black": {
        "slug":      "black",
        "name":      "Cenefas 3xA4",
        "format_id": "3xa4",
        "file":      "Bases cenefas BLACK 1.pptx",
    },
}

# ---------------------------------------------------------------------------
# Importación de PPTX
# ---------------------------------------------------------------------------

@router.post("/import-pptx")
async def import_pptx(
    file: UploadFile = File(..., description="Archivo PPTX a importar"),
    name: str = Form(default="Template importado"),
    category: str | None = Form(default=None),
    _: User = Depends(require_permission("cenefas.import")),
):
    """Parsea un PPTX y devuelve una definición v2 lista para cargar en el editor."""
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="El archivo debe ser .pptx")

    pptx_bytes = await read_limited(file, "PPTX")

    from app.services.cenefas.pptx_importer import import_pptx as _import
    try:
        definition = _import(pptx_bytes, name=name.strip() or "Template importado", category=category)
    except Exception as exc:
        logger.warning("import_pptx error: %s", exc)
        raise HTTPException(status_code=422, detail=f"No se pudo parsear el PPTX: {exc}")

    return definition


@router.get("/builtin-definitions")
async def get_builtin_definitions(_: User = Depends(require_permission("cenefas.view"))):
    """Devuelve las definiciones v2 de los templates predeterminados.
    Las parsea una vez al primer request y cachea en memoria."""
    global _builtin_definitions_cache

    if _builtin_definitions_cache is not None:
        return _builtin_definitions_cache

    from app.services.cenefas.pptx_importer import import_pptx as _import

    result = []
    for slug, info in _BUILTIN_PPTX.items():
        path = _STATIC_DIR / info["file"]
        if not path.exists():
            logger.warning("builtin-definitions: archivo no encontrado: %s", path)
            continue
        try:
            definition = _import(path.read_bytes(), name=info["name"])
        except Exception as exc:
            logger.warning("builtin-definitions: error parseando %s: %s", slug, exc)
            continue
        result.append({
            "slug":       slug,
            "name":       info["name"],
            "format_id":  info["format_id"],
            "definition": definition,
        })

    _builtin_definitions_cache = result
    return result


# ---------------------------------------------------------------------------
# Formatos del sistema
# ---------------------------------------------------------------------------

@router.get("/formats")
async def list_formats(_: User = Depends(require_permission("cenefas.view"))):
    """Devuelve los formatos disponibles con sus dimensiones."""
    return [
        {
            "id":        fmt_id,
            "label":     fmt["label"],
            "width_cm":  fmt["width_cm"],
            "height_cm": fmt["height_cm"],
            "slots":     fmt["slots"],
            "slot_cols": fmt.get("slot_cols", 1),
            "slot_rows": fmt.get("slot_rows", 1),
        }
        for fmt_id, fmt in FORMATS.items()
    ]


class _SlotBandsRequest(BaseModel):
    components: list[dict]


@router.post("/slot-bands")
async def detect_slot_bands(
    payload: _SlotBandsRequest,
    _: User = Depends(require_permission("cenefas.view")),
):
    """Agrupa los componentes de una plantilla multi-banda (3xA4/6xA4/A5/
    pinchos) en bandas -- una por cenefa de la hoja -- para que el editor
    standalone pueda vincular edición entre bandas (mover/achicar/agrandar
    una variable en una banda replica el cambio en las demás), igual que ya
    hace PreviewStep con job.slot_bands.

    Reusa `_detect_slot_bands` tal cual -- es la misma lógica ya probada en
    generación (jobs.py), no se reimplementa nada acá ni en el frontend."""
    bands = _detect_slot_bands(payload.components)
    return {
        "slot_bands": [[c["id"] for c in band] for band in bands] if bands else None,
    }


# ---------------------------------------------------------------------------
# CRUD de templates v2
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_templates(
    category: str | None = Query(default=None),
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    query = select(CenefaTemplateV2).order_by(CenefaTemplateV2.created_at.desc())
    if category is not None:
        query = query.where(CenefaTemplateV2.category == category)
    result = await db.execute(query)
    templates = result.scalars().all()
    return [
        {
            "id":         str(t.id),
            "name":       t.name,
            "formats":    t.formats,
            "category":   t.category,
            "is_builtin": t.is_builtin,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in templates
    ]


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: dict,
    current_user: User = Depends(require_permission("cenefas.edit")),
    db: AsyncSession = Depends(get_db),
):
    _validate_template_payload(payload)

    # source_pptx_b64: bytes del PPTX original en base64 (si el template vino
    # de importar un archivo, no de armarlo desde cero en el editor) — se
    # guarda aparte, no adentro del JSONB, para que el render final pueda
    # preservar el diseño (ver component_renderer.render_template_to_pptx).
    source_pptx_b64 = payload.pop("source_pptx_b64", None)
    source_pptx = None
    if source_pptx_b64:
        try:
            source_pptx = _b64.b64decode(source_pptx_b64)
        except Exception:
            source_pptx = None

    tmpl = CenefaTemplateV2(
        created_by=current_user.id,
        name=payload["name"].strip(),
        definition=payload,
        formats=payload.get("formats", []),
        category=payload.get("category"),
        source_pptx=source_pptx,
    )
    db.add(tmpl)
    await db.flush()
    await db.refresh(tmpl)
    return {"id": str(tmpl.id), "name": tmpl.name, "created_at": tmpl.created_at.isoformat()}


@router.get("/templates/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    tmpl = await _get_owned_template(template_id, current_user, db)
    return {
        "id":         str(tmpl.id),
        "name":       tmpl.name,
        "formats":    tmpl.formats,
        "category":   tmpl.category,
        "is_builtin": tmpl.is_builtin,
        "definition": tmpl.definition,
        "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
        "updated_at": tmpl.updated_at.isoformat() if tmpl.updated_at else None,
    }


@router.put("/templates/{template_id}")
async def update_template(
    template_id: uuid.UUID,
    payload: dict,
    current_user: User = Depends(require_permission("cenefas.edit")),
    db: AsyncSession = Depends(get_db),
):
    tmpl = await _get_owned_template(template_id, current_user, db, write_check=True)
    if tmpl.is_builtin:
        raise HTTPException(status_code=403, detail="No se pueden modificar templates del sistema")

    _validate_template_payload(payload)

    # source_pptx_b64 opcional: mismo criterio que create_template (ver línea
    # ~183) — se popea del payload ANTES de guardarlo como definition, para
    # no duplicar el base64 del pptx dentro del JSONB. Permite "Reemplazar"
    # el diseño de una plantilla ya guardada sin perder su identidad
    # (id/name/formats/category quedan a criterio del caller).
    source_pptx_b64 = payload.pop("source_pptx_b64", None)
    if source_pptx_b64:
        try:
            tmpl.source_pptx = _b64.b64decode(source_pptx_b64)
        except Exception:
            pass

    tmpl.name       = payload["name"].strip()
    tmpl.definition = payload
    tmpl.formats    = payload.get("formats", tmpl.formats)
    if "category" in payload:
        tmpl.category = payload.get("category")
    return {"id": str(tmpl.id), "name": tmpl.name}


@router.patch("/templates/{template_id}/rename")
async def rename_template(
    template_id: uuid.UUID,
    payload: dict,
    current_user: User = Depends(require_permission("cenefas.edit")),
    db: AsyncSession = Depends(get_db),
):
    tmpl = await _get_owned_template(template_id, current_user, db, write_check=True)
    if tmpl.is_builtin:
        raise HTTPException(status_code=403, detail="No se pueden modificar templates del sistema")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    tmpl.name = name
    return {"id": str(tmpl.id), "name": tmpl.name}


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    current_user: User = Depends(require_permission("cenefas.delete")),
    db: AsyncSession = Depends(get_db),
):
    tmpl = await _get_owned_template(template_id, current_user, db, write_check=True)
    if tmpl.is_builtin:
        raise HTTPException(status_code=403, detail="No se pueden eliminar templates del sistema")
    # AsyncSession.delete() es una corrutina (a diferencia de Session.delete()
    # en la API sync) -- sin el await acá, la llamada crea un objeto
    # corrutina que nunca corre: el delete nunca se registra en la unit-of-
    # work, el commit del get_db() de abajo no tiene nada pendiente que
    # confirmar, y el endpoint devuelve 204 sin haber borrado la fila.
    await db.delete(tmpl)


# ---------------------------------------------------------------------------
# Validación de CSV contra template
# ---------------------------------------------------------------------------

@router.post("/validate")
async def validate_csv(
    excel: UploadFile = File(..., description="Archivo Excel o CSV"),
    template_id: uuid.UUID = Form(...),
    vigencia: str = Form(default=""),
    legales: str = Form(default=""),
    usar_legales: bool = Form(default=False),
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Valida el CSV contra un template v2 sin generar el PPTX.

    Devuelve:
    - total de filas parseadas
    - variables requeridas faltantes en el CSV
    - resumen por regla: cuántas filas activan cada regla
    """
    tmpl = await _get_owned_template(template_id, current_user, db)
    definition = tmpl.definition

    excel_bytes = await read_limited(excel, "Excel")
    try:
        products = load_products_from_bytes(excel_bytes, vigencia, legales, usar_legales)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Columna requerida faltante en el Excel: {e}")
    except Exception as e:
        logger.error("validate_csv parse error: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error al parsear el archivo: {e}")

    rules       = definition.get("rules", [])
    variables   = {v["name"]: v for v in definition.get("variables", [])}
    rule_names  = {r["id"]: r.get("name", r["id"]) for r in rules if "id" in r}

    # Verificar variables requeridas contra columnas disponibles del primer producto
    missing_required: list[str] = []
    if products:
        sample = products[0]
        for var_name, var_def in variables.items():
            if var_def.get("required") and var_name not in sample:
                missing_required.append(var_name)

    # Contar activaciones por regla
    rule_hits: dict[str, int] = {r["id"]: 0 for r in rules if "id" in r}
    for product in products:
        visibility = evaluate_rules(rules, product)
        for rule in rules:
            if "id" not in rule:
                continue
            action = rule.get("action", {}).get("type", "show")
            comp_id = rule.get("target_component_id", "")
            is_visible = visibility.get(comp_id, True)
            if (action == "show" and is_visible) or (action == "hide" and not is_visible):
                rule_hits[rule["id"]] += 1

    return {
        "total_rows":       len(products),
        "missing_required": missing_required,
        "rule_summary": [
            {
                "rule_id":   rule_id,
                "rule_name": rule_names.get(rule_id, rule_id),
                "hits":      hits,
                "pct":       round(hits / len(products) * 100, 1) if products else 0,
            }
            for rule_id, hits in rule_hits.items()
        ],
        "status": "error" if missing_required else "ok",
    }


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

async def _get_owned_template(
    template_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    *,
    write_check: bool = False,
) -> CenefaTemplateV2:
    result = await db.execute(
        select(CenefaTemplateV2).where(CenefaTemplateV2.id == template_id)
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template no encontrado")
    if write_check and not tmpl.is_builtin and not current_user.is_superuser:
        if tmpl.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="No tenés permiso para modificar este template")
    return tmpl


def _validate_template_payload(payload: dict) -> None:
    required_keys = {"name", "components", "variables", "rules"}
    missing = required_keys - set(payload.keys())
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Campos requeridos faltantes en el template: {sorted(missing)}",
        )
    if not payload.get("name", "").strip():
        raise HTTPException(status_code=422, detail="El campo 'name' no puede estar vacío")


# ---------------------------------------------------------------------------
# Jobs de generación
# ---------------------------------------------------------------------------

def _parse_image_overrides(image_overrides_json: str) -> dict | None:
    """{variable: "ext:base64"} -> {variable: (bytes, ext)}.

    Un JSON roto no rompe la generación: se ignora y la cenefa sale sin la
    imagen, que es preferible a perder el trabajo entero por una cocarda.
    """
    try:
        crudo = json.loads(image_overrides_json or "{}")
        parsed: dict[str, tuple[bytes, str]] = {}
        for var_name, encoded in crudo.items():
            if ":" in encoded:
                ext, b64_data = encoded.split(":", 1)
                parsed[var_name] = (_b64.b64decode(b64_data), ext.lower())
        return parsed or None
    except Exception:
        return None


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    background_tasks: BackgroundTasks,
    request: Request,
    excel: UploadFile = File(..., description="Archivo Excel con hoja 'Cenefas'"),
    format_id: str | None = Form(
        default=None,
        description="Formato destino: a4 | a3 | 3xa4 | pinchos | a5 | 6xa4. "
                    "Si se omite, se usa el master_format detectado de la plantilla.",
    ),
    export_type: str = Form(default="pptx", description="Tipo de salida: pptx"),
    builtin_slug: str | None = Form(None, description="Slug de una plantilla base del repo"),
    template_id: uuid.UUID | None = Form(None, description="UUID de la plantilla del equipo"),
    template_upload: UploadFile | None = File(None, description="PPTX subido al vuelo, sin guardar como plantilla"),
    vigencia: str = Form(default=""),
    legales: str = Form(default="", description="Texto de legales -- solo se usa si usar_legales=true"),
    usar_legales: bool = Form(default=False, description="Habilita sustituir la variable legales"),
    image_overrides_json: str = Form(
        default="{}",
        description='JSON {variable_name: "ext:base64"} con imágenes a inyectar en componentes de imagen',
    ),
    current_user: User = Depends(require_permission("cenefas.generate")),
    db: AsyncSession = Depends(get_db),
):
    """Inicia un job de generación async.

    Acepta una plantilla del equipo, una plantilla base del repo o un PPTX
    subido al vuelo. Los tres caminos terminan en el mismo motor."""
    if format_id is not None and format_id not in FORMATS:
        raise HTTPException(status_code=400, detail=f"Formato inválido. Disponibles: {list(FORMATS)}")
    if not builtin_slug and not template_id and not template_upload:
        raise HTTPException(
            status_code=400,
            detail="Debés especificar una plantilla (template_id, builtin_slug o template_upload)",
        )
    if not excel.filename or not excel.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="El Excel debe ser .xlsx o .xlsm")

    excel_bytes = await read_limited(excel, "Excel")
    template_upload_bytes = await read_limited(template_upload, "PPTX") if template_upload else None

    image_overrides = _parse_image_overrides(image_overrides_json)

    # Plantilla y mundo quedan grabados en el job. Este camino no los guardaba,
    # y por eso las corridas de junio al 23/08 figuran como "(sin registrar)"
    # en el informe de produccion: el dato existia en el request y se perdia.
    # Con builtin_slug o template_upload no hay plantilla del equipo de donde
    # sacar el mundo, asi que ahi quedan en NULL igual que antes.
    tmpl_nombre: str | None = None
    tmpl_categoria: str | None = None
    if template_id is not None:
        tmpl = (await db.execute(
            select(CenefaTemplateV2).where(CenefaTemplateV2.id == template_id)
        )).scalar_one_or_none()
        if tmpl is None:
            raise HTTPException(status_code=404, detail=f"Plantilla {template_id} no encontrada")
        tmpl_nombre, tmpl_categoria = tmpl.name, tmpl.category

    job = CenefaJob(
        created_by=current_user.id,
        status="pending",
        format=format_id or "",  # se resuelve en run_generation_job si viene vacío
        export_type=export_type,
        excel_nombre=excel.filename,
        template_id=template_id,
        template_nombre=tmpl_nombre,
        categoria=tmpl_categoria,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    job_id = job.id
    db.add(AuditLog(
        user_id=current_user.id, action="cenefas.job.create", resource="cenefa_job", resource_id=str(job_id),
        details={"format": format_id, "export_type": export_type}, ip_address=_client_ip(request),
    ))
    # Commit explícito acá: BackgroundTasks corre en un momento del ciclo de
    # request/response que no está garantizado a ser posterior al commit
    # automático de la dependencia get_db — sin esto, run_generation_job
    # puede abrir su propia sesión y no encontrar todavía esta fila, y el
    # job queda colgado en "pending" para siempre (get_job hace return sin
    # tocar el status). El AuditLog viaja en el mismo commit.
    await db.commit()

    background_tasks.add_task(
        run_generation_job,
        job_id=job_id,
        excel_bytes=excel_bytes,
        builtin_slug=builtin_slug,
        template_v2_id=template_id,
        template_upload_bytes=template_upload_bytes,
        target_format=format_id,
        vigencia=vigencia,
        legales=legales,
        usar_legales=usar_legales,
        image_overrides=image_overrides,
    )

    return {"job_id": str(job_id), "status": "pending", "format": format_id}


@router.post("/jobs/{job_id}/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm_job(
    job_id: uuid.UUID,
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission("cenefas.generate")),
    db: AsyncSession = Depends(get_db),
):
    """Confirma el preview (con los componentes eventualmente reposicionados
    por el usuario) y dispara la generación final del PPTX.

    payload: {"components": [{"id": "...", "base_bounds": {"x","y","width","height"}}]}
    — solo hace falta mandar los que se movieron, el resto conserva su
    posición original."""
    job = await _get_job(job_id, current_user, db)
    if job.status != "preview":
        raise HTTPException(
            status_code=409,
            detail=f"El job no está en estado 'preview' (estado actual: {job.status})",
        )

    position_overrides = payload.get("components") or []

    # Marcarlo "running" ya mismo (no al empezar el background task) para
    # que un segundo POST /confirm mientras el primero corre choque con el
    # 409 de arriba en vez de disparar dos renders en paralelo.
    job.status = "running"
    await db.commit()

    background_tasks.add_task(
        confirm_generation_job,
        job_id=job_id,
        position_overrides=position_overrides,
    )

    return {"job_id": str(job_id), "status": "running"}


# ---------------------------------------------------------------------------
# Conocimiento del agente
# ---------------------------------------------------------------------------

class DecidirConocimiento(BaseModel):
    # activo = aprobado y entra al contexto del agente
    # descartado = rechazado, y no vuelve a proponerse
    # archivado = fue cierto pero ya no aplica
    estado: str
    # Permite corregir el texto al aprobarlo, en vez de rechazar y reescribir.
    contenido: str | None = None


@router.get("/conocimiento")
async def listar_conocimiento(
    estado: str | None = Query(None, description="propuesto | activo | descartado | archivado"),
    tipo: str | None = Query(None),
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Lo que el modulo aprendio de como se lo usa.

    Nada de esto esta activo hasta que una persona lo aprueba: lo `propuesto`
    es lo que el sistema noto y todavia no miro nadie.
    """
    items = await saber.listar(db, estado=estado, tipo=tipo)
    return [
        {
            "id":          str(i.id),
            "tipo":        i.tipo,
            "contenido":   i.contenido,
            "detalle":     i.detalle or {},
            "origen":      i.origen,
            "estado":      i.estado,
            "veces_visto": i.veces_visto,
            "visto_at":    i.visto_at.isoformat() if i.visto_at else None,
            "decidido_at": i.decidido_at.isoformat() if i.decidido_at else None,
        }
        for i in items
    ]


@router.patch("/conocimiento/{item_id}")
async def decidir_conocimiento(
    item_id: uuid.UUID,
    payload: DecidirConocimiento,
    request: Request,
    current_user: User = Depends(require_permission("cenefas.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Aprueba, descarta o archiva algo que el modulo aprendio.

    Aprobar hace que entre al contexto del agente. Descartar es definitivo en
    el sentido de que no vuelve a proponerse solo, aunque se siga contando
    cuantas veces reaparece.
    """
    try:
        item = await saber.decidir(db, item_id, payload.estado, current_user.id, payload.contenido)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if item is None:
        raise HTTPException(status_code=404, detail="No encontre eso")
    db.add(AuditLog(
        user_id=current_user.id, action=f"cenefas.conocimiento.{payload.estado}",
        resource="cenefa_conocimiento", resource_id=str(item_id),
        details={"contenido": item.contenido[:200]}, ip_address=_client_ip(request),
    ))
    await db.commit()
    return {"id": str(item.id), "estado": item.estado, "contenido": item.contenido}


# ---------------------------------------------------------------------------
# Informe de produccion
# ---------------------------------------------------------------------------

@router.get("/informe")
async def informe(
    desde: date | None = Query(None, description="Incluye desde esta fecha (YYYY-MM-DD)"),
    hasta: date | None = Query(None, description="Incluye hasta esta fecha, inclusive"),
    template: str | None = Query(None, description="Filtra por nombre de plantilla"),
    costo: float = Query(informe_service.COSTO_POR_CENEFA, ge=0,
                         description="Costo por cenefa disenada, en pesos"),
    detalle: bool = Query(True, description="Incluye la lista corrida por corrida"),
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Cuantas cenefas se hicieron, cuantas salieron correctas y cuanto vale.

    Solo cuenta las corridas confirmadas (status "done"): una en "preview" es
    una previsualizacion que nadie confirmo, y una en "error" no produjo nada.
    Cada corrida cuenta por separado aunque sea el mismo listado reprocesado
    -- es trabajo pedido a la herramienta y se paga igual.
    """
    data = await informe_service.resumen(db, desde, hasta, template, costo)
    data["plantillas"] = await informe_service.plantillas_del_historial(db)
    if detalle:
        filas = await informe_service.detalle(db, desde, hasta, template, costo, limite=100000)
        # La lista plana se recorta; el agrupado por listado sale de todas,
        # que es justamente lo que hace util ver los intentos.
        data["detalle"] = filas[:500]
        data["intentos"] = informe_service.agrupar_intentos(filas)
    return data


class VerificarRequest(BaseModel):
    verificado: bool


@router.patch("/informe/{job_id}/verificar")
async def verificar_corrida(
    job_id: uuid.UUID,
    payload: VerificarRequest,
    request: Request,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Marca (o desmarca) una corrida como revisada y correcta por una persona.

    La validacion automatica dice si la cenefa se pudo armar, no si quedo
    bien: eso solo lo sabe alguien que abrio el PPTX. Queda registrado quien
    y cuando, para que el informe pueda separar "el motor no encontro
    problemas" de "una persona lo miro y esta bien".
    """
    # _get_job y no db.get: sin el chequeo de pertenencia, cualquiera con
    # cenefas.view podia verificar o DESverificar una corrida ajena -- y los
    # ids se los servia el propio listado. Desverificar no es cosmetico:
    # verificado=False mete la fila en el WHERE de purgar_archivos_vencidos
    # (jobs.py), asi que a los CENEFAS_RETENCION_DIAS el PPTX de otro se
    # borraba sin vuelta atras. Del otro lado, verificar corridas ajenas
    # infla "verificadas" en el informe, que es la cifra que se factura.
    job = await _get_job(job_id, current_user, db)
    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Solo se puede verificar una corrida terminada (estado: {job.status})",
        )

    job.verificado = payload.verificado
    job.verificado_por = current_user.id if payload.verificado else None
    job.verificado_at = func.now() if payload.verificado else None
    db.add(AuditLog(
        user_id=current_user.id,
        action="cenefas.corrida.verificar" if payload.verificado else "cenefas.corrida.desverificar",
        resource="cenefa_job", resource_id=str(job_id),
        details={"cenefas": job.row_count}, ip_address=_client_ip(request),
    ))
    await db.commit()
    await db.refresh(job)
    return {
        "id": str(job.id),
        "verificado": job.verificado,
        "verificado_at": job.verificado_at.isoformat() if job.verificado_at else None,
    }


@router.get("/informe/export")
async def informe_export(
    desde: date | None = Query(None),
    hasta: date | None = Query(None),
    template: str | None = Query(None),
    costo: float = Query(informe_service.COSTO_POR_CENEFA, ge=0),
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """El mismo informe en Excel: una hoja de resumen y otra con el detalle."""
    resumen = await informe_service.resumen(db, desde, hasta, template, costo)
    filas = await informe_service.detalle(db, desde, hasta, template, costo, limite=100000)
    xlsx = informe_service.a_excel(resumen, filas)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="informe_cenefas.xlsx"'},
    )


@router.get("/informe/export/pdf")
async def informe_export_pdf(
    desde: date | None = Query(None),
    hasta: date | None = Query(None),
    template: str | None = Query(None),
    costo: float = Query(informe_service.COSTO_POR_CENEFA, ge=0),
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """El informe como PDF, pensado para mandarse como reporte semanal: lo
    real adelante y el respaldo detras. El Excel queda para auditar corrida
    por corrida; esto es lo que se presenta."""
    resumen = await informe_service.resumen(db, desde, hasta, template, costo)
    pdf = informe_service.a_pdf(resumen)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="informe_semanal_cenefas.pdf"'},
    )


@router.get("/jobs")
async def list_jobs(
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista los últimos 20 jobs."""
    result = await db.execute(
        select(CenefaJob)
        .order_by(CenefaJob.created_at.desc())
        .limit(20)
    )
    jobs = result.scalars().all()
    # include_preview=False, por lo mismo que el listado de un lote (ver el
    # docstring de _job_to_dict): con el preview puesto, esta lista lee de
    # Postgres el PPTX de origen de CADA job en estado "preview" -- 1,7 MB y
    # ~15s medidos con 13 previews -- y la pantalla de jobs la pollea cada 3s
    # mientras hay una corrida activa, compitiendo con los workers que están
    # generando. Además mandaba template_def y preview_products (descripción,
    # SKU y precios del Excel) de jobs ajenos a cualquiera con cenefas.view,
    # justo lo que _get_job se ocupa de impedir en el detalle. La lista solo
    # dibuja id/status/format/row_count/error_count/created_at.
    return [await _job_to_dict(j, include_preview=False) for j in jobs]


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Consulta el estado de un job (polling)."""
    job = await _get_job(job_id, current_user, db)
    return await _job_to_dict(job, include_report=True)


@router.get("/jobs/{job_id}/download")
async def download_job_result(
    job_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Descarga el archivo generado una vez que el job está en estado 'done'."""
    job = await _get_job(job_id, current_user, db)

    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"El job aún no está listo (estado: {job.status})",
        )
    if not job.result_path:
        raise HTTPException(status_code=404, detail="Resultado no disponible")

    result_bytes = await get_job_result(job.id)
    if not result_bytes:
        # No debería pasar en un job nuevo (result_bytes queda persistido en
        # Postgres, no se borra al descargar -- "Descargar de nuevo" pega acá
        # mismo). Solo puede darse en un job "done" de ANTES de este cambio,
        # cuyo resultado vivía en memoria y se perdió en algún redeploy.
        raise HTTPException(
            status_code=410,
            detail="El resultado ya no está disponible — confirmá la generación de nuevo",
        )

    # Se loguea solo la descarga que efectivamente se sirve, no los intentos
    # que cortan arriba en 409/404/410 -- get_db() commitea esto solo, no hay
    # commit explícito en esta ruta (a diferencia de create_job).
    db.add(AuditLog(
        user_id=current_user.id, action="cenefas.job.download", resource="cenefa_job", resource_id=str(job_id),
        ip_address=_client_ip(request),
    ))

    media_type = (
        "application/pdf"
        if job.export_type == "pdf"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    ext = job.export_type or "pptx"
    # Cuando el job viene de un lote se conocen los nombres reales: conviene
    # bajar "Mega Rompe Precios-3xA4 - Carniceria.pptx" y no un UUID que no le
    # dice nada a nadie. Mismo criterio que los archivos dentro del ZIP.
    if job.template_nombre or job.excel_nombre:
        excel = _nombre_archivo(pathlib.PurePath(job.excel_nombre or "").stem)
        plantilla = _nombre_archivo(job.template_nombre or "cenefa")
        nombre = f"{plantilla} - {excel}.{ext}" if excel else f"{plantilla}.{ext}"
    else:
        nombre = f"cenefas_{job_id}.{ext}"
    return Response(
        content=result_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


# ---------------------------------------------------------------------------
# Helpers de jobs
# ---------------------------------------------------------------------------

async def _get_job(
    job_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> CenefaJob:
    """Los jobs solo son visibles para quien los creó o para un superusuario —
    mismo criterio que _get_owned_template. Los Excel subidos a un job pueden
    traer precios/datos de negocio de la sucursal que los generó, así que no
    deberían quedar accesibles por UUID para cualquier otro usuario con
    cenefas.view."""
    result = await db.execute(
        select(CenefaJob).where(CenefaJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if job.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="No tenés permiso para acceder a este job")
    return job


def _nombre_archivo(texto: str) -> str:
    """Deja un texto usable como nombre de archivo o carpeta dentro del ZIP.

    Saca separadores de ruta y caracteres de control: un nombre de plantilla es
    texto libre cargado por el usuario y termina siendo una entrada del ZIP, así
    que una barra ahí crearía carpetas fantasma al descomprimir.
    """
    limpio = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', "", texto or "").strip()
    limpio = re.sub(r"\s+", " ", limpio)
    return limpio[:120] or "sin nombre"


async def _job_to_dict(
    job: CenefaJob, include_report: bool = False, include_preview: bool = True
) -> dict:
    """Serializa un job.

    include_preview=False saltea el preview (definición de componentes +
    productos). Es lo que usa el listado de un lote: cargarlo por cada job
    significa leer de Postgres el PPTX de origen de cada uno --varios MB en
    total-- en CADA polling, compitiendo con los mismos workers que están
    generando las cenefas. El preview se pide aparte, solo para la que se
    está mirando.
    """
    d = {
        "id":          str(job.id),
        "status":      job.status,
        "format":      job.format,
        "export_type": job.export_type,
        # Solo presente cuando el job se generó desde una plantilla del
        # equipo (no builtin_slug ni template_upload) -- PreviewStep lo usa
        # para saber si tiene sentido ofrecer "guardar estos cambios en la
        # plantilla" al confirmar (ver PreviewStep.tsx).
        "template_id": str(job.template_id) if job.template_id else None,
        "row_count":   job.row_count,
        "error_count": job.error_count,
        # Una persona confirmó que esta corrida salió bien. Además de sumar
        # aparte en el informe, decide la retención: el archivo de una corrida
        # verificada se conserva; el de una sin verificar se borra a los
        # CENEFAS_RETENCION_DIAS días (ver purga en jobs.py).
        "verificado":  job.verificado,
        "created_at":  job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    if include_report and job.validation_report:
        summary = job.validation_report.get("summary")
        d["validation_summary"] = summary
        # Variables del template que no se encontraron en el Excel
        missing = job.validation_report.get("missing_vars", [])
        if missing:
            d["missing_vars"] = missing
        # Exponer lista completa de errores y warnings para mostrar en el historial
        errors = job.validation_report.get("errors", [])
        if errors:
            d["errors"] = errors
        warnings = job.validation_report.get("warnings", [])
        if warnings:
            d["warnings"] = warnings
        # Expose error message so the frontend can display it instead of "Error desconocido"
        # La revisión previa del archivo: qué va a salir mal antes de confirmar.
        d["revision"] = (job.validation_report or {}).get("revision", [])
        if job.status == "error":
            d["validation_report"] = {"error": job.validation_report.get("error", "Error interno")}
    if include_preview and job.status == "preview":
        staged = await peek_job_products(job.id)
        if staged:
            componentes = staged.template_def.get("components", [])
            # Plantillas multi-banda (ej. 3xA4): exponer a qué componentes les
            # toca cada producto, para que el preview muestre 3 productos
            # distintos en vez de repetir el mismo en las 3 bandas (ver
            # Canvas.tsx). Mismo algoritmo que usa el render final -- no se
            # duplica la lógica de conteo/orden-por-Y en el frontend.
            slot_bands = _detect_slot_bands(componentes)

            # El achique de texto se aplica ACÁ TAMBIÉN, con los mismos datos
            # que va a usar el render: si no, el preview muestra el cuerpo
            # original del diseño y el archivo final sale con otro. Se aprobaba
            # en pantalla algo distinto de lo que se imprimía.
            if staged.products:
                if slot_bands:
                    ajustados = {}
                    for banda, producto in zip(slot_bands, staged.products):
                        for c in _fit_text_to_box(banda, producto):
                            ajustados[c["id"]] = c
                    componentes = [ajustados.get(c["id"], c) for c in componentes]
                else:
                    componentes = _fit_text_to_box(componentes, staged.products[0])

            d["template_def"]     = {**staged.template_def, "components": componentes}
            d["preview_product"]  = staged.products[0] if staged.products else {}
            if slot_bands:
                d["slot_bands"]       = [[c["id"] for c in band] for band in slot_bands]
                d["preview_products"] = staged.products[: len(slot_bands)]
    return d


# ---------------------------------------------------------------------------
# Destinos ("mundos")
# ---------------------------------------------------------------------------
#
# Un destino agrupa las plantillas de una campaña. No cambia cómo se procesa
# nada: las variables, el Excel y el motor de render son idénticos para
# todos. Son datos y no código para que sumar un mundo nuevo ("Mega Rompe
# Precios") no requiera tocar el repo ni desplegar.

# Íconos y colores que el frontend sabe dibujar. Se validan acá para que un
# valor inventado no llegue nunca a la UI: el frontend cae a un default, pero
# es mejor rechazarlo en el borde que mostrar un mundo sin identidad visual.
_ICONOS_VALIDOS = {
    "Store", "PartyPopper", "Wine", "ShoppingCart", "Tag", "Percent",
    "Sparkles", "Flame", "Gift", "Beef", "Apple", "Snowflake",
}
_COLORES_VALIDOS = {
    "emerald", "rose", "purple", "amber", "sky", "indigo", "orange", "teal",
}

_RE_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


def _slugify(nombre: str) -> str:
    """Nombre visible -> slug estable.

    "Mega Rompe Precios" -> "mega_rompe_precios". Se normaliza sin acentos
    porque el slug termina en una URL y en una columna de texto que ya
    contiene los slugs viejos, todos ASCII.
    """
    base = unicodedata.normalize("NFD", nombre).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()
    return base[:49]


@router.get("/destinos")
async def list_destinos(
    _: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CenefaDestino).order_by(CenefaDestino.orden, CenefaDestino.nombre)
    )
    return [
        {
            "slug":        d.slug,
            "nombre":      d.nombre,
            "descripcion": d.descripcion,
            "icono":       d.icono,
            "color":       d.color,
            # Si el trabajo de este mundo se valoriza en el informe de
            # produccion. Redexpres y el mundo de pruebas van en false.
            "cobrable":    d.cobrable,
            "cenefas_previas": d.cenefas_previas,
        }
        for d in result.scalars().all()
    ]


@router.post("/destinos", status_code=status.HTTP_201_CREATED)
async def create_destino(
    payload: dict,
    request: Request,
    current_user: User = Depends(require_permission("cenefas.edit")),
    db: AsyncSession = Depends(get_db),
):
    nombre = str(payload.get("nombre", "")).strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="El nombre del mundo no puede estar vacío")
    if len(nombre) > 120:
        raise HTTPException(status_code=422, detail="El nombre no puede superar los 120 caracteres")

    slug = _slugify(nombre)
    if not _RE_SLUG.match(slug):
        raise HTTPException(
            status_code=422,
            detail="El nombre tiene que tener al menos dos caracteres alfanuméricos",
        )

    existente = await db.get(CenefaDestino, slug)
    if existente is not None:
        raise HTTPException(status_code=409, detail=f"Ya existe un mundo llamado {existente.nombre!r}")

    icono = str(payload.get("icono") or "Store")
    color = str(payload.get("color") or "emerald")
    if icono not in _ICONOS_VALIDOS:
        icono = "Store"
    if color not in _COLORES_VALIDOS:
        color = "emerald"

    # El nuevo va al final: los mundos existentes ya tienen un orden con el
    # que el equipo está acostumbrado a verlos.
    max_orden = (await db.execute(select(func.max(CenefaDestino.orden)))).scalar() or 0

    destino = CenefaDestino(
        slug=slug,
        nombre=nombre,
        descripcion=str(payload.get("descripcion", "")).strip()[:300],
        icono=icono,
        color=color,
        orden=max_orden + 10,
        # Un mundo nace cobrable salvo que se diga lo contrario: es lo normal.
        # Se marca en false para Redexpres y para el mundo de pruebas, que
        # pasan por el motor pero no son trabajo facturable.
        cobrable=bool(payload.get("cobrable", True)),
        created_by=current_user.id,
    )
    db.add(destino)
    db.add(AuditLog(
        user_id=current_user.id, action="cenefas.destino.create", resource="cenefa_destino",
        resource_id=slug, details={"nombre": nombre}, ip_address=_client_ip(request),
    ))
    await db.commit()
    return {
        "slug": slug, "nombre": nombre, "descripcion": destino.descripcion,
        "icono": icono, "color": color, "cobrable": destino.cobrable,
        "cenefas_previas": destino.cenefas_previas,
    }


@router.delete("/destinos/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_destino(
    slug: str,
    request: Request,
    current_user: User = Depends(require_permission("cenefas.edit")),
    db: AsyncSession = Depends(get_db),
):
    destino = await db.get(CenefaDestino, slug)
    if destino is None:
        raise HTTPException(status_code=404, detail="Mundo no encontrado")

    # Un mundo con plantillas no se borra: las plantillas quedarían
    # inalcanzables (el picker filtra por category) sin ningún aviso, y
    # recuperarlas exigiría entrar a la base. Que las borren primero.
    en_uso = (await db.execute(
        select(func.count()).select_from(CenefaTemplateV2).where(CenefaTemplateV2.category == slug)
    )).scalar_one()
    if en_uso:
        raise HTTPException(
            status_code=409,
            detail=f"El mundo tiene {en_uso} plantilla(s). Borralas antes de eliminarlo.",
        )

    await db.delete(destino)
    db.add(AuditLog(
        user_id=current_user.id, action="cenefas.destino.delete", resource="cenefa_destino",
        resource_id=slug, details={"nombre": destino.nombre}, ip_address=_client_ip(request),
    ))
    await db.commit()


# ---------------------------------------------------------------------------
# Lotes: varios Excel, cada uno contra varias plantillas
# ---------------------------------------------------------------------------
#
# Un lote NO es un motor nuevo: cada combinación (Excel × plantilla) se resuelve
# con el mismo job de siempre, con su preview y su confirmación. El lote es la
# etiqueta que los agrupa para poder mirarlos juntos y bajarlos en un ZIP.

# Tope por Excel, a pedido explícito. Evita además que un descuido
# (seleccionar todas las plantillas del mundo) dispare decenas de renders.
MAX_PLANTILLAS_POR_EXCEL = 5
MAX_EXCELS_POR_LOTE = 20


@router.post("/lotes", status_code=status.HTTP_202_ACCEPTED)
async def create_lote(
    background_tasks: BackgroundTasks,
    request: Request,
    excels: list[UploadFile] = File(..., description="Uno o varios Excel"),
    pares_json: str = Form(
        ...,
        description='JSON [{"excel": "nombre.xlsx", "templates": ["uuid", ...]}] — '
                    "a qué plantillas va cada Excel",
    ),
    vigencia: str = Form(default=""),
    legales: str = Form(default=""),
    usar_legales: bool = Form(default=False),
    image_overrides_json: str = Form(default="{}"),
    current_user: User = Depends(require_permission("cenefas.generate")),
    db: AsyncSession = Depends(get_db),
):
    """Crea un lote: una cenefa por cada par (Excel, plantilla) declarado."""
    try:
        pares = json.loads(pares_json or "[]")
        if not isinstance(pares, list):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="pares_json no es un JSON válido")

    if not pares:
        raise HTTPException(status_code=400, detail="No hay ningún Excel emparejado con una plantilla")
    if len(excels) > MAX_EXCELS_POR_LOTE:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo {MAX_EXCELS_POR_LOTE} Excel por lote (llegaron {len(excels)})",
        )

    # Los dos topes de arriba cuentan archivos subidos y plantillas por par,
    # pero `pares` no tenía ninguno y NADA impide repetir el mismo nombre de
    # Excel: con un solo archivo subido y mil pares apuntándole, se encolaban
    # miles de corridas de una. Cada una es una fila en cenefa_jobs y trabajo
    # para los workers, y ademas ensucia el informe. El techo es el que los dos
    # topes ya daban a entender.
    MAX_JOBS_POR_LOTE = MAX_EXCELS_POR_LOTE * MAX_PLANTILLAS_POR_EXCEL
    total_pedido = sum(len(p.get("templates") or []) for p in pares if isinstance(p, dict))
    if total_pedido > MAX_JOBS_POR_LOTE:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo {MAX_JOBS_POR_LOTE} cenefas por lote (pediste {total_pedido})",
        )

    # Los archivos se leen UNA vez y se reusan para cada plantilla de ese Excel:
    # un UploadFile no se puede releer, y además evita subir el mismo contenido
    # a memoria tantas veces como plantillas tenga.
    contenidos: dict[str, bytes] = {}
    for archivo in excels:
        if not archivo.filename or not archivo.filename.lower().endswith((".xlsx", ".xlsm")):
            raise HTTPException(status_code=400, detail=f"{archivo.filename!r} no es un .xlsx/.xlsm")
        contenidos[archivo.filename] = await read_limited(archivo, "Excel")

    image_overrides = _parse_image_overrides(image_overrides_json)

    lote_id = uuid.uuid4()
    creados: list[dict] = []

    for par in pares:
        nombre_excel = str(par.get("excel", ""))
        ids = par.get("templates") or []
        if nombre_excel not in contenidos:
            raise HTTPException(status_code=400, detail=f"No subiste el Excel {nombre_excel!r}")
        if not ids:
            continue
        if len(ids) > MAX_PLANTILLAS_POR_EXCEL:
            raise HTTPException(
                status_code=400,
                detail=f"{nombre_excel!r}: máximo {MAX_PLANTILLAS_POR_EXCEL} plantillas por Excel",
            )

        for template_id in ids:
            try:
                tid = uuid.UUID(str(template_id))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Plantilla inválida: {template_id!r}")

            tmpl = (await db.execute(
                select(CenefaTemplateV2).where(CenefaTemplateV2.id == tid)
            )).scalar_one_or_none()
            if tmpl is None:
                raise HTTPException(status_code=404, detail=f"Plantilla {tid} no encontrada")

            job = CenefaJob(
                created_by=current_user.id,
                status="pending",
                format="",
                export_type="pptx",
                lote_id=lote_id,
                excel_nombre=nombre_excel,
                template_nombre=tmpl.name,
                template_id=tid,
                # Copiado, no referenciado: el FK a la plantilla es ON DELETE
                # SET NULL y borrar una plantilla dejaba la corrida sin mundo.
                categoria=tmpl.category,
            )
            db.add(job)
            await db.flush()
            creados.append({
                "job_id": str(job.id),
                "excel": nombre_excel,
                "template_id": str(tid),
                "template": tmpl.name,
                "_bytes": contenidos[nombre_excel],
            })

    if not creados:
        raise HTTPException(status_code=400, detail="Ningún Excel quedó emparejado con una plantilla")

    db.add(AuditLog(
        user_id=current_user.id, action="cenefas.lote.create", resource="cenefa_lote",
        resource_id=str(lote_id),
        details={"cenefas": len(creados), "excels": len(contenidos)},
        ip_address=_client_ip(request),
    ))
    # Mismo motivo que en create_job: BackgroundTasks puede arrancar antes del
    # commit automático de get_db y no encontrar las filas.
    await db.commit()

    for c in creados:
        background_tasks.add_task(
            run_generation_job,
            job_id=uuid.UUID(c["job_id"]),
            excel_bytes=c.pop("_bytes"),
            builtin_slug=None,
            template_v2_id=uuid.UUID(c["template_id"]),
            template_upload_bytes=None,
            target_format=None,
            vigencia=vigencia,
            legales=legales,
            usar_legales=usar_legales,
            image_overrides=image_overrides,
        )

    return {"lote_id": str(lote_id), "cenefas": creados}


@router.get("/lotes/{lote_id}")
async def get_lote(
    lote_id: uuid.UUID,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """Estado y preview de cada cenefa del lote, en el orden en que se pidieron."""
    result = await db.execute(
        select(CenefaJob)
        .where(CenefaJob.lote_id == lote_id, CenefaJob.created_by == current_user.id)
        .order_by(CenefaJob.created_at, CenefaJob.excel_nombre, CenefaJob.template_nombre)
    )
    jobs = result.scalars().all()
    if not jobs:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    cenefas = []
    for job in jobs:
        d = await _job_to_dict(job, include_report=True, include_preview=False)
        d["excel"] = job.excel_nombre
        d["template"] = job.template_nombre
        cenefas.append(d)

    estados = {c["status"] for c in cenefas}
    if "error" in estados:
        estado = "error" if estados == {"error"} else "parcial"
    elif estados <= {"done"}:
        estado = "done"
    elif estados <= {"preview", "done"}:
        estado = "preview"
    else:
        estado = "running"

    return {"lote_id": str(lote_id), "status": estado, "total": len(cenefas), "cenefas": cenefas}


@router.post("/lotes/{lote_id}/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm_lote(
    lote_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission("cenefas.generate")),
    db: AsyncSession = Depends(get_db),
):
    """Confirma de una todas las cenefas del lote que estén en preview."""
    result = await db.execute(
        select(CenefaJob).where(
            CenefaJob.lote_id == lote_id,
            CenefaJob.created_by == current_user.id,
            CenefaJob.status == "preview",
        )
    )
    jobs = result.scalars().all()
    if not jobs:
        # No es un error: pasa si se toca el boton dos veces, o si el lote ya
        # se confirmo desde otra pestana. Se responde que no habia nada nuevo
        # que disparar en vez de un 409 que el frontend tendria que
        # distinguir de un problema real.
        existe = (await db.execute(
            select(func.count()).select_from(CenefaJob).where(
                CenefaJob.lote_id == lote_id, CenefaJob.created_by == current_user.id)
        )).scalar_one()
        if not existe:
            raise HTTPException(status_code=404, detail="Lote no encontrado")
        return {"lote_id": str(lote_id), "confirmadas": 0}

    ids = [j.id for j in jobs]
    for job in jobs:
        job.status = "running"
    await db.commit()

    for job_id in ids:
        background_tasks.add_task(confirm_generation_job, job_id=job_id, position_overrides=None)

    return {"lote_id": str(lote_id), "confirmadas": len(ids)}


@router.get("/lotes/{lote_id}/download")
async def download_lote(
    lote_id: uuid.UUID,
    current_user: User = Depends(require_permission("cenefas.view")),
    db: AsyncSession = Depends(get_db),
):
    """ZIP del lote, con una subcarpeta por Excel."""
    result = await db.execute(
        select(CenefaJob)
        .where(CenefaJob.lote_id == lote_id, CenefaJob.created_by == current_user.id)
        .order_by(CenefaJob.excel_nombre, CenefaJob.template_nombre)
    )
    jobs = [j for j in result.scalars().all() if j.status == "done"]
    if not jobs:
        raise HTTPException(status_code=404, detail="El lote todavía no tiene ninguna cenefa lista")

    buffer = io.BytesIO()
    escritas = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        usados: set[str] = set()
        for job in jobs:
            contenido = await get_job_result(job.id)
            if contenido is None:
                continue
            excel = _nombre_archivo(pathlib.PurePath(job.excel_nombre or "excel").stem)
            plantilla = _nombre_archivo(job.template_nombre or "plantilla")
            ruta = f"{excel}/{plantilla} - {excel}.pptx"
            # Dos plantillas del mismo nombre en el mismo Excel se pisarian
            # dentro del ZIP sin que nadie se entere.
            n = 2
            while ruta in usados:
                ruta = f"{excel}/{plantilla} ({n}) - {excel}.pptx"
                n += 1
            usados.add(ruta)
            zf.writestr(ruta, contenido)
            escritas += 1

    # Contar entradas, no bytes: un ZIP vacio igual pesa 22 (el End Of Central
    # Directory), asi que `if not buffer.tell()` era siempre falso y en vez del
    # 404 se servia un .zip valido y VACIO con HTTP 200. Pasa de verdad cuando
    # las corridas del lote ya pasaron la retencion sin verificarse: la purga
    # les deja result_bytes en NULL pero el status en "done", get_job_result
    # devuelve None para todas y el `continue` de arriba las saltea a todas.
    if not escritas:
        raise HTTPException(
            status_code=410,
            detail="Las cenefas de este lote ya no estan disponibles — volve a generarlas",
        )
    if escritas < len(jobs):
        # Antes salia incompleto en silencio; que al menos quede en el log.
        logger.warning(
            "download_lote %s: %d de %d cenefas recuperadas, el ZIP va incompleto",
            lote_id, escritas, len(jobs),
        )

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="cenefas_{lote_id.hex[:8]}.zip"'},
    )
