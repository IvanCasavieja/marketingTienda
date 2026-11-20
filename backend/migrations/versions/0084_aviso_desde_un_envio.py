"""un aviso se puede contar desde la fecha de un envío

Ivan (20/11/2026): "que un aviso se pueda programar según la fecha de un
envío, no solo según el arranque de la acción".

`calendario_avisos.pieza_id`: la pieza de envío (email, WhatsApp, push) desde
cuya fecha se cuentan los días. Vacía, como todos los avisos que ya existen,
se cuentan desde que arranca la acción: nada cambia para ellos. Si se saca la
pieza, el aviso se va con ella.

Revision ID: 0084
Revises: 0083
Create Date: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendario_avisos", sa.Column("pieza_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        "calendario_avisos_pieza_id_fkey", "calendario_avisos", "calendario_piezas",
        ["pieza_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_calendario_avisos_pieza_id", "calendario_avisos", ["pieza_id"])


def downgrade() -> None:
    # Los avisos de un envío vuelven a contarse desde el inicio de la acción.
    op.drop_index("ix_calendario_avisos_pieza_id", table_name="calendario_avisos")
    op.drop_constraint("calendario_avisos_pieza_id_fkey", "calendario_avisos", type_="foreignkey")
    op.drop_column("calendario_avisos", "pieza_id")
