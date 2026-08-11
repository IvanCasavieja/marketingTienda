"""create facturacion tables (documentos, movimientos, canjes)

Nuevo módulo Facturación: presupuesto (cuenta única de la empresa) y canjes
con marcas/proveedores, cargados subiendo un PDF de factura que DogTi lee
con IA -- ver backend/app/services/facturacion/. facturacion_documentos
guarda el PDF entero (no hay storage tipo S3 en este repo) y el estado de
revisión; facturacion_movimientos/facturacion_canjes son las filas que
resultan de confirmar esa revisión.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facturacion_documentos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="application/pdf"),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendiente_revision"),
        sa.Column("extraction_raw", postgresql.JSONB(), nullable=True),
        sa.Column("extraction_error", sa.String(500), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "facturacion_movimientos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        sa.Column("moneda", sa.String(10), nullable=False, server_default="UYU"),
        sa.Column("concepto", sa.String(300), nullable=False),
        sa.Column("proveedor_marca", sa.String(200), nullable=True),
        sa.Column("numero_factura", sa.String(100), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column(
            "documento_id", sa.Integer(),
            sa.ForeignKey("facturacion_documentos.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.UniqueConstraint("documento_id", name="uq_facturacion_movimientos_documento_id"),
    )

    op.create_table(
        "facturacion_canjes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("marca_proveedor", sa.String(200), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("moneda", sa.String(10), nullable=False, server_default="UYU"),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("vigencia_desde", sa.Date(), nullable=True),
        sa.Column("vigencia_hasta", sa.Date(), nullable=True),
        sa.Column("descripcion", sa.String(500), nullable=True),
        sa.Column(
            "documento_id", sa.Integer(),
            sa.ForeignKey("facturacion_documentos.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.UniqueConstraint("documento_id", name="uq_facturacion_canjes_documento_id"),
    )


def downgrade() -> None:
    op.drop_table("facturacion_canjes")
    op.drop_table("facturacion_movimientos")
    op.drop_table("facturacion_documentos")
