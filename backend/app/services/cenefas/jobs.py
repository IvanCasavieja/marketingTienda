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
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.services.cenefas.component_renderer import patch_image_overrides, render_template_to_pptx
from app.services.cenefas.data_engine import load_products_con_headers
from app.services.cenefas.pptx_importer import import_pptx
from app.services.cenefas.revision_previa import revisar
from app.services.cenefas.validation_engine import build_summary, validate_products

logger = logging.getLogger(__name__)

# Techo de tiempo para el render final (confirm_generation_job) -- sin esto,
# un render trabado deja el job en status="running" para siempre, y el
# polling del frontend (PreviewStep.tsx) espera en silencio sin límite.
#
# 180s alcanzaba de sobra en local (1291 productos ~20s), pero la instancia
# real de Render corre con 1 sola CPU (WEB_CONCURRENCY=1, ver logs) y ahí
# el mismo render de 1291 productos supera los 180s -- confirmado en vivo
# con el archivo real del usuario (disparó este mismo timeout). Subido con
# margen generoso para ese volumen real en hardware más lento.
_RENDER_TIMEOUT_SECONDS = 600

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

    Desde 08/2026 hay UN solo motor de render para todos los destinos
    (component_renderer). Antes, Redexpres pasaba por render_engine.py --un
    motor aparte que reemplazaba texto directo sobre el PPTX y traía su
    propio ajuste automático de tamaño y centrado-- y por eso los
    position_overrides del preview se descartaban en ese camino. Ese motor
    se eliminó: ahora lo que se ve en el preview es lo que sale."""

    template_def:      dict
    products:          list
    target_format:     str
    source_pptx_bytes: bytes | None
    vigencia:          str = ""


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
            "vigencia":          staged.vigencia,
        }
        job.staged_source_pptx = staged.source_pptx_bytes
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
        vigencia=d.get("vigencia", ""),
    )


async def peek_job_products(job_id: uuid.UUID) -> StagedJob | None:
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            return None
        return _staged_job_from_row(job)


async def peek_job(job_id: uuid.UUID) -> CenefaJob | None:
    """Lectura suelta de un job (conexión propia) -- usada por
    confirm_generation_job para recuperar validation_report justo antes de
    escribir el resultado final, sin depender de la conexión abierta al
    principio de esa función (ver _finish_job)."""
    async with AsyncSessionLocal() as db:
        return await _get_job(db, job_id)


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
    template_v2_id:  uuid.UUID | None,
    target_format:   str | None,
    vigencia:        str,
    legales:         str,
    usar_legales:    bool,
    image_overrides:       dict | None = None,
    template_upload_bytes: bytes | None = None,
) -> None:
    """Etapa A: parsea Excel, valida, resuelve la definición de componentes
    (importando el PPTX crudo si vino como archivo) y hornea las imágenes
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
            if template_upload_bytes is not None:
                template_def = await asyncio.to_thread(
                    import_pptx, template_upload_bytes, "Plantilla subida"
                )
                source_pptx_bytes = template_upload_bytes
            else:
                template_def, source_pptx_bytes = await _resolve_template_def(
                    db, builtin_slug, template_v2_id
                )

            # El destino ya no cambia cómo se lee el Excel: las columnas se
            # llaman igual en todos lados. Antes se resolvía la plantilla
            # primero solo para conocer la categoría y ajustar el matching.
            products, headers = await asyncio.to_thread(
                load_products_con_headers, excel_bytes, vigencia, legales, usar_legales
            )
            validation = validate_products(products)
            summary    = build_summary(validation)

            # Revisión del archivo ENTERO contra esta plantilla, además de la
            # validación fila por fila. Es la que ve los errores que arruinan
            # una corrida completa -- una columna mal nombrada deja las N
            # cenefas sin precio y fila por fila no se nota. Nunca bloquea.
            vars_plantilla: set[str] = set()
            for c in template_def.get("components", []):
                if c.get("variable"):
                    vars_plantilla.add(c["variable"])
                for seg in (c.get("segments") or []):
                    if seg.get("type") == "variable" and seg.get("value"):
                        vars_plantilla.add(seg["value"])
            revision = await asyncio.to_thread(revisar, headers, products, vars_plantilla)

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
                vigencia=vigencia,
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
                "revision":     revision,
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


async def _finish_job(
    job_id: uuid.UUID,
    *,
    status: str,
    validation_report: dict | None = None,
    result_path: str | None = None,
) -> None:
    """Escribe el estado final de un job en una conexión NUEVA -- separado a
    propósito del resto de confirm_generation_job (ver ahí el porqué): así
    el commit que reporta "done"/"error" nunca depende de una conexión que
    estuvo abierta e inactiva durante todo el render."""
    async with AsyncSessionLocal() as db:
        job = await _get_job(db, job_id)
        if job is None:
            logger.error("_finish_job: job %s not found", job_id)
            return
        job.status = status
        if validation_report is not None:
            job.validation_report = validation_report
        if result_path is not None:
            job.result_path = result_path
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def confirm_generation_job(
    job_id: uuid.UUID,
    position_overrides: list[dict] | None = None,
) -> None:
    """Etapa B: toma lo que quedó guardado por run_generation_job(), aplica
    los deltas de posición que el usuario movió en el preview (por id de
    componente) y genera el PPTX final.

    A propósito NO mantiene una única conexión a la base abierta durante
    todo esto -- el render puede tardar hasta _RENDER_TIMEOUT_SECONDS, y
    dejar una conexión abierta e inactiva ese tiempo corre el riesgo de que
    el pool (Supabase/PgBouncer) la cierre por inactividad; si el commit
    final ("done"/"error") se hiciera sobre ESA misma conexión ya cortada,
    fallaría en silencio -- el job se queda en "running" para siempre sin
    ningún error visible en ningún lado (síntoma real reportado: "carga y
    carga y nunca termina", sin 409/410/timeout). peek_job_products/
    pop_job_products/store_job_result ya abren su propia conexión nueva
    cada vez (ver arriba) -- acá se hace lo mismo para leer el job inicial
    y para escribir el resultado final, en vez de reusar una sola conexión
    de punta a punta."""
    staged = await pop_job_products(job_id)
    if staged is None:
        await _finish_job(
            job_id, status="error",
            validation_report={"error": "No hay preview pendiente para este job (¿ya se confirmó o expiró?)"},
        )
        return

    try:
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
                    None, staged.source_pptx_bytes,  # image_overrides ya horneado
                ),
                timeout=_RENDER_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"La generación del archivo superó el límite de {_RENDER_TIMEOUT_SECONDS}s. "
                "Probá con menos productos o revisá la plantilla."
            )
        await store_job_result(job_id, pptx_bytes)

        job = await peek_job(job_id)
        report = dict((job.validation_report if job else None) or {})
        report["missing_vars"] = missing_vars

        await _finish_job(job_id, status="done", validation_report=report, result_path=str(job_id))
        logger.info("job %s confirmado y renderizado", job_id)

    except Exception as exc:
        logger.error("job %s confirm failed: %s", job_id, exc, exc_info=True)
        await _finish_job(job_id, status="error", validation_report={"error": str(exc)})


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
        raise ValueError(f"Template {template_id} no encontrado")
    return tmpl.definition, tmpl.source_pptx


async def _resolve_template_def(
    db,
    builtin_slug:   str | None,
    template_v2_id: uuid.UUID | None,
) -> tuple[dict, bytes | None]:
    """Resuelve la plantilla a una definición de componentes.

    Dos orígenes posibles: una plantilla guardada del equipo, o uno de los
    PPTX base que vienen con el repo (builtin), que se importa al vuelo. Los
    dos terminan en el mismo formato y el mismo motor de render.

    Devuelve también los bytes crudos del PPTX origen cuando existen: el
    render final los usa como base para preservar el diseño completo
    (fondo, master, layout y cualquier shape que el importer no haya
    capturado como componente).
    """
    if template_v2_id is not None:
        return await _resolve_template_v2(db, template_v2_id)

    if builtin_slug is None:
        raise ValueError("Debés especificar una plantilla")

    filename = _BUILTIN_FILES.get(builtin_slug)
    if not filename:
        raise ValueError(f"Plantilla predeterminada desconocida: {builtin_slug!r}")
    path = _STATIC_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {path}")
    pptx_bytes = path.read_bytes()
    template_def = await asyncio.to_thread(import_pptx, pptx_bytes, "Plantilla importada")
    return template_def, pptx_bytes
