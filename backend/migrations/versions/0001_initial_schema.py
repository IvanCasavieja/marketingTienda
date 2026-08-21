"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Enum ---
    platform_enum = postgresql.ENUM(
        "meta", "google_ads", "tiktok", "dv360", "sfmc",
        name="platform",
        create_type=True,
    )
    platform_enum.create(op.get_bind(), checkfirst=True)

    # --- teams ---
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_teams_slug", "teams", ["slug"], unique=True)

    # --- team_groups ---
    op.create_table(
        "team_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("join_code", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("team_group_id", sa.Integer(), sa.ForeignKey("team_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("is_superuser", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --- platform_connections ---
    op.create_table(
        "platform_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_group_id", sa.Integer(), sa.ForeignKey("team_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.Enum("meta", "google_ads", "tiktok", "dv360", "sfmc", name="platform"), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- campaign_metrics ---
    op.create_table(
        "campaign_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_group_id", sa.Integer(), sa.ForeignKey("team_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.Enum("meta", "google_ads", "tiktok", "dv360", "sfmc", name="platform"), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("campaign_id", sa.String(255), nullable=False),
        sa.Column("campaign_name", sa.String(500), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), default=0),
        sa.Column("clicks", sa.Integer(), default=0),
        sa.Column("spend", sa.Float(), default=0.0),
        sa.Column("conversions", sa.Integer(), default=0),
        sa.Column("revenue", sa.Float(), default=0.0),
        sa.Column("reach", sa.Integer(), default=0),
        sa.Column("ctr", sa.Float(), default=0.0),
        sa.Column("cpc", sa.Float(), default=0.0),
        sa.Column("cpm", sa.Float(), default=0.0),
        sa.Column("roas", sa.Float(), default=0.0),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_campaign_metrics_team_date_platform", "campaign_metrics", ["team_group_id", "date", "platform"])
    op.create_index("ix_campaign_metrics_team_date", "campaign_metrics", ["team_group_id", "date"])

    # --- ai_analyses ---
    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_type", sa.String(100), nullable=False),
        sa.Column("platforms", sa.JSON(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("prompt_used", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), default=0),
        sa.Column("output_tokens", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_analyses_user_created", "ai_analyses", ["user_id", "created_at"])

    # --- cenefa_templates ---
    op.create_table(
        "cenefa_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_group_id", sa.Integer(), sa.ForeignKey("team_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("format_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("file_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("resource", sa.String(255), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("cenefa_templates")
    op.drop_table("ai_analyses")
    op.drop_index("ix_campaign_metrics_team_date", table_name="campaign_metrics")
    op.drop_index("ix_campaign_metrics_team_date_platform", table_name="campaign_metrics")
    op.drop_table("campaign_metrics")
    op.drop_table("platform_connections")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("team_groups")
    op.drop_index("ix_teams_slug", table_name="teams")
    op.drop_table("teams")
    sa.Enum(name="platform").drop(op.get_bind(), checkfirst=True)
