import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app.core.tenant_migration import migrate_roles
from app.models import User, PlatformConnection, CampaignMetric, AuditLog, AIAnalysis, CenefaTemplate, CenefaTemplateV2, CenefaJob, Producto, PrecioHistorial
from app.models.role import Role  # noqa: F401 — registers with Base.metadata
from app.api import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.APP_ENV == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Migraciones en background — no bloquear el lifespan.
    # Render mata la instancia si /health no responde en 5s, y scripts/migrate.py
    # tarda 3-5s abriendo conexiones síncronas a Supabase antes de que uvicorn arranque.
    # Solución: uvicorn arranca solo, migraciones corren acá en background.
    def _run_alembic():
        """Ejecuta scripts/migrate.py en thread pool (es código síncrono)."""
        import os, sys
        from sqlalchemy import create_engine, inspect, text as sa_text
        raw_url = os.environ.get("DATABASE_URL", "")
        if not raw_url:
            return
        sync_url = raw_url.replace("postgresql+asyncpg://", "postgresql://")
        eng = create_engine(sync_url)
        try:
            with eng.connect() as conn:
                tables = inspect(eng).get_table_names()
                if "alembic_version" not in tables and "teams" in tables:
                    conn.execute(sa_text(
                        "CREATE TABLE alembic_version "
                        "(version_num VARCHAR(32) NOT NULL CONSTRAINT alembic_version_pkc PRIMARY KEY)"
                    ))
                    conn.execute(sa_text("INSERT INTO alembic_version (version_num) VALUES ('0001')"))
                    conn.commit()
        finally:
            eng.dispose()
        from alembic import command
        from alembic.config import Config
        command.upgrade(Config("alembic.ini"), "head")
        logger.info("Alembic migrations completed")

    async def _run_migrations():
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, _run_alembic)
        except Exception as e:
            logger.error("Alembic migration failed: %s", e)
        try:
            async with engine.begin() as conn:
                await migrate_roles(conn)
        except Exception as e:
            logger.error("In-app migrations failed: %s", e)

    asyncio.create_task(_run_migrations())

    # Arrancar auto-sync de métricas si está habilitado
    sync_task = None
    if settings.SYNC_INTERVAL_HOURS > 0:
        from app.services.auto_sync import run_auto_sync_loop
        sync_task = asyncio.create_task(run_auto_sync_loop())
        logger.info("auto_sync: loop iniciado (cada %dh)", settings.SYNC_INTERVAL_HOURS)

    # Arrancar scraper nocturno de precios si está habilitado
    scraper_task = None
    if settings.SCRAPER_ENABLED:
        import os
        os.environ.setdefault("SCRAPER_DATA_DIR", settings.SCRAPER_DATA_DIR)
        from app.services.scraper_sync import run_scraper_loop
        scraper_task = asyncio.create_task(run_scraper_loop())
        logger.info(
            "scraper_sync: scheduler iniciado — diario %02d:%02d UY",
            settings.SCRAPER_HOUR, settings.SCRAPER_MINUTE,
        )

    yield

    for task in (sync_task, scraper_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

app = FastAPI(
    lifespan=lifespan,
    title="MKTG Platform API",
    version="1.0.0",
    docs_url="/api/docs" if settings.APP_ENV == "development" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.APP_ENV == "development" else None,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security headers middleware — must be registered BEFORE CORSMiddleware so that
# CORS ends up as the outermost middleware. In Starlette, the last middleware
# registered via add_middleware becomes the outermost one. Using the decorator here
# and then calling add_middleware(CORS) below achieves: CORS → security_headers → SlowAPI → app.
# This ensures CORS headers are always injected even for 5xx responses.
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# CORS — registered last so it becomes the outermost middleware and injects
# Access-Control-Allow-Origin on ALL responses, including 5xx errors.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(router, prefix=settings.API_V1_PREFIX)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Convierte cualquier excepcion no manejada en JSONResponse antes de que
    llegue al middleware — garantiza que CORSMiddleware siempre pueda inyectar
    el header Access-Control-Allow-Origin, incluso en respuestas 500."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
