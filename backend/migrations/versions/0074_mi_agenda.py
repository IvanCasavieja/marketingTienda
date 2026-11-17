"""mi agenda: el calendario de cada persona (Outlook, Google) adentro de Core Tienda

Pedido de Ivan (17/11/2026): "que la gente pueda importar su propio
calendario a la aplicacion y que se vaya actualizando con los eventos que
vayan agregando". Una fila por persona con el link (cifrado) y los eventos de
la última lectura; solo la ve su dueño (ver app/services/agenda_externa.py).

En lugar del link que llevaba las acciones de Tienda a Outlook, que se sacó:
"no me gusta que las acciones del calendario de Tienda puedan estar en un
calendario cualquiera".

Revision ID: 0074
Revises: 0073
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agendas_externas",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("url_cifrada", sa.Text(), nullable=False),
        sa.Column("eventos", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("leida_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agendas_externas")
