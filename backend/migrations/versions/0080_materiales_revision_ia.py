"""lo del ZIP y el link en la revisión de la IA

Pedido de Ivan (19/11/2026): que la IA revise también lo que la agencia
entrega en un ZIP o en un link (WeTransfer, un link directo), no solo las
imágenes subidas. Lo que la IA miró de ahí, lo que no se pudo abrir (y por
qué) y lo que venía sin ser imagen ni PDF queda con la revisión, para
mostrárselo al aprobador: `calendario_revisiones_ia.materiales` (JSONB,
nullable: las revisiones de antes y las que no tuvieron ZIP ni link no lo
tienen). Ver app/services/materiales.py y revision_ia.materiales_para_mostrar.

Revision ID: 0080
Revises: 0079
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendario_revisiones_ia", sa.Column("materiales", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendario_revisiones_ia", "materiales")
