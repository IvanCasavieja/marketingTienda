from fastapi import APIRouter
from app.api.routes import auth, connections, metrics, analytics, sfmc, tools, chat, cenefas_v2, admin

router = APIRouter()
router.include_router(auth.router)
router.include_router(connections.router)
router.include_router(metrics.router)
router.include_router(analytics.router)
router.include_router(sfmc.router)
router.include_router(tools.router)
router.include_router(chat.router)
router.include_router(cenefas_v2.router)
router.include_router(admin.router)
