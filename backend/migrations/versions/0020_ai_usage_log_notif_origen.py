"""add ai_usage_logs table and origen_tipo/origen_ref to notificaciones

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-10

"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notificaciones", sa.Column("origen_tipo", sa.String(50), nullable=True))
    op.add_column("notificaciones", sa.Column("origen_ref", sa.String(255), nullable=True))

    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feature", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_logs_created", "ai_usage_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_logs_created", table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")
    op.drop_column("notificaciones", "origen_ref")
    op.drop_column("notificaciones", "origen_tipo")
