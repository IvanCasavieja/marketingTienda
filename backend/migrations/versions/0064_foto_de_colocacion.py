"""la foto de colocación: los locales muestran cómo quedó la cartelería

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-15

Desde la ficha de una acción, promo le pide una foto a los locales; cada local
la sube desde el teléfono y promo la aprueba o la devuelve. Tres tablas nuevas
(ver app/models/colocacion.py). No toca nada de lo que ya existe.

Las fotos van en una tabla propia con los bytes adentro (bytea), igual que los
archivos de cenefas, y se purgan solas 120 días después de que termina la
acción (services/colocacion.py, donde está también la cuenta de cuánto ocupan).
"""
from alembic import op
import sqlalchemy as sa

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "colocacion_pedidos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "barra_id", sa.String(64),
            sa.ForeignKey("calendario_barras.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("tipo_local", sa.String(20), nullable=False),
        sa.Column("limite", sa.Date(), nullable=False),
        sa.Column("indicacion", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("aviso_completo_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Una acción, un pedido: el índice único es además el que usa /datos para
    # juntar el resumen de cada acción.
    op.create_index("ix_colocacion_pedidos_barra_id", "colocacion_pedidos", ["barra_id"], unique=True)

    op.create_table(
        "colocacion_locales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pedido_id", sa.Integer(),
            sa.ForeignKey("colocacion_pedidos.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("local_nombre", sa.String(200), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("enviada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revisado_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revisado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("pedido_id", "local_nombre", name="uq_colocacion_local"),
    )
    op.create_index("ix_colocacion_locales_pedido_id", "colocacion_locales", ["pedido_id"])
    # "Lo que tiene que subir este local" busca por nombre.
    op.create_index("ix_colocacion_locales_local_nombre", "colocacion_locales", ["local_nombre"])

    op.create_table(
        "colocacion_fotos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "local_id", sa.Integer(),
            sa.ForeignKey("colocacion_locales.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("subida_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("tipo_miniatura", sa.String(20), nullable=False),
        sa.Column("ancho", sa.Integer(), nullable=False),
        sa.Column("alto", sa.Integer(), nullable=False),
        sa.Column("peso", sa.Integer(), nullable=False),
        sa.Column("devuelta", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("datos", sa.LargeBinary(), nullable=False),
        sa.Column("miniatura", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_colocacion_fotos_local_id", "colocacion_fotos", ["local_id"])


def downgrade() -> None:
    op.drop_index("ix_colocacion_fotos_local_id", table_name="colocacion_fotos")
    op.drop_table("colocacion_fotos")
    op.drop_index("ix_colocacion_locales_local_nombre", table_name="colocacion_locales")
    op.drop_index("ix_colocacion_locales_pedido_id", table_name="colocacion_locales")
    op.drop_table("colocacion_locales")
    op.drop_index("ix_colocacion_pedidos_barra_id", table_name="colocacion_pedidos")
    op.drop_table("colocacion_pedidos")
