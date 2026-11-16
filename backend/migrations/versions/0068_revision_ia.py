"""la IA revisa la pieza antes que el aprobador

Revision ID: 0068
Revises: 0067
Create Date: 2026-11-16

Pedido de Ivan (idea 5, 16/11/2026): "IA que revisa la pieza antes que vos:
ortografía, logo de otro mundo, falta del legal, QR roto". Una fila por
versión entregada con lo que encontró la IA. Por qué es así, en
app/models/revision_ia.py; la lógica, en app/services/revision_ia.py.

Cuelga de `calendario_versiones` con ON DELETE CASCADE: se va con la versión
(y con la tarea o la acción). Es chica: unos cientos de bytes por versión, sin
imágenes (las imágenes siguen siendo las de la versión).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendario_revisiones_ia",
        sa.Column(
            "version_id", sa.String(64), sa.ForeignKey("calendario_versiones.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("motivo", sa.String(300), nullable=True),
        sa.Column("modelo", sa.String(100), nullable=True),
        sa.Column("observaciones", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("costo_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("terminada_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calendario_revisiones_ia_created", "calendario_revisiones_ia", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_calendario_revisiones_ia_created", table_name="calendario_revisiones_ia")
    op.drop_table("calendario_revisiones_ia")
