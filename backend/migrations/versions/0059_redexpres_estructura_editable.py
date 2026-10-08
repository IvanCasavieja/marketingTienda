"""planilla de pedidos editable: estructura por mes y valores de columnas nuevas

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-08

Ivan, 08/10/2026: Valentina o Lucía tienen que poder armar cada mes la planilla
que completan las sucursales (agregar o sacar grupos y columnas, cambiar los
topes), como en un Excel. Hasta hoy las columnas eran campos fijos de la tabla.

- redexpres_estructuras: la estructura (grupos y columnas con su tope) de cada
  mes. Si un mes no tiene fila, rige la estructura por defecto del código.
- planilla_pedidos.extras: los valores de las columnas que NO son de las 17
  históricas, por clave. Nunca se borra un valor: sacar una columna de la
  estructura solo deja de mostrarla.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planilla_pedidos",
        sa.Column("extras", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "redexpres_estructuras",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("estructura", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("year", "month", name="uq_redexpres_estructura_periodo"),
    )


def downgrade() -> None:
    op.drop_table("redexpres_estructuras")
    op.drop_column("planilla_pedidos", "extras")
