"""create redexpress tables

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-03

"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planilla_pedidos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("local_nombre", sa.String(200), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("a4_oferta_vertical", sa.Integer(), nullable=True),
        sa.Column("cenefa_oferta_x3", sa.Integer(), nullable=True),
        sa.Column("pinchos", sa.Integer(), nullable=True),
        sa.Column("afiche_54x74", sa.Integer(), nullable=True),
        sa.Column("cenefa_valle_del_sol", sa.Integer(), nullable=True),
        sa.Column("cenefa_supremo_hogar", sa.Integer(), nullable=True),
        sa.Column("bombas_3xa4", sa.Integer(), nullable=True),
        sa.Column("bombas_a4", sa.Integer(), nullable=True),
        sa.Column("bombas_74x54", sa.Integer(), nullable=True),
        sa.Column("pinchos_bombas", sa.Integer(), nullable=True),
        sa.Column("sticker_valle_del_sol", sa.Integer(), nullable=True),
        sa.Column("sticker_carne", sa.Integer(), nullable=True),
        sa.Column("cenefas_preciazos", sa.Integer(), nullable=True),
        sa.Column("afiche_super_ahorro", sa.Integer(), nullable=True),
        sa.Column("pinchos_dias_expres", sa.Integer(), nullable=True),
        sa.Column("hojas_amarillas", sa.String(50), nullable=True),
        sa.Column("otros", sa.Text(), nullable=True),
        sa.Column("confirmado", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("local_nombre", "year", "month", name="uq_planilla_local_periodo"),
    )

    op.create_table(
        "local_asignaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_nombre", sa.String(200), nullable=False),
        sa.UniqueConstraint("user_id", "local_nombre", name="uq_local_asignacion"),
    )

    op.create_index("ix_planilla_year_month", "planilla_pedidos", ["year", "month"])
    op.create_index("ix_local_asig_user", "local_asignaciones", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_local_asig_user", "local_asignaciones")
    op.drop_index("ix_planilla_year_month", "planilla_pedidos")
    op.drop_table("local_asignaciones")
    op.drop_table("planilla_pedidos")
