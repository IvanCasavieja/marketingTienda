"""reset de usuarios existentes — todos a rol "Usuario" con todos los permisos

Migración de datos, una sola vez (a pedido del usuario 2026-07-08): deja a
todos los usuarios registrados hasta ahora (menos el Super Admin) con rol
"Usuario" y acceso funcional completo, como default temporal hasta que se
revise y restrinja permiso por permiso desde el panel de admin. Los usuarios
que se creen DESPUÉS de esta migración no se ven afectados — arrancan según
el rol que se les asigne en ese momento (Usuario = sin permisos por defecto).

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-08
"""
import json

from alembic import op
from sqlalchemy import text

revision      = "0014"
down_revision = "0013"
branch_labels = None
depends_on    = None

# Congelado al momento de escribir esta migración — no se importa
# app.models.role.ALL_PERMISSIONS a propósito, para que esta migración haga
# siempre lo mismo sin importar cómo evolucione el catálogo de permisos más adelante.
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

    # Auto-contenido a propósito: esta migración corre ANTES que
    # tenant_migration.py::migrate_roles() (que es lo que normalmente siembra
    # la fila "Usuario") — si dependiéramos de que ya exista, en el primer
    # deploy con este cambio la fila todavía no estaría creada. Se asegura acá
    # con el mismo ON CONFLICT DO NOTHING que usa el seed normal.
    conn.execute(text("""
        INSERT INTO roles (name, description, permissions, is_system, view_only)
        VALUES ('Usuario', 'Arranca sin permisos — se le arman a medida desde su perfil', '[]', TRUE, FALSE)
        ON CONFLICT (name) DO NOTHING
    """))

    conn.execute(
        text("""
            UPDATE users
            SET role_id = (SELECT id FROM roles WHERE name = 'Usuario'),
                permissions = CAST(:perms AS json)
            WHERE is_superuser = FALSE
        """),
        {"perms": json.dumps(_ALL_PERMISSIONS_AT_THE_TIME)},
    )


def downgrade() -> None:
    # No hay forma de recuperar el estado anterior (permisos individuales
    # previos a esta migración) — es un reset intencional, sin vuelta atrás.
    pass
