"""cenefas v2 tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0002"
down_revision = "0001"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # --- cenefa_templates_v2 ---
    op.create_table(
        "cenefa_templates_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "team_group_id",
            sa.Integer(),
            sa.ForeignKey("team_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name",       sa.String(255), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column(
            "formats",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_cenefa_templates_v2_team_group",
        "cenefa_templates_v2",
        ["team_group_id"],
    )

    # --- cenefa_jobs ---
    op.create_table(
        "cenefa_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "team_group_id",
            sa.Integer(),
            sa.ForeignKey("team_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cenefa_templates_v2.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status",      sa.String(20),  nullable=False, server_default="pending"),
        sa.Column("format",      sa.String(50),  nullable=False),
        sa.Column("export_type", sa.String(20),  nullable=False, server_default="pptx"),
        sa.Column("row_count",   sa.Integer(),   nullable=True),
        sa.Column("error_count", sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("result_path", sa.String(500), nullable=True),
        sa.Column("validation_report", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cenefa_jobs_team_group", "cenefa_jobs", ["team_group_id"])
    op.create_index("ix_cenefa_jobs_status",     "cenefa_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_cenefa_jobs_status",          table_name="cenefa_jobs")
    op.drop_index("ix_cenefa_jobs_team_group",       table_name="cenefa_jobs")
    op.drop_table("cenefa_jobs")
    op.drop_index("ix_cenefa_templates_v2_team_group", table_name="cenefa_templates_v2")
    op.drop_table("cenefa_templates_v2")
