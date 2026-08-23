"""Rutas /tools/cenefas/v2/ — API del nuevo motor de componentes."""
import base64 as _b64
import json
import logging
import pathlib
import re
import unicodedata
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
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
from app.services.cenefas.component_renderer import _detect_slot_bands
from app.services.cenefas.jobs import (
    confirm_generation_job,
    get_job_result,
    peek_job_products,
    run_generation_job,
)
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

    # Parse image overrides: {var_name: "ext:base64"} → {var_name: (bytes, ext)}
    image_overrides: dict | None = None
    try:
        raw = json.loads(image_overrides_json or "{}")
        parsed: dict[str, tuple[bytes, str]] = {}
        for var_name, encoded in raw.items():
            if ":" in encoded:
                ext, b64_data = encoded.split(":", 1)
                parsed[var_name] = (_b64.b64decode(b64_data), ext.lower())
        if parsed:
            image_overrides = parsed
    except Exception:
        pass

    job = CenefaJob(
        created_by=current_user.id,
        status="pending",
        format=format_id or "",  # se resuelve en run_generation_job si viene vacío
        export_type=export_type,
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
    return [await _job_to_dict(j) for j in jobs]


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
    return Response(
        content=result_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="cenefas_{job_id}.{ext}"'},
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


async def _job_to_dict(job: CenefaJob, include_report: bool = False) -> dict:
    d = {
        "id":          str(job.id),
        "status":      job.status,
        "format":      job.format,
        "export_type": job.export_type,
        "row_count":   job.row_count,
        "error_count": job.error_count,
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
        if job.status == "error":
            d["validation_report"] = {"error": job.validation_report.get("error", "Error interno")}
    if job.status == "preview":
        staged = await peek_job_products(job.id)
        if staged:
            d["template_def"]     = staged.template_def
            d["preview_product"]  = staged.products[0] if staged.products else {}
            # Plantillas multi-banda (ej. 3xA4): exponer a qué componentes les
            # toca cada producto, para que el preview muestre 3 productos
            # distintos en vez de repetir el mismo en las 3 bandas (ver
            # Canvas.tsx). Mismo algoritmo que usa el render final -- no se
            # duplica la lógica de conteo/orden-por-Y en el frontend.
            slot_bands = _detect_slot_bands(staged.template_def.get("components", []))
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
        "icono": icono, "color": color,
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
