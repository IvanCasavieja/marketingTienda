"""plantillas de mapeo del convertidor

Las variables cuyo nombre de columna cambia segun el archivo de gestion que
se suba (ofertaUno..Cuatro, vigencia, aclaracionUno..Tres, legales) no se
pueden resolver por codigo: las elige la persona en la pantalla de mapeo.
Esta tabla guarda esa eleccion para no reconfigurarla en cada import.

Compartida por todo el equipo (sin scoping por usuario): el archivo de una
campana es el mismo para todos, y que cada persona lo reconfigure por su
cuenta es el trabajo repetido que esto viene a eliminar.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-23

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "convertidor_mapeos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("destino", sa.String(50), nullable=True),
        sa.Column("mapeo", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # El picker filtra por destino en cada apertura de la pantalla de mapeo.
    op.create_index("ix_convertidor_mapeos_destino", "convertidor_mapeos", ["destino"])


def downgrade() -> None:
    op.drop_index("ix_convertidor_mapeos_destino", table_name="convertidor_mapeos")
    op.drop_table("convertidor_mapeos")
