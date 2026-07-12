"""watchlist sharing + duration/lifecycle (estado, fecha_inicio/fin, watchlist_shares)

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-12

"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlists", sa.Column("fecha_inicio", sa.Date(), nullable=True))
    op.add_column("watchlists", sa.Column("fecha_fin", sa.Date(), nullable=True))
    op.add_column("watchlists", sa.Column("estado", sa.String(20), nullable=False, server_default="activa"))

    # Backfill: listas ya existentes arrancaron a monitorear el día que se crearon.
    op.execute("UPDATE watchlists SET fecha_inicio = created_at::date WHERE fecha_inicio IS NULL")

    op.create_index("ix_watchlists_estado", "watchlists", ["estado"])

    op.create_table(
        "watchlist_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.UniqueConstraint("watchlist_id", "user_id", name="uq_watchlist_shares_watchlist_user"),
    )
    op.create_index("ix_watchlist_shares_watchlist", "watchlist_shares", ["watchlist_id"])
    op.create_index("ix_watchlist_shares_user", "watchlist_shares", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_shares_user", "watchlist_shares")
    op.drop_index("ix_watchlist_shares_watchlist", "watchlist_shares")
    op.drop_table("watchlist_shares")
    op.drop_index("ix_watchlists_estado", "watchlists")
    op.drop_column("watchlists", "estado")
    op.drop_column("watchlists", "fecha_fin")
    op.drop_column("watchlists", "fecha_inicio")
