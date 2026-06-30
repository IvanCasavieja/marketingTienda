"""eliminar team_group_id de tablas cenefas

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision      = "0008"
down_revision = "0007"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Eliminar índices primero (IF EXISTS por si las tablas no existen todavía)
    op.execute("DROP INDEX IF EXISTS ix_cenefa_templates_v2_team_group")
    op.execute("DROP INDEX IF EXISTS ix_cenefa_jobs_team_group")

    # Eliminar la columna (PostgreSQL elimina automáticamente el FK constraint junto con ella)
    op.execute("ALTER TABLE cenefa_templates_v2 DROP COLUMN IF EXISTS team_group_id")
    op.execute("ALTER TABLE cenefa_jobs DROP COLUMN IF EXISTS team_group_id")


def downgrade() -> None:
    pass  # no revertimos — team_group_id fue eliminado del modelo
