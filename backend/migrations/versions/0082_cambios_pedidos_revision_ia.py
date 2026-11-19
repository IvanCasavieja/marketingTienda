"""lo que dijo la IA de los cambios pedidos en la ronda anterior

Pedido de Ivan (19/11/2026), cuando se le contó que la IA no comparaba con la
ronda anterior: "debería de hacerlo (...) si ves que algo no anda, ¿por qué no
arreglarlo?". Cuando una versión viene después de una ronda de la misma fase
que volvió con cambios, la IA recibe además lo que se pidió (las marcas y el
comentario) y dice, marca por marca, si se ve hecho, si falta o si es dudoso.
Eso queda con la revisión: `calendario_revisiones_ia.cambios_pedidos` (JSONB,
nullable: las revisiones de antes y las de una primera ronda no lo tienen).
Ver app/services/revision_ia.py (limpiar_cambios_pedidos).

Revision ID: 0082
Revises: 0081
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendario_revisiones_ia", sa.Column("cambios_pedidos", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendario_revisiones_ia", "cambios_pedidos")
