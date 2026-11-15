"""la revisión del calendario, también por mundo

Revision ID: 0063
Revises: 0062
Create Date: 2026-11-15

El calendario pregunta cada 15 s "¿hubo cambios desde la revisión N?". La
revisión era una sola para todos los mundos: un cambio en Redexpres hacía que
quien miraba Tienda Inglesa se volviera a bajar su calendario entero (~900 KB
sin comprimir), que no había cambiado.

Ahora cada mundo anota la última revisión que lo tocó. El contador sigue
siendo uno solo (los números no se repiten entre mundos y el front sigue
comparando igual); /datos contesta "sin cambios" si nada de ESE mundo cambió
después de la revisión que tiene el front.

Arranca con la revisión actual en todos los mundos: una pestaña abierta con la
revisión de hoy sigue "sin cambios", sin bajarse nada de más.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

# Copia de app.core.mundos.MUNDOS al día de hoy (una migración no importa la app).
_MUNDOS = ("tienda_inglesa", "tienda_express", "redexpres", "tienda_viajes", "tienda_farma")


def upgrade() -> None:
    op.create_table(
        "calendario_revision_mundo",
        sa.Column("mundo", sa.String(32), primary_key=True),
        sa.Column("rev", sa.BigInteger(), nullable=False),
    )
    op.get_bind().execute(
        text(
            """
            INSERT INTO calendario_revision_mundo (mundo, rev)
            SELECT m, COALESCE((SELECT rev FROM calendario_revision WHERE id = 1), 0)
              FROM unnest(CAST(:mundos AS text[])) AS m
            """
        ),
        {"mundos": list(_MUNDOS)},
    )


def downgrade() -> None:
    op.drop_table("calendario_revision_mundo")
