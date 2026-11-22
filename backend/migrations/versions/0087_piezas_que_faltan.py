"""las piezas del pedido que faltan en una entrega, y por qué

Ivan (21/11/2026): "la IA a veces encuentra un problema y a veces no. Si yo
pido 4 banners y me pasan uno, puede ser que lo primero que estén haciendo
sea pasarme un KV para que yo apruebe, pero cuando son todos los banners ahí
es donde tiene que analizar y decir 'che, pará, acá faltan también los
banners X o Y'. Y quizás estaría bueno que le des el espacio a la agencia
ahí de escribir por qué no los manda."

Que falte una pieza ahora lo dice la plataforma sola, por las medidas de lo
que se entrega (frontend/lib/calendario/piezas.ts, con las piezas de
app/services/tipos_de_tarea.py: piezas_del_pedido). Si quien entrega manda
igual, viajan con la ronda:

- `faltan`: la lista de nombres de las piezas que no venían ("Header
  (mobile)", "Checkout"). NULL si no faltaba nada (y en las rondas de antes).
- `por_que_faltan`: lo que escribió en «¿Por qué no va todo?» ("Es el KV,
  para aprobarlo antes"). Opcional.

Lo ven quien aprueba y la agencia, en la ficha de esa ronda y arriba al
revisarla. Dos columnas que aceptan NULL: no hay nada que llenar en las
filas que ya están.

Revision ID: 0087
Revises: 0086
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendario_versiones", sa.Column("faltan", postgresql.JSONB(), nullable=True))
    op.add_column("calendario_versiones", sa.Column("por_que_faltan", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendario_versiones", "por_que_faltan")
    op.drop_column("calendario_versiones", "faltan")
