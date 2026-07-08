"""corregir roles — Usuario A deja de ser Super Admin, 4 personas pasan a Admin

Migración de datos puntual (a pedido del usuario 2026-07-08): Usuario A
aparecía como Super Admin por error — el único Super Admin debe ser la cuenta
de Ivan. Estas 4 personas pasan a rol "Admin" (todos los permisos activos,
ajustables después por usuario desde el panel):
  - usuarioA@example.com   (deja de ser is_superuser)
  - usuarioB@example.com
  - usuarioC@example.com
  - usuarioD@example.com

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-08
"""
import json

from alembic import op
from sqlalchemy import text

revision      = "0015"
down_revision = "0014"
branch_labels = None
depends_on    = None

# Congelado al momento de escribir esta migración — ver 0014 para el porqué
# de no importar app.models.role.ALL_PERMISSIONS acá.
_ALL_PERMISSIONS_AT_THE_TIME = [
    "platform.super", "platform.admin", "platform.users.view", "platform.users.manage",
    "cenefas.view", "cenefas.generate", "cenefas.edit", "cenefas.import", "cenefas.delete",
    "analytics.view", "analytics.export",
    "connections.view", "connections.manage",
    "precios.search",
    "ai.use",
]


def upgrade() -> None:
    conn = op.get_bind()

    # Auto-contenido — ver 0014 para el porqué (esta migración corre antes que
    # tenant_migration.py::migrate_roles(), que es lo que normalmente siembra
    # los roles del sistema).
    conn.execute(
        text("""
            INSERT INTO roles (name, description, permissions, is_system, view_only)
            VALUES ('Admin', 'Arranca con todos los permisos; se pueden ajustar por usuario', CAST(:perms AS json), TRUE, FALSE)
            ON CONFLICT (name) DO NOTHING
        """),
        {"perms": json.dumps(_ALL_PERMISSIONS_AT_THE_TIME)},
    )

    conn.execute(
        text("""
            UPDATE users
            SET role_id      = (SELECT id FROM roles WHERE name = 'Admin'),
                permissions  = CAST(:perms AS json),
                is_superuser = FALSE
            WHERE LOWER(email) IN (:e1, :e2, :e3, :e4)
        """),
        {
            "perms": json.dumps(_ALL_PERMISSIONS_AT_THE_TIME),
            "e1": "usuarioA@example.com",
            "e2": "usuarioB@example.com",
            "e3": "usuarioC@example.com",
            "e4": "usuarioD@example.com",
        },
    )


def downgrade() -> None:
    # No hay vuelta atrás automática — restaurar manualmente si hace falta.
    pass
