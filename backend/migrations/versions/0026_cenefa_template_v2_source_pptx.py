"""agregar source_pptx a cenefa_templates_v2 (preservar diseno original)

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-14

"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cenefa_templates_v2", sa.Column("source_pptx", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("cenefa_templates_v2", "source_pptx")
