"""cuenta recomendada por proveedor recurrente

La recurrencia 2026 (Gastos 2026.xlsx, enero-agosto) muestra que 66 de 115
proveedores facturaron siempre a la misma cuenta de marketing. Esta tabla
guarda ese mapeo proveedor -> cuenta para que, al subir un PDF, la cuenta
venga preseleccionada y alcance con aprobar: es la version deterministica
de la cuenta_sugerida que hoy adivina DogTi leyendo el PDF.

El nombre del proveedor se guarda NORMALIZADO (mayusculas, sin tildes ni
puntuacion, espacios colapsados) porque viene de sistemas distintos y
"CREATIVAS S A" y "CREATIVAS S.A" son el mismo proveedor.

Revision ID: 0051
Revises: 0050
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "facturacion_proveedor_cuenta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("proveedor", sa.String(length=200), nullable=False),
        sa.Column(
            "cuenta_id",
            sa.Integer(),
            sa.ForeignKey("facturacion_cuentas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("facturas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("origen", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("proveedor", name="uq_facturacion_proveedor_cuenta_proveedor"),
    )


def downgrade():
    op.drop_table("facturacion_proveedor_cuenta")
