"""el tablero, libre como Trello para el equipo de Tienda

Pedido de Ivan (18/11/2026): "¿por qué en el tablero no puedo mover a
esperando feedback o finalizado?". Eligió "libre, como Trello": alguien del
equipo (no una agencia) lleva la tarjeta a cualquier columna.

La columna sale de las entregas (ver reglas.columna_de). Cuando alguien la
lleva a mano a Ingresado, En proceso o Esperando feedback y las entregas no
dicen eso, se guarda acá; Finalizado a mano es darla por aprobada. Lo
próximo que pase de verdad (una entrega, una decisión) vuelve a mandar.

Revision ID: 0075
Revises: 0074
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendario_entregas", sa.Column("columna_manual", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("calendario_entregas", "columna_manual")
