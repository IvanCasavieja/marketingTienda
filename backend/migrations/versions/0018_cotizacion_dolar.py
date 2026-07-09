"""create cotizaciones_dolar table

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-09

"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cotizaciones_dolar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fecha", sa.Date(), nullable=False, unique=True),
        sa.Column("compra", sa.Float(), nullable=False),
        sa.Column("venta", sa.Float(), nullable=False),
        sa.Column("fuente", sa.String(20), nullable=False, server_default="brou"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    op.create_index("ix_cotizaciones_dolar_fecha", "cotizaciones_dolar", ["fecha"])


def downgrade() -> None:
    op.drop_index("ix_cotizaciones_dolar_fecha", "cotizaciones_dolar")
    op.drop_table("cotizaciones_dolar")
