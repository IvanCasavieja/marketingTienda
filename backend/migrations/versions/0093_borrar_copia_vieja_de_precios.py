"""borra la copia vieja de precios de la competencia (productos y precio_historial)

Ivan (26/11/2026), mirando qué ocupa lugar en la base: OK para borrarla.

Es la foto de precios de Disco, Devoto, Géant, Ta-Ta, Farmashop, Botiga y El
Dorado que bajó un robot nocturno entre el 20/06 y el 01/07/2026 (0003, 0004,
0007). Ese 01/07 se borraron el robot, los modelos y las pantallas del
catálogo, y las dos tablas quedaron solas en la base: nada las lee. Buscar
precios busca en vivo en las cadenas y las listas de monitoreo tienen sus
propias tablas (watchlist_*). `productos` ocupaba 16,5 MB de los 500 de la
cuota de Supabase (36.975 filas y sus índices); `precio_historial`, casi nada.

Irreversible: los datos no vuelven. DROP devuelve el lugar en el momento, sin
VACUUM FULL. El downgrade recrea las dos tablas vacías con el esquema que
tenían (sin el índice duplicado que sacó la 0053), para no mentirle al
historial.

Revision ID: 0093
Revises: 0092
Create Date: 2026-11-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS precio_historial")
    op.execute("DROP TABLE IF EXISTS productos")


def downgrade() -> None:
    op.create_table(
        "productos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tienda", sa.String(100), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False, unique=True),
        sa.Column("nombre", sa.String(500), nullable=True),
        sa.Column("precio", sa.Float(), nullable=True),
        sa.Column("precio_lista", sa.Float(), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("barcode", sa.String(50), nullable=True),
        sa.Column("marca", sa.String(200), nullable=True),
        sa.Column("categoria", sa.String(500), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sucursal_id", sa.String(50), nullable=True),
        sa.Column("sucursal_nombre", sa.String(200), nullable=True),
    )
    op.create_index("ix_productos_tienda", "productos", ["tienda"])
    op.create_index("ix_productos_sku", "productos", ["sku"])
    op.create_index("ix_productos_barcode", "productos", ["barcode"])
    op.create_index("ix_productos_nombre", "productos", ["nombre"])
    op.create_index("ix_productos_sucursal", "productos", ["sucursal_id"])

    op.create_table(
        "precio_historial",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("tienda", sa.String(100), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("nombre", sa.String(500)),
        sa.Column("precio", sa.Float),
        sa.Column("precio_lista", sa.Float),
        sa.Column("sku", sa.String(100)),
        sa.Column("barcode", sa.String(50)),
        sa.Column("marca", sa.String(200)),
        sa.Column("categoria", sa.String(500)),
        sa.Column("fecha_scan", sa.Date, nullable=False),
        sa.Column("sucursal_id", sa.String(50), nullable=True),
        sa.Column("sucursal_nombre", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", "fecha_scan", name="uq_historial_url_fecha"),
    )
    op.create_index("ix_historial_fecha_scan", "precio_historial", ["fecha_scan"])
    op.create_index("ix_historial_tienda", "precio_historial", ["tienda"])
    op.create_index("ix_historial_barcode", "precio_historial", ["barcode"])
    op.create_index("ix_historial_sucursal", "precio_historial", ["sucursal_id"])
