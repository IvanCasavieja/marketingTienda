"""add sucursal_id/sucursal_nombre to watchlist_items

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-09

"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlist_items", sa.Column("sucursal_id", sa.String(50), nullable=True))
    op.add_column("watchlist_items", sa.Column("sucursal_nombre", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlist_items", "sucursal_nombre")
    op.drop_column("watchlist_items", "sucursal_id")
