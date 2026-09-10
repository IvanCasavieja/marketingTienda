"""permisos por usuario — agrega users.permissions y roles.view_only

Revision ID: 0013
Revises: 0012_1
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision      = "0013"
down_revision = "0012_1"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("users", sa.Column("permissions", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("roles", sa.Column("view_only",   sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("roles", "view_only")
    op.drop_column("users", "permissions")
