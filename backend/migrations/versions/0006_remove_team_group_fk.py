"""hacer team_group_id nullable — eliminacion del modelo de grupos

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision      = "0006"
down_revision = "0005"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # platform_connections: quitar NOT NULL y FK a team_groups
    with op.batch_alter_table("platform_connections") as batch_op:
        batch_op.alter_column("team_group_id", existing_type=sa.Integer(), nullable=True)
        batch_op.drop_constraint("platform_connections_team_group_id_fkey", type_="foreignkey")

    # campaign_metrics: quitar NOT NULL y FK a team_groups
    with op.batch_alter_table("campaign_metrics") as batch_op:
        batch_op.alter_column("team_group_id", existing_type=sa.Integer(), nullable=True)
        batch_op.drop_constraint("campaign_metrics_team_group_id_fkey", type_="foreignkey")


def downgrade() -> None:
    pass  # no revertimos la eliminacion de grupos
