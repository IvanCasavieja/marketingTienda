"""Rutas /tools/cenefas/v2/ — API del nuevo motor de componentes."""
import logging
import pathlib
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.cenefa_job import CenefaJob
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.models.user import User
from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.jobs import run_generation_job, pop_job_result
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
    _: User = Depends(get_current_user),
):
    """Parsea un PPTX y devuelve una definición v2 lista para cargar en el editor."""
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="El archivo debe ser .pptx")

    pptx_bytes = await file.read()

    from app.services.cenefas.pptx_importer import import_pptx as _import
    try:
        definition = _import(pptx_bytes, name=name.strip() or "Template importado")
    except Exception as exc:
        logger.warning("import_pptx error: %s", exc)
        raise HTTPException(status_code=422, detail=f"No se pudo parsear el PPTX: {exc}")

    return definition


@router.get("/builtin-definitions")
async def get_builtin_definitions(_: User = Depends(get_current_user)):
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
async def list_formats(_: User = Depends(get_current_user)):
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        return []
    result = await db.execute(
        select(CenefaTemplateV2)
        .where(CenefaTemplateV2.team_group_id == current_user.team_group_id)
        .order_by(CenefaTemplateV2.created_at.desc())
    )
    templates = result.scalars().all()
    return [
        {
            "id":         str(t.id),
            "name":       t.name,
            "formats":    t.formats,
            "is_builtin": t.is_builtin,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in templates
    ]


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Unite a un equipo para crear templates")

    _validate_template_payload(payload)

    tmpl = CenefaTemplateV2(
        team_group_id=current_user.team_group_id,
        created_by=current_user.id,
        name=payload["name"].strip(),
        definition=payload,
        formats=payload.get("formats", []),
    )
    db.add(tmpl)
    await db.flush()
    await db.refresh(tmpl)
    return {"id": str(tmpl.id), "name": tmpl.name, "created_at": tmpl.created_at.isoformat()}


@router.get("/templates/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tmpl = await _get_owned_template(template_id, current_user, db)
    return {
        "id":         str(tmpl.id),
        "name":       tmpl.name,
        "formats":    tmpl.formats,
        "is_builtin": tmpl.is_builtin,
        "definition": tmpl.definition,
        "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
        "updated_at": tmpl.updated_at.isoformat() if tmpl.updated_at else None,
    }


@router.put("/templates/{template_id}")
async def update_template(
    template_id: uuid.UUID,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tmpl = await _get_owned_template(template_id, current_user, db)
    if tmpl.is_builtin:
        raise HTTPException(status_code=403, detail="No se pueden modificar templates del sistema")

    _validate_template_payload(payload)

    tmpl.name       = payload["name"].strip()
    tmpl.definition = payload
    tmpl.formats    = payload.get("formats", tmpl.formats)
    return {"id": str(tmpl.id), "name": tmpl.name}


@router.patch("/templates/{template_id}/rename")
async def rename_template(
    template_id: uuid.UUID,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tmpl = await _get_owned_template(template_id, current_user, db)
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tmpl = await _get_owned_template(template_id, current_user, db)
    if tmpl.is_builtin:
        raise HTTPException(status_code=403, detail="No se pueden eliminar templates del sistema")
    await db.delete(tmpl)


# ---------------------------------------------------------------------------
# Validación de CSV contra template
# ---------------------------------------------------------------------------

@router.post("/validate")
async def validate_csv(
    excel: UploadFile = File(..., description="Archivo Excel o CSV"),
    template_id: uuid.UUID = Form(...),
    vigencia: str = Form(default=""),
    aclaracion: str = Form(default=""),
    otra_alcohol: str = Form(default="Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
    banco: str = Form(default=""),
    current_user: User = Depends(get_current_user),
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

    excel_bytes = await excel.read()
    try:
        products = load_products_from_bytes(excel_bytes, vigencia, aclaracion, otra_alcohol, banco)
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
) -> CenefaTemplateV2:
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Unite a un equipo para gestionar templates")
    result = await db.execute(
        select(CenefaTemplateV2).where(
            CenefaTemplateV2.id == template_id,
            CenefaTemplateV2.team_group_id == current_user.team_group_id,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template no encontrado")
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
    excel: UploadFile = File(..., description="Archivo Excel con hoja 'Cenefas'"),
    format_id: str = Form(default="a4", description="Formato destino: a4 | a3 | 3xa4 | pinchos"),
    export_type: str = Form(default="pptx", description="Tipo de salida: pptx"),
    builtin_slug: str | None = Form(None, description="Slug de plantilla predeterminada (v1)"),
    template_v1_id: int | None = Form(None, description="ID de template v1 del equipo"),
    template_v2_id: uuid.UUID | None = Form(None, description="UUID de template v2 del equipo"),
    vigencia: str = Form(default=""),
    aclaracion: str = Form(default=""),
    otra_alcohol: str = Form(default="Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
    banco: str = Form(default=""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Inicia un job de generación async. Acepta templates v1 (PPTX) y v2 (componentes JSON)."""
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Unite a un equipo para generar cenefas")
    if format_id not in FORMATS:
        raise HTTPException(status_code=400, detail=f"Formato inválido. Disponibles: {list(FORMATS)}")
    if not builtin_slug and not template_v1_id and not template_v2_id:
        raise HTTPException(
            status_code=400,
            detail="Debés especificar builtin_slug, template_v1_id o template_v2_id",
        )
    if not excel.filename or not excel.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="El Excel debe ser .xlsx o .xlsm")

    excel_bytes = await excel.read()

    job = CenefaJob(
        team_group_id=current_user.team_group_id,
        created_by=current_user.id,
        status="pending",
        format=format_id,
        export_type=export_type,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    job_id = job.id

    background_tasks.add_task(
        run_generation_job,
        job_id=job_id,
        excel_bytes=excel_bytes,
        builtin_slug=builtin_slug,
        template_v1_id=template_v1_id,
        template_v2_id=template_v2_id,
        team_group_id=current_user.team_group_id,
        target_format=format_id,
        vigencia=vigencia,
        aclaracion=aclaracion,
        otra_alcohol=otra_alcohol,
        banco=banco,
    )

    return {"job_id": str(job_id), "status": "pending", "format": format_id}


@router.get("/jobs")
async def list_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista los últimos 20 jobs del equipo."""
    if not current_user.team_group_id:
        return []
    result = await db.execute(
        select(CenefaJob)
        .where(CenefaJob.team_group_id == current_user.team_group_id)
        .order_by(CenefaJob.created_at.desc())
        .limit(20)
    )
    jobs = result.scalars().all()
    return [_job_to_dict(j) for j in jobs]


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consulta el estado de un job (polling)."""
    job = await _get_owned_job(job_id, current_user, db)
    return _job_to_dict(job, include_report=True)


@router.get("/jobs/{job_id}/download")
async def download_job_result(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Descarga el archivo generado una vez que el job está en estado 'done'."""
    job = await _get_owned_job(job_id, current_user, db)

    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"El job aún no está listo (estado: {job.status})",
        )
    if not job.result_path:
        raise HTTPException(status_code=404, detail="Resultado no disponible")

    result_bytes = pop_job_result(job.id)
    if not result_bytes:
        raise HTTPException(
            status_code=410,
            detail="El resultado ya fue descargado o el servidor se reinició — generá de nuevo",
        )

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

async def _get_owned_job(
    job_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> CenefaJob:
    if not current_user.team_group_id:
        raise HTTPException(status_code=400, detail="Unite a un equipo para consultar jobs")
    result = await db.execute(
        select(CenefaJob).where(
            CenefaJob.id == job_id,
            CenefaJob.team_group_id == current_user.team_group_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return job


def _job_to_dict(job: CenefaJob, include_report: bool = False) -> dict:
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
        # Expose error message so the frontend can display it instead of "Error desconocido"
        if job.status == "error":
            d["validation_report"] = {"error": job.validation_report.get("error", "Error interno")}
    return d
