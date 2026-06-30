"""eliminar toda la lógica de teams y team_groups — solo roles

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-30
"""
from alembic import op

revision      = "0009"
down_revision = "0008"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # -- users: quitar team_group_id --
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS team_group_id")

    # -- platform_connections: quitar team_group_id --
    op.execute("ALTER TABLE platform_connections DROP COLUMN IF EXISTS team_group_id")

    # -- campaign_metrics: quitar índices y columna --
    op.execute("DROP INDEX IF EXISTS ix_campaign_metrics_team_date_platform")
    op.execute("DROP INDEX IF EXISTS ix_campaign_metrics_team_date")
    op.execute("ALTER TABLE campaign_metrics DROP COLUMN IF EXISTS team_group_id")

    # -- cenefa_templates (v1): quitar team_group_id --
    op.execute("ALTER TABLE cenefa_templates DROP COLUMN IF EXISTS team_group_id")

    # -- eliminar tablas (CASCADE elimina FKs colgantes) --
    op.execute("DROP TABLE IF EXISTS team_groups CASCADE")
    op.execute("DROP TABLE IF EXISTS teams CASCADE")


def downgrade() -> None:
    pass  # eliminación de grupos es irreversible
