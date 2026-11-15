"""indice de las notificaciones por su origen

Revision ID: 0061
Revises: 0060
Create Date: 2026-11-15

El loop de los recordatorios del calendario y cada cambio de fecha de una
accion buscan las notificaciones ya mandadas por (origen_tipo, origen_ref)
(`app/services/calendario_avisos.py`). Sin indice eso recorre la tabla entera,
y lo hace adentro del candado del calendario: con 300.000 filas, 35 ms contra
0,12 ms con el indice (medido el 15/11/2026). La tabla solo crece.
"""
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_notificaciones_origen", "notificaciones", ["origen_tipo", "origen_ref"],
    )


def downgrade() -> None:
    op.drop_index("ix_notificaciones_origen", table_name="notificaciones")
