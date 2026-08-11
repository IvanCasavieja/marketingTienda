"""backfill de los permisos de Facturación en roles/usuarios existentes

facturacion.view/facturacion.upload/ai.dogti son nuevos en ALL_PERMISSIONS
(ver role.py). DEFAULT_ROLES solo siembra roles NUEVOS (INSERT ... ON
CONFLICT DO NOTHING en tenant_migration.py::migrate_roles) — las filas de
roles/usuarios que ya existían en la base no los reciben solos, hay que
backfillearlos acá, mismo patrón que 0031_split_ai_use_permission.py.

A diferencia de esos permisos "ai.*" (que heredaban de un permiso ya
existente), acá no hay una herencia natural -- es una sección nueva de la
plataforma. Se otorga a Superadmin/Admin (que ya reciben
list(ALL_PERMISSIONS.keys()) al asignarse el rol) para que las cuentas
existentes queden igual de habilitadas que una cuenta nueva con ese rol.
"Usuario"/"Viewer" quedan sin tocar a propósito -- es acceso a datos
financieros de una única cuenta compartida de toda la empresa, se otorga
puntual por usuario desde el panel, no por defecto (ver role.py).

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-11
"""
import json

from alembic import op
from sqlalchemy import text

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_NUEVOS = ["facturacion.view", "facturacion.upload", "ai.dogti"]


def _con_nuevos(permissions) -> tuple[list, bool]:
    permisos = list(permissions or [])
    cambio = False
    for p in _NUEVOS:
        if p not in permisos:
            permisos.append(p)
            cambio = True
    return permisos, cambio


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
        permisos, cambio = _con_nuevos(permissions)
        if cambio:
            conn.execute(
                text("UPDATE roles SET permissions = CAST(:perms AS json) WHERE id = :id"),
                {"perms": json.dumps(permisos), "id": row_id},
            )

    for row_id, permissions in conn.execute(
        text("SELECT id, permissions FROM users WHERE role_id = ANY(:ids)"),
        {"ids": list(admin_role_ids)},
    ).fetchall():
        permisos, cambio = _con_nuevos(permissions)
        if cambio:
            conn.execute(
                text("UPDATE users SET permissions = CAST(:perms AS json) WHERE id = :id"),
                {"perms": json.dumps(permisos), "id": row_id},
            )


def downgrade() -> None:
    # No hay vuelta atrás automática -- los permisos pudieron haber sido
    # tildados/destildados a mano después de aplicar esto (mismo criterio
    # que 0031_split_ai_use_permission.py).
    pass
