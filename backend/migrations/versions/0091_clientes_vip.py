"""Clientes VIP: el resumen por cliente y por mes, el análisis y la predicción

Ivan (25/11/2026): "vamos a hacer nosotros el dashboard, voy a pasarte un
montón de excels que vamos a ir actualizando todos los meses… un agente que
analice… prever el comportamiento futuro de los clientes VIP". El archivo de
cada mes (CSV de 2 GB, una fila por línea de ticket) no se sube: el navegador
de quien carga lo resume y sube una fila por cliente y por mes. Ver
app/services/clientes_vip.py.

- vip_cargas: cada archivo cargado (quién, cuándo, qué meses, cuántas filas).
- vip_cliente_mes: una fila por cliente y mes (~10.000 clientes × 12 meses por
  año, ~170 bytes cada una). Los montos, en pesos enteros sin IVA.
- vip_mes_dimension: los totales del mes por categoría, sucursal, canal y
  marca propia (unas 70 filas por mes).
- vip_clientes: la foto de hoy de cada cliente (segmento, riesgo, lo que se
  espera que compre el mes que viene). Se rehace con cada carga.
- vip_informes: lo que escriben Sofía (análisis) y Valentina (predicción)
  después de cada carga, y a cuántos se les mandó por mail.

Revision ID: 0091
Revises: 0090
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vip_cargas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("archivo", sa.String(255), nullable=False),
        sa.Column("meses", sa.JSON(), nullable=False),
        sa.Column("filas_archivo", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("filas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clientes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("venta", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("estado", sa.String(20), nullable=False, server_default="cargando"),
        sa.Column("subido_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("terminada_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "vip_cliente_mes",
        sa.Column("id_cliente", sa.BigInteger(), primary_key=True),
        sa.Column("mes", sa.Date(), primary_key=True),
        sa.Column("venta", sa.Integer(), nullable=False),
        sa.Column("margen", sa.Integer(), nullable=False),
        sa.Column("unidades", sa.Integer(), nullable=False),
        sa.Column("tickets", sa.Integer(), nullable=False),
        sa.Column("dias", sa.SmallInteger(), nullable=False),
        sa.Column("venta_ecommerce", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("venta_smart", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("venta_marca_propia", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sucursal", sa.String(80), nullable=True),
        sa.Column("categorias", sa.String(240), nullable=True),
        # De qué carga es la fila: al terminar una carga se borran las filas de
        # sus meses que vinieron de otra (si se corta a la mitad, el mes no
        # queda vacío: queda con lo de antes y lo nuevo que llegó).
        sa.Column("carga_id", sa.Integer(), nullable=False),
    )
    op.create_index("ix_vip_cliente_mes_mes", "vip_cliente_mes", ["mes"])
    op.create_table(
        "vip_mes_dimension",
        sa.Column("mes", sa.Date(), primary_key=True),
        sa.Column("dimension", sa.String(20), primary_key=True),
        sa.Column("valor", sa.String(120), primary_key=True),
        sa.Column("venta", sa.BigInteger(), nullable=False),
        sa.Column("margen", sa.BigInteger(), nullable=False),
        sa.Column("unidades", sa.BigInteger(), nullable=False),
        sa.Column("tickets", sa.Integer(), nullable=False),
        sa.Column("clientes", sa.Integer(), nullable=False),
    )
    op.create_table(
        "vip_clientes",
        sa.Column("id_cliente", sa.BigInteger(), primary_key=True),
        sa.Column("segmento", sa.String(20), nullable=False),
        sa.Column("riesgo", sa.SmallInteger(), nullable=False),
        sa.Column("venta_esperada", sa.Integer(), nullable=False),
        sa.Column("venta_12m", sa.BigInteger(), nullable=False),
        sa.Column("venta_3m", sa.Integer(), nullable=False),
        sa.Column("venta_3m_antes", sa.Integer(), nullable=False),
        sa.Column("margen_12m", sa.BigInteger(), nullable=False),
        sa.Column("tickets_12m", sa.Integer(), nullable=False),
        sa.Column("meses_con_compra", sa.SmallInteger(), nullable=False),
        sa.Column("ultimo_mes", sa.Date(), nullable=True),
        sa.Column("sucursal", sa.String(80), nullable=True),
        sa.Column("categoria", sa.String(120), nullable=True),
        sa.Column("parte_ecommerce", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.create_index("ix_vip_clientes_segmento", "vip_clientes", ["segmento"])
    op.create_table(
        "vip_informes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("carga_id", sa.Integer(), sa.ForeignKey("vip_cargas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mes", sa.Date(), nullable=False),
        sa.Column("analisis", sa.Text(), nullable=False),
        sa.Column("prediccion", sa.JSON(), nullable=False),
        sa.Column("con_ia", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("enviado_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("vip_informes")
    op.drop_index("ix_vip_clientes_segmento", table_name="vip_clientes")
    op.drop_table("vip_clientes")
    op.drop_table("vip_mes_dimension")
    op.drop_index("ix_vip_cliente_mes_mes", table_name="vip_cliente_mes")
    op.drop_table("vip_cliente_mes")
    op.drop_table("vip_cargas")
