"""Background task de generación — orquesta pipeline completo para un job."""
import asyncio
import logging
import pathlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.cenefa_job import CenefaJob
from app.models.cenefa_template import CenefaTemplate
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.services.cenefas.component_renderer import render_template_to_pptx
from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.render_engine import generate_pptx_bytes
from app.services.cenefas.validation_engine import build_summary, validate_products

logger = logging.getLogger(__name__)

_STATIC_DIR = pathlib.Path(__file__).parent.parent.parent / "static" / "cenefa_templates"

_BUILTIN_FILES = {
    "a4":         "Base cenefa A4 1.pptx",
    "pinchos":    "Base pinchos 1.pptx",
    "black":      "Bases cenefas BLACK 1.pptx",
    "plato-dia":  "Plato del dia template.pptx",
}

REDIS_INPUT_TTL  = 3_600   # 1 hora
REDIS_RESULT_TTL = 86_400  # 24 horas


async def run_generation_job(
    job_id:          uuid.UUID,
    builtin_slug:    str | None,
    template_v1_id:  int | None,
    template_v2_id:  uuid.UUID | None,
    team_group_id:   int,
    target_format:   str,
    vigencia:        str,
    aclaracion:      str,
    otra_alcohol:    str,
    banco:           str,
) -> None:
    """Orquesta la generación completa.

    Pipeline v1/builtin:  Excel → generate_pptx_bytes (template PPTX clonado)
    Pipeline v2:          Excel → component_renderer   (JSON components)
    """
    redis = get_redis()

    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            logger.error("run_generation_job: job %s not found", job_id)
            return
        job.status = "running"
        await db.commit()

        try:
            # Leer Excel desde Redis
            excel_bytes = await redis.get(f"cenefa:input:{job_id}")
            if not excel_bytes:
                raise ValueError("Excel expiró o no fue almacenado correctamente")

            # Parsear y validar productos (ambos pipelines necesitan esto)
            products = await asyncio.to_thread(
                load_products_from_bytes, excel_bytes, vigencia, aclaracion, otra_alcohol, banco
            )
            validation = validate_products(products)
            summary    = build_summary(validation)

            # Generar PPTX según el tipo de template
            if template_v2_id is not None:
                template_def = await _resolve_template_v2(db, template_v2_id, team_group_id)
                pptx_bytes = await asyncio.to_thread(
                    render_template_to_pptx,
                    template_def, products, target_format,
                )
            else:
                template_bytes = await _resolve_template_pptx(
                    db, builtin_slug, template_v1_id, team_group_id
                )
                pptx_bytes = await asyncio.to_thread(
                    generate_pptx_bytes,
                    excel_bytes, template_bytes,
                    vigencia, aclaracion, otra_alcohol, banco,
                )

            # Guardar resultado en Redis
            result_key = f"cenefa:result:{job_id}"
            await redis.setex(result_key, REDIS_RESULT_TTL, pptx_bytes)

            job.status            = "done"
            job.row_count         = len(products)
            job.error_count       = len(validation["errors"])
            job.result_path       = result_key
            job.validation_report = {
                "summary":  summary,
                "errors":   validation["errors"],
                "warnings": validation["warnings"],
            }
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "job %s done: %d products, %d errors", job_id, len(products), len(validation["errors"])
            )

        except Exception as exc:
            logger.error("job %s failed: %s", job_id, exc, exc_info=True)
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


async def _resolve_template_v2(db, template_id: uuid.UUID, team_group_id: int) -> dict:
    result = await db.execute(
        select(CenefaTemplateV2).where(
            CenefaTemplateV2.id == template_id,
            CenefaTemplateV2.team_group_id == team_group_id,
        )
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        raise ValueError(f"Template v2 {template_id} no encontrado")
    return tmpl.definition


async def _resolve_template_pptx(
    db,
    builtin_slug:   str | None,
    template_v1_id: int | None,
    team_group_id:  int,
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
                CenefaTemplate.team_group_id == team_group_id,
                CenefaTemplate.is_active == True,
            )
        )
        tmpl = result.scalar_one_or_none()
        if tmpl is None:
            raise ValueError(f"Template v1 #{template_v1_id} no encontrado")
        return tmpl.file_bytes

    raise ValueError("Debés especificar builtin_slug o template_v1_id")
