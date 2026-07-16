"""create sku_descripciones table

Catálogo compartido SKU → descripción correcta de cenefa, usado por el
Convertidor de Excel para no repetir a mano la misma corrección de
descripción cada vez que un SKU vuelve a aparecer en un export futuro del
sistema de gestión. Se puebla inicialmente con Gestion/Diccionario.xlsx via
scripts/seed_sku_descripciones_standalone.py (fuera de esta migración —
carga de datos, no de esquema).

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-16

"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sku_descripciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.UniqueConstraint("sku", name="uq_sku_descripciones_sku"),
    )


def downgrade() -> None:
    op.drop_table("sku_descripciones")
