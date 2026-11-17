"""los comentarios de las tarjetas del tablero, al costado como en Trello

Pedido de Ivan (17/11/2026): "en las tarjetas de los tableros deberiamos tener
una opcion de poner comentario como tiene Trello en un costado, para asi poder
explicar cambios y cosas asi". Los escribe cualquiera que ve la tarjeta: el
equipo de Tienda y el tablero (Publicis, Another Monday o Diseñadores, ver
app/core/tableros.py) al que va la pieza.

Revision ID: 0073
Revises: 0072
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendario_comentarios",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tarea_id", sa.String(64),
                  sa.ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("autor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_calendario_comentarios_tarea_id", "calendario_comentarios", ["tarea_id"])


def downgrade() -> None:
    op.drop_index("ix_calendario_comentarios_tarea_id", table_name="calendario_comentarios")
    op.drop_table("calendario_comentarios")
