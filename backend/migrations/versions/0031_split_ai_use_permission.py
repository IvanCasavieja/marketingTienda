"""separar ai.use en 4 permisos por agente (Don Tino, Doña Tina, Tinín, La Triada)

Migración de datos: ai.use en los hechos solo exigía La Triada (ver
analytics.py) — Don Tino (/chat/message) no tenía ningún permission gate,
y Doña Tina/Tinín ya vivían atados a precios.search/cenefas.view. Se
reemplaza por 4 permisos independientes, backfileados sin sacarle a nadie
acceso a lo que ya podía usar:
  - ai.triada    <- quien ya tenía ai.use
  - ai.dona_tina <- quien ya tenía precios.search (ahí vivían sus 2 endpoints)
  - ai.tinin     <- quien ya tenía cenefas.view (ídem)
  - ai.don_tino  <- todos los usuarios/roles, EXCEPTO los de rol view_only:
    Don Tino era accesible para cualquier autenticado (sin gate), pero no es
    un permiso ".view" — agregárselo a Viewer rompería el próximo guardado
    de permisos de ese usuario desde /admin (rechazo 422, ver admin.py).

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-17
"""
import json

from alembic import op
from sqlalchemy import text

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

_HEREDA_DE = {
    "ai.triada": "ai.use",
    "ai.dona_tina": "precios.search",
    "ai.tinin": "cenefas.view",
}


def _procesar(permissions) -> tuple[list, bool]:
    permisos = list(permissions or [])
    cambio = False
    for nuevo, heredado_de in _HEREDA_DE.items():
        if heredado_de in permisos and nuevo not in permisos:
            permisos.append(nuevo)
            cambio = True
    if "ai.use" in permisos:
        permisos = [p for p in permisos if p != "ai.use"]
        cambio = True
    return permisos, cambio


def upgrade() -> None:
    conn = op.get_bind()

    view_only_ids = {
        r[0] for r in conn.execute(text("SELECT id FROM roles WHERE view_only = true")).fetchall()
    }

    for row_id, permissions in conn.execute(text("SELECT id, permissions FROM roles")).fetchall():
        permisos, cambio = _procesar(permissions)
        if row_id not in view_only_ids and "ai.don_tino" not in permisos:
            permisos.append("ai.don_tino")
            cambio = True
        if cambio:
            conn.execute(
                text("UPDATE roles SET permissions = CAST(:perms AS json) WHERE id = :id"),
                {"perms": json.dumps(permisos), "id": row_id},
            )

    for row_id, role_id, permissions in conn.execute(
        text("SELECT id, role_id, permissions FROM users")
    ).fetchall():
        permisos, cambio = _procesar(permissions)
        if role_id not in view_only_ids and "ai.don_tino" not in permisos:
            permisos.append("ai.don_tino")
            cambio = True
        if cambio:
            conn.execute(
                text("UPDATE users SET permissions = CAST(:perms AS json) WHERE id = :id"),
                {"perms": json.dumps(permisos), "id": row_id},
            )


def downgrade() -> None:
    # No hay vuelta atrás automática — los 4 permisos nuevos pudieron haber
    # sido tildados/destildados a mano después de aplicar esto.
    pass
