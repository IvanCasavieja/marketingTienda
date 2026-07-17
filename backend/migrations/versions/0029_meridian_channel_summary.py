"""create meridian_channel_summary table

Última foto por canal del modelo de Marketing Mix (Meridian): spend, ROI y
% de contribución a la revenue. Se sobreescribe entera en cada corrida via
scripts/import_meridian_summary.py (fuera de esta migración — carga de
datos, no de esquema) — no guarda historial de corridas anteriores.
debate_service.py la usa como contexto real para La Triada cuando
`reliable=True` (52+ semanas de historia al momento de fitear).

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-16

"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meridian_channel_summary",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("spend", sa.Float(), nullable=False),
        sa.Column("pct_of_spend", sa.Float(), nullable=False),
        sa.Column("incremental_outcome", sa.Float(), nullable=False),
        sa.Column("pct_of_contribution", sa.Float(), nullable=False),
        sa.Column("roi", sa.Float(), nullable=False),
        sa.Column("mroi", sa.Float(), nullable=False),
        sa.Column("reliable", sa.Boolean(), nullable=False),
        sa.Column("fitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.UniqueConstraint("channel", name="uq_meridian_channel_summary_channel"),
    )


def downgrade() -> None:
    op.drop_table("meridian_channel_summary")
