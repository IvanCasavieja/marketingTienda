"""presets de banco con descuento del convertidor

precioBanco (+ su decimal) hasta ahora solo salia de una columna del Excel
o de un texto fijo. Muchos descuentos bancarios ("15% extra con Club Card
Scotia") son un multiplicador fijo sobre precioOferta que define Tienda
Inglesa, no algo que gestion traiga calculado por producto. Esta tabla
guarda nombre + multiplicador para reusar de una corrida a otra, mismo
criterio que convertidor_mapeos (compartida por todo el equipo, sin scoping
por usuario).

Revision ID: 0052
Revises: 0051
Create Date: 2026-09-02

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "convertidor_banco_presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("multiplicador", sa.Float(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("convertidor_banco_presets")
