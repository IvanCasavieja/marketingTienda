"""renombrar redexpress -> redexpres (permiso + categoria de template)

El código pasa "redexpress.view" -> "redexpres.view" y la categoría de
template "redexpress" -> "redexpres", pero eso no actualiza lo que ya está
persistido: roles.permissions y users.permissions son arrays JSON con el
string viejo grabado, y cenefa_templates_v2.category tiene 'redexpress' en
los 3 builtins (ver migración 0025). Sin esto, cualquier usuario/rol que ya
tenía el permiso otorgado pierde el acceso en silencio, y el matching de
templates por destino deja de encontrar los builtin.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_OLD_PERM = "redexpress.view"
_NEW_PERM = "redexpres.view"


def _rename_permission(old: str, new: str) -> None:
    """Recorre roles y users fila por fila en vez de un UPDATE con funciones
    JSONB específicas — permissions es JSON genérico (no necesariamente
    jsonb), así que esto no depende de qué tipo exacto tenga la columna."""
    conn = op.get_bind()
    for table_name in ("roles", "users"):
        table = sa.table(table_name, sa.column("id", sa.Integer), sa.column("permissions", sa.JSON))
        rows = conn.execute(sa.select(table.c.id, table.c.permissions)).fetchall()
        for row_id, perms in rows:
            perms = perms or []
            if old not in perms:
                continue
            new_perms = [new if p == old else p for p in perms]
            conn.execute(sa.update(table).where(table.c.id == row_id).values(permissions=new_perms))


def upgrade() -> None:
    _rename_permission(_OLD_PERM, _NEW_PERM)
    op.execute("UPDATE cenefa_templates_v2 SET category = 'redexpres' WHERE category = 'redexpress'")


def downgrade() -> None:
    _rename_permission(_NEW_PERM, _OLD_PERM)
    op.execute("UPDATE cenefa_templates_v2 SET category = 'redexpress' WHERE category = 'redexpres'")
