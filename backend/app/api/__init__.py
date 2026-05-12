from fastapi import APIRouter
from app.api.routes import auth, connections, metrics, analytics, sfmc

router = APIRouter()
router.include_router(auth.router)
router.include_router(connections.router)
router.include_router(metrics.router)
router.include_router(analytics.router)
router.include_router(sfmc.router)
