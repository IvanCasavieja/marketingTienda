"""backfill del permiso facturacion.manage en roles/usuarios existentes

Mismo patrón que 0035_facturacion_permissions.py -- ALL_PERMISSIONS tiene un
permiso nuevo (facturacion.manage, para administrar cuentas de Facturación)
que DEFAULT_ROLES no llega a sembrar en roles/usuarios que ya existían.
Se otorga a Superadmin/Admin (ya reciben list(ALL_PERMISSIONS.keys()) al
asignarse el rol) para que las cuentas existentes queden igual de
habilitadas que una cuenta nueva con ese rol. "Usuario"/"Viewer" quedan sin
tocar a propósito, mismo criterio que el resto de los permisos de
Facturación (ver role.py).

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-12
"""
import json

from alembic import op
from sqlalchemy import text

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_NUEVO = "facturacion.manage"


def upgrade() -> None:
    conn = op.get_bind()

    admin_role_ids = {
        r[0] for r in conn.execute(
            text("SELECT id FROM roles WHERE name IN ('Superadmin', 'Admin')")
        ).fetchall()
    }
    if not admin_role_ids:
        return

    for row_id, permissions in conn.execute(
        text("SELECT id, permissions FROM roles WHERE id = ANY(:ids)"),
        {"ids": list(admin_role_ids)},
    ).fetchall():
        permisos = list(permissions or [])
        if _NUEVO not in permisos:
            permisos.append(_NUEVO)
            conn.execute(
                text("UPDATE roles SET permissions = CAST(:perms AS json) WHERE id = :id"),
                {"perms": json.dumps(permisos), "id": row_id},
            )

    for row_id, permissions in conn.execute(
        text("SELECT id, permissions FROM users WHERE role_id = ANY(:ids)"),
        {"ids": list(admin_role_ids)},
    ).fetchall():
        permisos = list(permissions or [])
        if _NUEVO not in permisos:
            permisos.append(_NUEVO)
            conn.execute(
                text("UPDATE users SET permissions = CAST(:perms AS json) WHERE id = :id"),
                {"perms": json.dumps(permisos), "id": row_id},
            )


def downgrade() -> None:
    # No hay vuelta atrás automática -- los permisos pudieron haber sido
    # tildados/destildados a mano después de aplicar esto.
    pass
