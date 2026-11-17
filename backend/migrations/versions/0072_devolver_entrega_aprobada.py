"""devolver una entrega ya aprobada: abre otra fase con lo que hay que cambiar

Pedido de Ivan (17/11/2026): despues de aprobada la pieza "no aparece algo
para evaluar, un cuadro de texto o algo donde poder escribir algo para que
podamos volver para atras el arte". Y: "no podes tener un limite en las fases
de entrega, la idea seria que eso sea infinito, podes ir aumentando el
contador fase 1, fase 2, fase 3...".

Hasta hoy, con la unica fase aprobada la tarjeta quedaba cerrada: nadie podia
entregar de nuevo ni pedir cambios. Ahora quien la aprueba (o quien lidera)
la puede devolver con un texto, y eso abre una fase nueva al final ("Entrega
2", "Entrega 3"...). La fase guarda ese texto y quien lo pidio, para que
quien entrega lo vea arriba de todo.

Revision ID: 0072
Revises: 0071
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendario_fases", sa.Column("motivo", sa.Text(), nullable=True))
    op.add_column(
        "calendario_fases",
        sa.Column("abierta_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calendario_fases", "abierta_por_id")
    op.drop_column("calendario_fases", "motivo")
