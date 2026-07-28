"""create convertidor_header_aliases table

Cache de headers de columna de Excel que Tinín clasificó vía IA como
fecha_inicio/fecha_fin (o confirmó que NO son de vigencia -- field_name NULL)
cuando no matcheaban ningún alias hardcodeado en _INPUT_ALIASES (ver
convertidor.py / convertidor_ai.py) — el mismo header normalizado nunca
vuelve a pasar por IA una segunda vez, ni para un match positivo ni negativo.

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "convertidor_header_aliases",
        sa.Column("header_norm", sa.String(120), primary_key=True),
        sa.Column("field_name", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("convertidor_header_aliases")
