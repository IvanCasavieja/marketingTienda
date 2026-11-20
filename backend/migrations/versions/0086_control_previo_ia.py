"""el control de la IA antes de entregar

Ivan (20/11/2026): "que a la agencia, cuando va a subir los archivos, la IA le
diga 'che, pará, acá faltan estas cositas de los cambios' (...) que detecte al
momento de subir si se hicieron los cambios pedidos". Eligió que sea ANTES de
mandar y que a la agencia se le muestren solo los cambios pedidos.

`calendario_controles_previos`: una fila por control, con la revisión entera
(observaciones y cambios pedidos), la huella de las imágenes y lo que costó.
Si la agencia entrega exactamente esas imágenes, la revisión de la versión
sale de acá (`usado_en_version_id`) y no se le paga dos veces a la IA. Ver
app/services/revision_ia.py (controlar_antes_de_entregar).

Revision ID: 0086
Revises: 0085
Create Date: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendario_controles_previos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tarea_id", sa.String(64), sa.ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fase_id", sa.String(64), sa.ForeignKey("calendario_fases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ronda", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("motivo", sa.String(300), nullable=True),
        sa.Column("modelo", sa.String(100), nullable=True),
        sa.Column("observaciones", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cambios_pedidos", postgresql.JSONB(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("costo_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("usado_en_version_id", sa.String(64),
                  sa.ForeignKey("calendario_versiones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("terminado_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calendario_controles_previos_tarea", "calendario_controles_previos", ["tarea_id", "created_at"])
    op.create_index("ix_calendario_controles_previos_created", "calendario_controles_previos", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_calendario_controles_previos_created", table_name="calendario_controles_previos")
    op.drop_index("ix_calendario_controles_previos_tarea", table_name="calendario_controles_previos")
    op.drop_table("calendario_controles_previos")
