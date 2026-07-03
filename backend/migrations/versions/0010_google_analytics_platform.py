"""add google_analytics to platform enum

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-03

"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE platform ADD VALUE IF NOT EXISTS 'google_analytics'")


def downgrade() -> None:
    # PostgreSQL no permite eliminar valores de un enum sin recrearlo
    pass
