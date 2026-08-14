"""Background task de generación — orquesta pipeline completo para un job."""
import asyncio
import logging
import pathlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.cenefa_job import CenefaJob
from app.models.cenefa_template import CenefaTemplate
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.services.cenefas.component_renderer import patch_image_overrides, render_template_to_pptx
from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.pptx_importer import import_pptx
from app.services.cenefas.render_engine import generate_pptx_bytes
from app.services.cenefas.validation_engine import build_summary, validate_products

logger = logging.getLogger(__name__)

# Techo de tiempo para el render final (confirm_generation_job) -- sin esto,
# un render trabado deja el job en status="running" para siempre, y el
# polling del frontend (PreviewStep.tsx) espera en silencio sin límite.
_RENDER_TIMEOUT_SECONDS = 180

_STATIC_DIR = pathlib.Path(__file__).parent.parent.parent / "static" / "cenefa_templates"

_BUILTIN_FILES = {
    "a4":      "Base cenefa A4 1.pptx",
    "pinchos": "Base pinchos 1.pptx",
    "black":   "Bases cenefas BLACK 1.pptx",
}

# Estado entre preview/confirmación + resultado final: persistido en
# Postgres (columnas staged_data/staged_source_pptx/staged_excel_bytes/
# result_bytes de CenefaJob, ver migración 0038), NO en un dict del proceso.
#
# Historia: el 15/07 se probó Redis para esto mismo, pero Render no tenía
# ningún Redis provisionado en producción (REDIS_URL caía al default
# "localhost:6379", inexistente ahí) y rompió /materiales/cenefas al toque.
# El 16/07 se revirtió a un dict en memoria para desbloquear la herramienta
# sin gastar en un plan Starter de Redis. Contrapartida ya conocida de ese
# dict: un job confirmado justo cuando el backend redespliega (o si hay más
# de una instancia sirviendo tráfico) quedaba inaccesible -- "el resultado
# ya fue descargado o el servidor se reinició" (410) sin haberse descargado
# nunca. Postgres ya está provisionado (sin costo extra) y no tiene ese
# problema de disponibilidad, así que reemplaza al dict directamente sin
# reintroducir la dependencia de Redis que ya se probó frágil acá.


@dataclass
class StagedJob:
    """Lo que queda guardado entre el preview y la confirmación.

    use_legacy_engine=True (Redexpres: builtin/v1/subida al vuelo) → el
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
    category:           str | None = None
    excel_bytes:        bytes | None = None
    vigencia:           str = ""
    aclaracion:         str = ""
    otra_alcohol:       str = ""
    banco:              str = ""


async def store_job_result(job_id: uuid.UUID, pptx_bytes: bytes) -> None:
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            return
        job.result_bytes = pptx_bytes
        await db.commit()


async def get_job_result(job_id: uuid.UUID) -> bytes | None:
    # No destructivo a propósito (a diferencia del dict en memoria de
    # antes): "Descargar de nuevo" en PreviewStep.tsx vuelve a pegarle a
    # este mismo endpoint, y con el dict eso ya daba 410 en el segundo
    # click -- guardado en Postgres no hay presión de memoria que obligue a
    # limpiarlo apenas se sirve una vez.
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            return None
        return job.result_bytes


async def store_job_products(job_id: uuid.UUID, staged: StagedJob) -> None:
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            return
        job.staged_data = {
            "template_def":      staged.template_def,
            "products":          staged.products,
            "target_format":     staged.target_format,
            "use_legacy_engine": staged.use_legacy_engine,
            "category":          staged.category,
            "vigencia":          staged.vigencia,
            "aclaracion":        staged.aclaracion,
            "otra_alcohol":      staged.otra_alcohol,
            "banco":             staged.banco,
        }
        job.staged_source_pptx = staged.source_pptx_bytes
        job.staged_excel_bytes = staged.excel_bytes
        await db.commit()


def _staged_job_from_row(job: CenefaJob) -> StagedJob | None:
    d = job.staged_data
    if d is None:
        return None
    return StagedJob(
        template_def=d["template_def"],
        products=d["products"],
        target_format=d["target_format"],
        source_pptx_bytes=job.staged_source_pptx,
        use_legacy_engine=d["use_legacy_engine"],
        category=d.get("category"),
        excel_bytes=job.staged_excel_bytes,
        vigencia=d.get("vigencia", ""),
        aclaracion=d.get("aclaracion", ""),
        otra_alcohol=d.get("otra_alcohol", ""),
        banco=d.get("banco", ""),
    )


async def peek_job_products(job_id: uuid.UUID) -> StagedJob | None:
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            return None
        return _staged_job_from_row(job)


async def pop_job_products(job_id: uuid.UUID) -> StagedJob | None:
    # Destructivo a propósito, a diferencia de result_bytes: el PPTX/Excel
    # crudo de acá puede pesar varios MB y solo hace falta una vez, para
    # alimentar el render final -- no tiene sentido dejarlo ocupando la fila
    # para siempre después de confirmado.
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            return None
        staged = _staged_job_from_row(job)
        if staged is None:
            return None
        job.staged_data = None
        job.staged_source_pptx = None
        job.staged_excel_bytes = None
        await db.commit()
        return staged


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
            # Resolver la plantilla PRIMERO -- category tiene que estar
            # disponible antes de parsear el Excel, porque el matching de
            # columnas de Parrilla y Vinos depende del destino (ver
            # data_engine.py::load_products_from_bytes). Ninguno de los dos
            # bloques depende del resultado del otro, así que reordenar acá
            # no cambia ningún otro comportamiento.
            use_legacy_engine = template_v2_id is None
            if template_upload_bytes is not None:
                template_def = await asyncio.to_thread(
                    import_pptx, template_upload_bytes, "Plantilla subida"
                )
                source_pptx_bytes = template_upload_bytes
                category = None
            else:
                template_def, source_pptx_bytes, category = await _resolve_template_def(
                    db, builtin_slug, template_v1_id, template_v2_id
                )

            products = await asyncio.to_thread(
                load_products_from_bytes, excel_bytes, vigencia, aclaracion, otra_alcohol, banco, category
            )
            validation = validate_products(products)
            summary    = build_summary(validation)

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
                category=category,
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
                # Redexpres: el render final pasa por el motor viejo tal
                # cual, sin tocar nada — es el que ya tiene calibrado el
                # achicado/centrado de precio y demás ajustes de layout A4
                # que component_renderer no replica. Los position_overrides
                # del preview NO se aplican acá a propósito: ese motor no
                # tiene un modelo de "mover este shape", y aplicar ediciones
                # parciales de posición sobre su lógica de centrado
                # automático podría romper justo lo que queremos preservar.
                if position_overrides:
                    logger.info(
                        "job %s: se ignoran %d overrides de posición (motor legado, Redexpres)",
                        job_id, len(position_overrides),
                    )
                try:
                    pptx_bytes = await asyncio.wait_for(
                        asyncio.to_thread(
                            generate_pptx_bytes,
                            staged.excel_bytes, staged.source_pptx_bytes,
                            staged.vigencia, staged.aclaracion, staged.otra_alcohol, staged.banco,
                        ),
                        timeout=_RENDER_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        f"La generación del archivo superó el límite de {_RENDER_TIMEOUT_SECONDS}s. "
                        "Probá con menos productos o revisá la plantilla."
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
                try:
                    pptx_bytes, missing_vars = await asyncio.wait_for(
                        asyncio.to_thread(
                            render_template_to_pptx, template_def, staged.products, staged.target_format,
                            None, staged.source_pptx_bytes,  # image_overrides ya horneado, source_pptx_bytes
                            staged.category,
                        ),
                        timeout=_RENDER_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        f"La generación del archivo superó el límite de {_RENDER_TIMEOUT_SECONDS}s. "
                        "Probá con menos productos o revisá la plantilla."
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


async def _resolve_template_v2(db, template_id: uuid.UUID) -> tuple[dict, bytes | None, str | None]:
    result = await db.execute(
        select(CenefaTemplateV2).where(CenefaTemplateV2.id == template_id)
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        raise ValueError(f"Template v2 {template_id} no encontrado")
    return tmpl.definition, tmpl.source_pptx, tmpl.category


async def _resolve_template_def(
    db,
    builtin_slug:   str | None,
    template_v1_id: int | None,
    template_v2_id: uuid.UUID | None,
) -> tuple[dict, bytes | None, str | None]:
    """Unifica los 3 orígenes posibles de plantilla en una definición de
    componentes v2 — para builtin/v1 (pptx crudo, sin datos de posición)
    corre el importer, así Redexpres también puede reposicionar en el
    preview aunque su plantilla nunca haya pasado por el editor v2.

    Devuelve también los bytes crudos del pptx origen cuando existen — el
    render final los usa para preservar el diseño (ver component_renderer) —
    y la categoría del template v2 (None para builtin/v1, que siempre son
    Redexpres): render_template_to_pptx la usa para restringir a Rompe
    Precios los ajustes de precio que no deben tocar otras plantillas."""
    if template_v2_id is not None:
        return await _resolve_template_v2(db, template_v2_id)

    pptx_bytes = await _resolve_template_pptx(db, builtin_slug, template_v1_id)
    template_def = await asyncio.to_thread(import_pptx, pptx_bytes, "Plantilla importada")
    return template_def, pptx_bytes, None


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
