"""actualizar permisos default del rol "Usuario" (y de quienes ya lo tienen)

Migración de datos (a pedido del usuario 2026-07-08): el rol "Usuario" pasa
de "sin nada" a un set operativo estándar — todo lo funcional (cenefas,
analytics, precios, IA) menos gestión de usuarios/plataforma y gestión de
conexiones (solo ver). Se actualiza tanto la fila del rol en `roles` (para
que sirva de plantilla a futuras asignaciones) como el `permissions`
individual de cada usuario que YA tiene ese rol asignado — reemplaza
cualquier valor previo (incluido el acceso total temporal de la migración 0014).

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-08
"""
import json

from alembic import op
from sqlalchemy import text

revision      = "0016"
down_revision = "0015"
branch_labels = None
depends_on    = None

# Congelado al momento de escribir esta migración.
_USUARIO_PERMISSIONS = [
    "platform.users.view",
    "cenefas.view", "cenefas.generate", "cenefas.edit", "cenefas.import", "cenefas.delete",
    "analytics.view", "analytics.export",
    "connections.view",
    "precios.search",
    "ai.use",
]


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        text("UPDATE roles SET permissions = CAST(:perms AS json) WHERE name = 'Usuario'"),
        {"perms": json.dumps(_USUARIO_PERMISSIONS)},
    )

    conn.execute(
        text("""
            UPDATE users
            SET permissions = CAST(:perms AS json)
            WHERE role_id = (SELECT id FROM roles WHERE name = 'Usuario')
        """),
        {"perms": json.dumps(_USUARIO_PERMISSIONS)},
    )


def downgrade() -> None:
    # No hay vuelta atrás automática al set anterior.
    pass
