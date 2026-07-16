"""Background task de generación — orquesta pipeline completo para un job."""
import asyncio
import logging
import pathlib
import pickle
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.cenefa_job import CenefaJob
from app.models.cenefa_template import CenefaTemplate
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.services.cenefas.component_renderer import patch_image_overrides, render_template_to_pptx
from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.pptx_importer import import_pptx
from app.services.cenefas.render_engine import generate_pptx_bytes
from app.services.cenefas.validation_engine import build_summary, validate_products

logger = logging.getLogger(__name__)

_STATIC_DIR = pathlib.Path(__file__).parent.parent.parent / "static" / "cenefa_templates"

_BUILTIN_FILES = {
    "a4":      "Base cenefa A4 1.pptx",
    "pinchos": "Base pinchos 1.pptx",
    "black":   "Bases cenefas BLACK 1.pptx",
}

# Input (Excel parseado + template_def, entre preview y confirm) y output
# (PPTX final, entre confirm y download) viven en Redis, no en un dict del
# proceso — un restart/redeploy a mitad de un job (ej. Render reciclando el
# dyno) ya no lo deja atascado para siempre ni filtra memoria: Redis expira
# solo la entrada si nadie la reclama.
REDIS_INPUT_TTL  = 3_600   # 1h para confirmar un preview
REDIS_RESULT_TTL = 86_400  # 24h para descargar el PPTX ya generado

_RESULT_PREFIX   = "cenefa_job_result:"
_PRODUCTS_PREFIX = "cenefa_job_staged:"


@dataclass
class StagedJob:
    """Lo que queda guardado entre el preview y la confirmación.

    use_legacy_engine=True (RedExpress: builtin/v1/subida al vuelo) → el
    render final usa render_engine.generate_pptx_bytes con excel_bytes +
    template_bytes crudos — el motor viejo, probado, con todo el ajuste
    fino de tamaño/centrado de precio que component_renderer no replica.
    El preview (Canvas) igual usa template_def/products para mostrar algo
    navegable, pero es aproximado — el archivo final NO sale de ahí.

    use_legacy_engine=False (Rompe Precios: template_v2_id) → el render
    final sí usa component_renderer.render_template_to_pptx, que soporta
    aplicar los position_overrides del preview."""
    template_def:      dict
    products:           list
    target_format:      str
    source_pptx_bytes:  bytes | None
    use_legacy_engine:  bool
    excel_bytes:        bytes | None = None
    vigencia:           str = ""
    aclaracion:         str = ""
    otra_alcohol:       str = ""
    banco:              str = ""


async def store_job_result(job_id: uuid.UUID, pptx_bytes: bytes) -> None:
    await get_redis().set(f"{_RESULT_PREFIX}{job_id}", pptx_bytes, ex=REDIS_RESULT_TTL)


async def pop_job_result(job_id: uuid.UUID) -> bytes | None:
    key = f"{_RESULT_PREFIX}{job_id}"
    r = get_redis()
    async with r.pipeline(transaction=True) as pipe:
        value, _ = await pipe.get(key).delete(key).execute()
    return value


async def store_job_products(job_id: uuid.UUID, staged: StagedJob) -> None:
    await get_redis().set(f"{_PRODUCTS_PREFIX}{job_id}", pickle.dumps(staged), ex=REDIS_INPUT_TTL)


async def peek_job_products(job_id: uuid.UUID) -> StagedJob | None:
    raw = await get_redis().get(f"{_PRODUCTS_PREFIX}{job_id}")
    return pickle.loads(raw) if raw else None


async def pop_job_products(job_id: uuid.UUID) -> StagedJob | None:
    key = f"{_PRODUCTS_PREFIX}{job_id}"
    r = get_redis()
    async with r.pipeline(transaction=True) as pipe:
        raw, _ = await pipe.get(key).delete(key).execute()
    return pickle.loads(raw) if raw else None


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

            use_legacy_engine = template_v2_id is None
            if template_upload_bytes is not None:
                template_def = await asyncio.to_thread(
                    import_pptx, template_upload_bytes, "Plantilla subida"
                )
                source_pptx_bytes = template_upload_bytes
            else:
                template_def, source_pptx_bytes = await _resolve_template_def(
                    db, builtin_slug, template_v1_id, template_v2_id
                )
            if image_overrides:
                template_def = {
                    **template_def,
                    "components": patch_image_overrides(template_def.get("components", []), image_overrides),
                }

            # Sin formato explícito: usar el master_format que ya detectó el
            # importer/la plantilla — es lo único que es correcto tanto para
            # diseños de hoja completa (a4) como de celda única (pinchos/3xa4).
            resolved_format = target_format or template_def.get("master_format", "a4")

            await store_job_products(job_id, StagedJob(
                template_def=template_def,
                products=products,
                target_format=resolved_format,
                source_pptx_bytes=source_pptx_bytes,
                use_legacy_engine=use_legacy_engine,
                excel_bytes=excel_bytes,
                vigencia=vigencia,
                aclaracion=aclaracion,
                otra_alcohol=otra_alcohol,
                banco=banco,
            ))

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

        staged = await pop_job_products(job_id)
        if staged is None:
            job.status            = "error"
            job.validation_report = {"error": "No hay preview pendiente para este job (¿ya se confirmó o expiró?)"}
            job.completed_at      = datetime.now(timezone.utc)
            await db.commit()
            return

        try:
            if staged.use_legacy_engine:
                # RedExpress: el render final pasa por el motor viejo tal
                # cual, sin tocar nada — es el que ya tiene calibrado el
                # achicado/centrado de precio y demás ajustes de layout A4
                # que component_renderer no replica. Los position_overrides
                # del preview NO se aplican acá a propósito: ese motor no
                # tiene un modelo de "mover este shape", y aplicar ediciones
                # parciales de posición sobre su lógica de centrado
                # automático podría romper justo lo que queremos preservar.
                if position_overrides:
                    logger.info(
                        "job %s: se ignoran %d overrides de posición (motor legado, RedExpress)",
                        job_id, len(position_overrides),
                    )
                pptx_bytes = await asyncio.to_thread(
                    generate_pptx_bytes,
                    staged.excel_bytes, staged.source_pptx_bytes,
                    staged.vigencia, staged.aclaracion, staged.otra_alcohol, staged.banco,
                )
                missing_vars: list[str] = []
            else:
                template_def = staged.template_def
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
                    render_template_to_pptx, template_def, staged.products, staged.target_format,
                    None, staged.source_pptx_bytes,  # image_overrides ya horneado, source_pptx_bytes
                )
            await store_job_result(job_id, pptx_bytes)

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


async def _resolve_template_v2(db, template_id: uuid.UUID) -> tuple[dict, bytes | None]:
    result = await db.execute(
        select(CenefaTemplateV2).where(CenefaTemplateV2.id == template_id)
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        raise ValueError(f"Template v2 {template_id} no encontrado")
    return tmpl.definition, tmpl.source_pptx


async def _resolve_template_def(
    db,
    builtin_slug:   str | None,
    template_v1_id: int | None,
    template_v2_id: uuid.UUID | None,
) -> tuple[dict, bytes | None]:
    """Unifica los 3 orígenes posibles de plantilla en una definición de
    componentes v2 — para builtin/v1 (pptx crudo, sin datos de posición)
    corre el importer, así RedExpress también puede reposicionar en el
    preview aunque su plantilla nunca haya pasado por el editor v2.

    Devuelve también los bytes crudos del pptx origen cuando existen — el
    render final los usa para preservar el diseño (ver component_renderer).
    Para un template v2 armado a mano en el editor (sin source_pptx en la
    DB), es None y el render cae al canvas en blanco de siempre."""
    if template_v2_id is not None:
        return await _resolve_template_v2(db, template_v2_id)

    pptx_bytes = await _resolve_template_pptx(db, builtin_slug, template_v1_id)
    template_def = await asyncio.to_thread(import_pptx, pptx_bytes, "Plantilla importada")
    return template_def, pptx_bytes


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
