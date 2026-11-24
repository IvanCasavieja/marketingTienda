"""los archivos del pedido de una tarea

Ivan (24/11/2026): "en el brief de las tareas deberíamos poder adjuntar
archivos, como el Excel por ejemplo". Una tabla nueva, `calendario_adjuntos`:
cada archivo con su tarea, su nombre, su tipo, lo que pesa y los bytes. Se
va con la tarea (CASCADE). Los topes están en app/services/adjuntos.py y en
ADJUNTOS_TOPE_MB (app/core/config.py). Ver app/models/adjuntos.py.

Es la 0089 y sale de la 0087: la 0088 la tiene la rama feat/nombre-con-tarea,
que todavía no entró a main. Si entra antes, acá va down_revision = "0088".

Revision ID: 0089
Revises: 0087
Create Date: 2026-11-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0089"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendario_adjuntos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tarea_id", sa.String(64), sa.ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("tipo_mime", sa.String(100), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False),
        sa.Column("datos", sa.LargeBinary(), nullable=False),
        sa.Column("subido_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_calendario_adjuntos_tarea_id", "calendario_adjuntos", ["tarea_id"])


def downgrade() -> None:
    op.drop_index("ix_calendario_adjuntos_tarea_id", table_name="calendario_adjuntos")
    op.drop_table("calendario_adjuntos")
