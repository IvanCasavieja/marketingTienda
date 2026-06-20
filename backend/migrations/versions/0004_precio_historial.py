"""tabla precio_historial para snapshots diarios de precios

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision      = "0004"
down_revision = "0003"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "precio_historial",
        sa.Column("id",           sa.Integer,      nullable=False),
        sa.Column("tienda",       sa.String(100),  nullable=False),
        sa.Column("url",          sa.String(1000), nullable=False),
        sa.Column("nombre",       sa.String(500)),
        sa.Column("precio",       sa.Float),
        sa.Column("precio_lista", sa.Float),
        sa.Column("sku",          sa.String(100)),
        sa.Column("barcode",      sa.String(50)),
        sa.Column("marca",        sa.String(200)),
        sa.Column("categoria",    sa.String(500)),
        sa.Column("fecha_scan",   sa.Date, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", "fecha_scan", name="uq_historial_url_fecha"),
    )
    op.create_index("ix_historial_fecha_scan", "precio_historial", ["fecha_scan"])
    op.create_index("ix_historial_tienda",     "precio_historial", ["tienda"])
    op.create_index("ix_historial_barcode",    "precio_historial", ["barcode"])


def downgrade() -> None:
    op.drop_index("ix_historial_barcode",    table_name="precio_historial")
    op.drop_index("ix_historial_tienda",     table_name="precio_historial")
    op.drop_index("ix_historial_fecha_scan", table_name="precio_historial")
    op.drop_table("precio_historial")
