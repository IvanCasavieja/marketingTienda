"""create facturacion_cuentas + cuenta_id en movimientos/canjes

"Cuenta" es la dimensión de a qué cuenta interna ingresa un gasto/canje
(varias razones sociales/locales manejan su propio presupuesto). No se
pre-siembra ninguna cuenta acá -- el panel de administración de Facturación
las crea/edita/desactiva desde la app (ver facturacion_cuentas_service.py).

"Eliminar" una cuenta desde ese panel nunca hace un DELETE real -- solo
marca activa=False (ver FacturacionCuenta) -- así que ondelete=RESTRICT acá
es una red de seguridad extra, no el mecanismo principal de protección.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facturacion_cuentas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.UniqueConstraint("nombre", name="uq_facturacion_cuentas_nombre"),
    )

    op.add_column(
        "facturacion_movimientos",
        sa.Column(
            "cuenta_id", sa.Integer(),
            sa.ForeignKey("facturacion_cuentas.id", ondelete="RESTRICT"), nullable=True,
        ),
    )
    op.add_column(
        "facturacion_canjes",
        sa.Column(
            "cuenta_id", sa.Integer(),
            sa.ForeignKey("facturacion_cuentas.id", ondelete="RESTRICT"), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("facturacion_canjes", "cuenta_id")
    op.drop_column("facturacion_movimientos", "cuenta_id")
    op.drop_table("facturacion_cuentas")
