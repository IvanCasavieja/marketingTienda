"""valores fijos en las plantillas de mapeo del Convertidor

Cada variable mapeable pasa a admitir dos formas de resolverse: mapear una
columna del Excel de gestion, o escribir un valor fijo que se aplica a todas
las filas. La segunda hacia falta porque hay variables que el export de
gestion NO trae nunca -- vigencia y legales las escribe una persona, no salen
de ninguna columna.

`mapeo` sigue siendo {variable: nombre_de_columna} y `valores` es
{variable: texto_fijo}. Son excluyentes por variable: la pantalla deja elegir
una u otra, y si por lo que sea llegaran las dos, gana el valor fijo (es lo
que la persona escribio explicitamente para esta corrida).

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-23

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "convertidor_mapeos",
        sa.Column("valores", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("convertidor_mapeos", "valores")
