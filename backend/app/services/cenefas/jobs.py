"""Background task de generación — orquesta pipeline completo para un job."""
import asyncio
import logging
import pathlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.cenefa_job import CenefaJob
from app.models.cenefa_template import CenefaTemplate
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.services.cenefas.component_renderer import patch_image_overrides, render_template_to_pptx
from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.pptx_importer import import_pptx
from app.services.cenefas.validation_engine import build_summary, validate_products

logger = logging.getLogger(__name__)

_STATIC_DIR = pathlib.Path(__file__).parent.parent.parent / "static" / "cenefa_templates"

_BUILTIN_FILES = {
    "a4":      "Base cenefa A4 1.pptx",
    "pinchos": "Base pinchos 1.pptx",
    "black":   "Bases cenefas BLACK 1.pptx",
}

REDIS_INPUT_TTL  = 3_600
REDIS_RESULT_TTL = 86_400

# Cache en memoria — reemplaza Redis para input/output de jobs.
# Funciona en deployments single-process (Render free tier).
# Los bytes se eliminan al descargar o al reiniciar el servidor.
_job_results: dict[str, bytes] = {}

# Etapa intermedia entre "parseado" y "renderizado final": guarda la
# definición de componentes + productos reales mientras el usuario ve el
# preview y reposiciona. Se consume (pop) al confirmar. Mismo ciclo de vida
# en memoria que _job_results — se pierde si el server reinicia antes de
# confirmar, igual que ya pasaba con el resultado final.
_job_products: dict[str, tuple[dict, list, str]] = {}


def store_job_result(job_id: uuid.UUID, pptx_bytes: bytes) -> None:
    _job_results[str(job_id)] = pptx_bytes


def pop_job_result(job_id: uuid.UUID) -> bytes | None:
    return _job_results.pop(str(job_id), None)


def store_job_products(job_id: uuid.UUID, template_def: dict, products: list, target_format: str) -> None:
    _job_products[str(job_id)] = (template_def, products, target_format)


def peek_job_products(job_id: uuid.UUID) -> tuple[dict, list, str] | None:
    return _job_products.get(str(job_id))


def pop_job_products(job_id: uuid.UUID) -> tuple[dict, list, str] | None:
    return _job_products.pop(str(job_id), None)


async def run_generation_job(
    job_id:          uuid.UUID,
    excel_bytes:     bytes,
    builtin_slug:    str | None,
    template_v1_id:  int | None,
    template_v2_id:  uuid.UUID | None,
    target_format:   str | None,
    vigencia:        str,
    aclaracion:      str,
    otra_alcohol:    str,
    banco:           str,
    image_overrides:       dict | None = None,
    template_upload_bytes: bytes | None = None,
) -> None:
    """Etapa A: parsea Excel, valida, resuelve la definición de componentes
    (importando el PPTX crudo si es builtin/v1) y hornea las imágenes
    subidas (ej. cocarda). Deja el job en status="preview" con los datos
    reales listos para que el frontend los muestre en el Canvas y el
    usuario pueda reposicionar antes de generar el PPTX final — ver
    confirm_generation_job() para la etapa B."""
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            logger.error("run_generation_job: job %s not found", job_id)
            return
        job.status = "running"
        await db.commit()

        try:
            products = await asyncio.to_thread(
                load_products_from_bytes, excel_bytes, vigencia, aclaracion, otra_alcohol, banco
            )
            validation = validate_products(products)
            summary    = build_summary(validation)

            if template_upload_bytes is not None:
                template_def = await asyncio.to_thread(
                    import_pptx, template_upload_bytes, "Plantilla subida"
                )
            else:
                template_def = await _resolve_template_def(db, builtin_slug, template_v1_id, template_v2_id)
            if image_overrides:
                template_def = {
                    **template_def,
                    "components": patch_image_overrides(template_def.get("components", []), image_overrides),
                }

            # Sin formato explícito: usar el master_format que ya detectó el
            # importer/la plantilla — es lo único que es correcto tanto para
            # diseños de hoja completa (a4) como de celda única (pinchos/3xa4).
            resolved_format = target_format or template_def.get("master_format", "a4")

            store_job_products(job_id, template_def, products, resolved_format)

            job.status            = "preview"
            job.format            = resolved_format
            job.row_count         = len(products)
            job.error_count       = len(validation["errors"])
            job.validation_report = {
                "summary":      summary,
                "errors":       validation["errors"],
                "warnings":     validation["warnings"],
                "missing_vars": [],
            }
            await db.commit()

            logger.info(
                "job %s en preview: %d products, %d errors", job_id, len(products), len(validation["errors"])
            )

        except Exception as exc:
            logger.error("job %s failed: %s", job_id, exc, exc_info=True)
            job.status            = "error"
            job.validation_report = {"error": str(exc)}
            job.completed_at      = datetime.now(timezone.utc)
            await db.commit()


async def confirm_generation_job(
    job_id: uuid.UUID,
    position_overrides: list[dict] | None = None,
) -> None:
    """Etapa B: toma lo que quedó guardado por run_generation_job(), aplica
    los deltas de posición que el usuario movió en el preview (por id de
    componente) y genera el PPTX final."""
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            logger.error("confirm_generation_job: job %s not found", job_id)
            return

        staged = pop_job_products(job_id)
        if staged is None:
            job.status            = "error"
            job.validation_report = {"error": "No hay preview pendiente para este job (¿ya se confirmó o expiró?)"}
            job.completed_at      = datetime.now(timezone.utc)
            await db.commit()
            return

        template_def, products, target_format = staged

        try:
            if position_overrides:
                bounds_by_id = {o["id"]: o["base_bounds"] for o in position_overrides if o.get("id")}
                template_def = {
                    **template_def,
                    "components": [
                        {**c, "base_bounds": bounds_by_id.get(c["id"], c["base_bounds"])}
                        for c in template_def.get("components", [])
                    ],
                }

            pptx_bytes, missing_vars = await asyncio.to_thread(
                render_template_to_pptx, template_def, products, target_format,
            )
            store_job_result(job_id, pptx_bytes)

            report = dict(job.validation_report or {})
            report["missing_vars"] = missing_vars

            job.status            = "done"
            job.result_path       = str(job_id)
            job.validation_report = report
            job.completed_at      = datetime.now(timezone.utc)
            await db.commit()

            logger.info("job %s confirmado y renderizado", job_id)

        except Exception as exc:
            logger.error("job %s confirm failed: %s", job_id, exc, exc_info=True)
            job.status            = "error"
            job.validation_report = {"error": str(exc)}
            job.completed_at      = datetime.now(timezone.utc)
            await db.commit()


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

async def _get_job(db, job_id: uuid.UUID) -> CenefaJob | None:
    result = await db.execute(select(CenefaJob).where(CenefaJob.id == job_id))
    return result.scalar_one_or_none()


async def _resolve_template_v2(db, template_id: uuid.UUID) -> dict:
    result = await db.execute(
        select(CenefaTemplateV2).where(CenefaTemplateV2.id == template_id)
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        raise ValueError(f"Template v2 {template_id} no encontrado")
    return tmpl.definition


async def _resolve_template_def(
    db,
    builtin_slug:   str | None,
    template_v1_id: int | None,
    template_v2_id: uuid.UUID | None,
) -> dict:
    """Unifica los 3 orígenes posibles de plantilla en una definición de
    componentes v2 — para builtin/v1 (pptx crudo, sin datos de posición)
    corre el importer, así RedExpress también puede reposicionar en el
    preview aunque su plantilla nunca haya pasado por el editor v2."""
    if template_v2_id is not None:
        return await _resolve_template_v2(db, template_v2_id)

    pptx_bytes = await _resolve_template_pptx(db, builtin_slug, template_v1_id)
    return await asyncio.to_thread(import_pptx, pptx_bytes, "Plantilla importada")


async def _resolve_template_pptx(
    db,
    builtin_slug:   str | None,
    template_v1_id: int | None,
) -> bytes:
    if builtin_slug is not None:
        filename = _BUILTIN_FILES.get(builtin_slug)
        if not filename:
            raise ValueError(f"Plantilla predeterminada desconocida: {builtin_slug!r}")
        path = _STATIC_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {path}")
        return path.read_bytes()

    if template_v1_id is not None:
        result = await db.execute(
            select(CenefaTemplate).where(
                CenefaTemplate.id == template_v1_id,
                CenefaTemplate.is_active == True,
            )
        )
        tmpl = result.scalar_one_or_none()
        if tmpl is None:
            raise ValueError(f"Template v1 #{template_v1_id} no encontrado")
        return tmpl.file_bytes

    raise ValueError("Debés especificar builtin_slug o template_v1_id")
