"""create listas de monitoreo tables

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tienda", sa.String(50), nullable=False),
        sa.Column("sku", sa.String(120), nullable=True),
        sa.Column("nombre", sa.String(300), nullable=False),
        sa.Column("termino_busqueda", sa.String(200), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("precio_actual", sa.Float(), nullable=False),
        sa.Column("moneda", sa.String(10), nullable=False),
        sa.Column("ultimo_chequeo", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "watchlist_precio_historial",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("watchlist_item_id", sa.Integer(), sa.ForeignKey("watchlist_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("precio", sa.Float(), nullable=False),
        sa.Column("moneda", sa.String(10), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "notificaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("leida", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("watchlist_item_id", sa.Integer(), sa.ForeignKey("watchlist_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    op.create_index("ix_watchlists_user", "watchlists", ["user_id"])
    op.create_index("ix_watchlist_items_watchlist", "watchlist_items", ["watchlist_id"])
    op.create_index("ix_watchlist_precio_historial_item", "watchlist_precio_historial", ["watchlist_item_id"])
    op.create_index("ix_notificaciones_user", "notificaciones", ["user_id"])
    op.create_index("ix_notificaciones_user_leida", "notificaciones", ["user_id", "leida"])


def downgrade() -> None:
    op.drop_index("ix_notificaciones_user_leida", "notificaciones")
    op.drop_index("ix_notificaciones_user", "notificaciones")
    op.drop_index("ix_watchlist_precio_historial_item", "watchlist_precio_historial")
    op.drop_index("ix_watchlist_items_watchlist", "watchlist_items")
    op.drop_index("ix_watchlists_user", "watchlists")
    op.drop_table("notificaciones")
    op.drop_table("watchlist_precio_historial")
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
