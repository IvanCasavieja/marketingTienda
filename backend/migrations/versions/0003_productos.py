"""tabla productos para catálogo de precios de supermercados

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision      = "0003"
down_revision = "0002"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "productos",
        sa.Column("id",           sa.Integer(),      primary_key=True),
        sa.Column("tienda",       sa.String(100),    nullable=False),
        sa.Column("url",          sa.String(1000),   nullable=False, unique=True),
        sa.Column("nombre",       sa.String(500),    nullable=True),
        sa.Column("precio",       sa.Float(),        nullable=True),
        sa.Column("precio_lista", sa.Float(),        nullable=True),
        sa.Column("sku",          sa.String(100),    nullable=True),
        sa.Column("barcode",      sa.String(50),     nullable=True),
        sa.Column("marca",        sa.String(200),    nullable=True),
        sa.Column("categoria",    sa.String(500),    nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_productos_url",      "productos", ["url"],      unique=True)
    op.create_index("ix_productos_tienda",   "productos", ["tienda"])
    op.create_index("ix_productos_sku",      "productos", ["sku"])
    op.create_index("ix_productos_barcode",  "productos", ["barcode"])
    op.create_index("ix_productos_nombre",   "productos", ["nombre"])


def downgrade() -> None:
    op.drop_index("ix_productos_nombre",  table_name="productos")
    op.drop_index("ix_productos_barcode", table_name="productos")
    op.drop_index("ix_productos_sku",     table_name="productos")
    op.drop_index("ix_productos_tienda",  table_name="productos")
    op.drop_index("ix_productos_url",     table_name="productos")
    op.drop_table("productos")
