"""eliminar todos los productos de Tienda Inglesa

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-20
"""
from alembic import op

revision      = "0005"
down_revision = "0004"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("DELETE FROM precio_historial WHERE tienda = 'Tienda Inglesa'")
    op.execute("DELETE FROM productos WHERE tienda = 'Tienda Inglesa'")


def downgrade() -> None:
    pass  # datos eliminados no se recuperan
