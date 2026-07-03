"""fix google_analytics enum value casing to uppercase

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-03

Migration 0010 added 'google_analytics' (lowercase) but SQLAlchemy maps
Python enum members by NAME ('GOOGLE_ANALYTICS'), so the DB value must
be uppercase to match the existing convention (META, GOOGLE_ADS, etc.).
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE platform RENAME VALUE 'google_analytics' TO 'GOOGLE_ANALYTICS'")


def downgrade() -> None:
    op.execute("ALTER TYPE platform RENAME VALUE 'GOOGLE_ANALYTICS' TO 'google_analytics'")
