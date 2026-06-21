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
from app.core.tenant_migration import migrate_default_team, migrate_roles
from app.models import Team, TeamGroup, User, PlatformConnection, CampaignMetric, AuditLog, AIAnalysis, CenefaTemplate, CenefaTemplateV2, CenefaJob, Producto, PrecioHistorial
from app.models.role import Role  # noqa: F401 — registers with Base.metadata
from app.api import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.APP_ENV == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await migrate_roles(conn)
        await migrate_default_team(conn)

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

# CORS — only allow configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        # Si la cadena interna lanza excepción no capturada, devolvemos una
        # respuesta propia para que el CORSMiddleware pueda agregar sus headers.
        response = JSONResponse({"detail": "Internal server error"}, status_code=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health():
    import subprocess, os
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd="/app").decode().strip()
    except Exception:
        commit = "unknown"
    return {"status": "ok", "commit": commit}
