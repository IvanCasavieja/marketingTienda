"""plantillas de tareas por tipo de acción, y tareas que se mueven con su acción

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-15

Cada acción de un mismo tipo lleva casi siempre las mismas tareas: el brief a
la agencia, las entregas, la aprobación final, las cenefas a los locales, la
foto de colocación y el retiro de lo que se colgó. Hasta acá se cargaban a mano
en cada acción.

1. `calendario_plantillas`: las plantillas de cada mundo. Una plantilla tiene
   nombre, opcionalmente la categoría de acción a la que va (la `banda`: "MEGA
   EVENTO"...) y la lista de tareas, cada una con su vencimiento relativo: N
   días antes o después del inicio o del fin de la acción.

2. En `calendario_tareas`, de dónde sale el vencimiento de una tarea que vino
   de una plantilla (`ancla` = 'inicio' | 'fin' y `ancla_dias`) y de qué
   plantilla vino (`plantilla_id`). Con el ancla, si la acción se mueve de
   fecha, sus tareas no hechas se mueven solas. Si alguien cambia a mano el
   vencimiento, el ancla se borra y la fecha queda donde la puso.

No se siembra ninguna plantilla: las arma cada equipo (la pantalla ofrece
"Empezar con un ejemplo").
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendario_plantillas",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("mundo", sa.String(32), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=True),
        sa.Column("tareas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("creado_por_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actualizado_por_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calendario_plantillas_mundo", "calendario_plantillas", ["mundo"])

    op.add_column("calendario_tareas", sa.Column("ancla", sa.String(8), nullable=True))
    op.add_column("calendario_tareas", sa.Column("ancla_dias", sa.Integer(), nullable=True))
    op.add_column("calendario_tareas", sa.Column("plantilla_id", sa.String(64), nullable=True))


def downgrade() -> None:
    # Las tareas que vinieron de una plantilla se quedan, con la fecha que
    # tenían: solo dejan de moverse con su acción.
    op.drop_column("calendario_tareas", "plantilla_id")
    op.drop_column("calendario_tareas", "ancla_dias")
    op.drop_column("calendario_tareas", "ancla")
    op.drop_index("ix_calendario_plantillas_mundo", table_name="calendario_plantillas")
    op.drop_table("calendario_plantillas")
