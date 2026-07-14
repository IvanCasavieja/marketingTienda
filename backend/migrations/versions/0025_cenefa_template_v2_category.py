"""agregar category a cenefa_templates_v2 (redexpress vs rompe_precios)

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-14

"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cenefa_templates_v2", sa.Column("category", sa.String(50), nullable=True))

    # Los 3 builtins (a4/pinchos/black) son las plantillas de RedExpress de hoy.
    op.execute("UPDATE cenefa_templates_v2 SET category = 'redexpress' WHERE is_builtin = true")


def downgrade() -> None:
    op.drop_column("cenefa_templates_v2", "category")
