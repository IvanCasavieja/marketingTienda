"""Logging estructurado.

structlog envuelve el logging stdlib existente en vez de reemplazarlo —
ProcessorFormatter intercepta el LogRecord que ya arma cualquier
`logging.getLogger(__name__).info(...)` de siempre (no hace falta tocar esos
~20 módulos) y lo renderiza como JSON en producción, agregando nivel,
timestamp y — vía request_id_middleware en main.py — el request_id de
contextvars, para poder correlacionar todas las líneas de un mismo request
en el mismo incidente."""
import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Consola coloreada en dev (más legible mientras se labura en local),
    # JSON en cualquier otro entorno (lo que Render/Supabase/un futuro
    # agregador de logs puede parsear).
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.APP_ENV == "development"
        else structlog.processors.JSONRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # uvicorn instala sus propios handlers en "uvicorn"/"uvicorn.access" — se
    # los sacamos para que propaguen al root y salgan con el mismo formato
    # estructurado que el resto de los logs, en vez de un formato aparte.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True
