"""agregar sucursal_id y sucursal_nombre a productos y precio_historial

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision      = "0007"
down_revision = "0006"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # productos
    op.add_column("productos", sa.Column("sucursal_id",     sa.String(50),  nullable=True))
    op.add_column("productos", sa.Column("sucursal_nombre", sa.String(200), nullable=True))
    op.create_index("ix_productos_sucursal", "productos", ["sucursal_id"])

    # precio_historial
    op.add_column("precio_historial", sa.Column("sucursal_id",     sa.String(50),  nullable=True))
    op.add_column("precio_historial", sa.Column("sucursal_nombre", sa.String(200), nullable=True))
    op.create_index("ix_historial_sucursal", "precio_historial", ["sucursal_id"])


def downgrade() -> None:
    op.drop_index("ix_historial_sucursal", table_name="precio_historial")
    op.drop_column("precio_historial", "sucursal_nombre")
    op.drop_column("precio_historial", "sucursal_id")

    op.drop_index("ix_productos_sucursal", table_name="productos")
    op.drop_column("productos", "sucursal_nombre")
    op.drop_column("productos", "sucursal_id")
