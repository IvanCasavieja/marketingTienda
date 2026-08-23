import logging
import re
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from app.core.deps import require_permission
from app.models.user import User
from app.services.cenefas.data_engine import generate_template_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])

_BUILTIN_TEMPLATES = [
    {"slug": "a4",      "name": "Cenefa A4",   "format_name": "A4",     "filename": "Base cenefa A4 1.pptx"},
    {"slug": "pinchos", "name": "Pinchos",      "format_name": "Pinchos","filename": "Base pinchos 1.pptx"},
    {"slug": "black",   "name": "Cenefas 3xA4", "format_name": "3xA4",  "filename": "Bases cenefas BLACK 1.pptx"},
]


def _safe_filename(name: str) -> str:
    """El nombre del template es texto libre cargado por el usuario y termina
    reflejado sin escapar en el header Content-Disposition — una comilla ahí
    rompe el parámetro filename= y permite manipular la respuesta. Sacamos
    comillas, backslashes y cualquier caracter de control (CR/LF incluidos)."""
    cleaned = re.sub(r'[\x00-\x1f\x7f"\\]', "", name)
    return cleaned.strip() or "template"


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
# El endpoint síncrono de generación (POST /cenefas/generate) se retiró —
# tanto Redexpres como Rompe Precios generan ahora vía el pipeline de jobs
# async (POST /tools/cenefas/v2/jobs), que además deja el paso de preview +
# reposicionar antes del render final. El motor viejo (render_engine.py) se
# eliminó en 08/2026 -- hoy hay un solo motor para todos los destinos.

@router.get("/cenefas/template")
async def download_cenefa_template(
    destino: str = Query("cenefas", description="Destino -- solo afecta el nombre del archivo"),
    current_user: User = Depends(require_permission("cenefas.view")),
):
    """Plantilla Excel con las 26 columnas del sistema.

    Es la misma para todos los destinos: el vocabulario de variables es
    único y cada diseño usa las que necesita."""
    xlsx_bytes = generate_template_bytes(destino)
    filename = f"plantilla_{destino}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Plantillas base que vienen con el repo
# ---------------------------------------------------------------------------

@router.get("/cenefas/builtin-templates")
async def list_builtin_templates(
    current_user: User = Depends(require_permission("cenefas.view")),
):
    return [
        {"slug": t["slug"], "name": t["name"], "format_name": t["format_name"]}
        for t in _BUILTIN_TEMPLATES
    ]


# ---------------------------------------------------------------------------
# Las plantillas v1 (PPTX crudo guardado en cenefa_templates) se eliminaron
# en 08/2026: Redexpres pasó a usar el mismo editor y el mismo motor que el
# resto de las cenefas, así que ya no hay dos sistemas de plantillas. El CRUD
# de esas plantillas vivía acá; ahora todo pasa por /tools/cenefas/v2/templates.
# ---------------------------------------------------------------------------
