"""tablero de la agencia (estilo Trello) y alcance del calendario por usuario

Revision ID: 0070
Revises: 0069
Create Date: 2026-11-16

Pedido de Ivan (16/11/2026): "La agencia tiene que tener otro tipo de entrada,
otra vista. Lo único que le interesa es tener las tareas de cada promoción
para irlas completando y mandando. Una vista estilo Trello": Ingresado, En
proceso, Esperando feedback, Finalizado y Archivado.

- `calendario_tareas.para` y `.agencia`: quién la hace. 'agencia' = una
  agencia que usa la plataforma (`agencia` es el nombre de su empresa, como
  `users.empresa`); 'fuera' = una agencia que NO usa la plataforma (`agencia`
  es su nombre, y quien carga sus entregas es la persona del equipo asignada);
  'tienda' = la gente de Tienda Inglesa. Las tareas que ya estaban asignadas a
  una cuenta externa pasan a ser "para la agencia" de su empresa: es lo que
  eran.
- `calendario_tareas.tipo`, `.opciones` y `.detalles`: el tipo de tarea
  (Banners, Mailing, Cenefas...), lo que se tildó ("Header, Slider") y los
  datos de más (el CTA, los bloques). El catálogo, con las medidas que mandó
  Ivan, está en app/services/tipos_de_tarea.py. Una tarea con tipo es una pieza: le
  nace su tarjeta en el tablero, con el nombre "<Acción> - <Tipo>".
- `calendario_entregas`: las fechas que el momento de la entrega no dice y
  el tablero necesita (cuándo se arrancó, cuándo se finalizó, cuándo se
  archivó y quién, cuándo se desarchivó). `iniciada_at` y `finalizada_at` se
  completan con lo que ya hay: la primera versión entregada y la última vez
  que se tocó una aprobada.
- `users.calendario_alcance`: hasta dónde ve el calendario cada persona
  ('nada', '1m', '2m', '12m', 'todo'; ver app/core/alcance.py). Las cuentas
  externas quedan en 'nada' ("en un inicio la agencia no va a tener acceso a
  ver el calendario"); las del equipo, en 'todo' (no les cambia nada).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Para quién es la tarea ------------------------------------------------
    op.add_column(
        "calendario_tareas",
        sa.Column("para", sa.String(length=8), nullable=False, server_default="tienda"),
    )
    op.add_column("calendario_tareas", sa.Column("agencia", sa.String(length=120), nullable=True))
    # Lo que ya estaba asignado a una cuenta externa era, de hecho, para su
    # agencia. La empresa ya está limpia (admin.py la guarda con limpiar_empresa).
    op.execute(
        "UPDATE calendario_tareas t SET para = 'agencia', agencia = u.empresa "
        "FROM users u WHERE u.id = t.asignado_a_id AND u.es_externo "
        "AND u.empresa IS NOT NULL AND length(btrim(u.empresa)) > 0"
    )
    op.create_check_constraint(
        "ck_calendario_tareas_para", "calendario_tareas", "para IN ('tienda', 'agencia', 'fuera')",
    )
    # Una agencia (de la plataforma o de afuera) lleva siempre cuál; Tienda, ninguna.
    op.create_check_constraint(
        "ck_calendario_tareas_agencia", "calendario_tareas",
        "(para = 'tienda' AND agencia IS NULL) "
        "OR (para IN ('agencia', 'fuera') AND agencia IS NOT NULL AND length(btrim(agencia)) > 0)",
    )
    op.add_column("calendario_tareas", sa.Column("tipo", sa.String(length=20), nullable=True))
    op.add_column("calendario_tareas", sa.Column("opciones", JSONB(), nullable=True))
    op.add_column("calendario_tareas", sa.Column("detalles", JSONB(), nullable=True))
    # El tablero de una agencia busca sus tarjetas por el nombre de la empresa
    # sin mayúsculas: un índice solo sobre las que son para una agencia.
    op.create_index(
        "ix_calendario_tareas_agencia", "calendario_tareas", [sa.text("lower(agencia)")],
        postgresql_where=sa.text("para = 'agencia'"),
    )

    # --- Las fechas del tablero ------------------------------------------------
    op.add_column("calendario_entregas", sa.Column("iniciada_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calendario_entregas", sa.Column("finalizada_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calendario_entregas", sa.Column("archivada_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "calendario_entregas",
        sa.Column("archivada_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("calendario_entregas", sa.Column("desarchivada_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE calendario_entregas e SET iniciada_at = v.primera "
        "FROM (SELECT tarea_id, min(created_at) AS primera FROM calendario_versiones GROUP BY tarea_id) v "
        "WHERE v.tarea_id = e.tarea_id"
    )
    op.execute(
        "UPDATE calendario_entregas SET finalizada_at = coalesce(updated_at, created_at) "
        "WHERE momento = 'aprobada'"
    )
    # El tablero tiene que andar rápido aunque haya miles de tarjetas viejas
    # (lo que más molesta del Trello de hoy): busca las activas por el momento
    # y, de las aprobadas, solo las finalizadas o archivadas hace poco. Las
    # viejas quedan en la base pero ni se leen.
    op.create_index("ix_calendario_entregas_momento", "calendario_entregas", ["momento"])
    op.create_index(
        "ix_calendario_entregas_aprobadas", "calendario_entregas", ["finalizada_at", "archivada_at"],
        postgresql_where=sa.text("momento = 'aprobada'"),
    )

    # --- Hasta dónde ve el calendario cada persona -------------------------------
    op.add_column(
        "users",
        sa.Column("calendario_alcance", sa.String(length=8), nullable=False, server_default="todo"),
    )
    op.execute("UPDATE users SET calendario_alcance = 'nada' WHERE es_externo")
    op.create_check_constraint(
        "ck_users_calendario_alcance", "users", "calendario_alcance IN ('nada', '1m', '2m', '12m', 'todo')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_calendario_alcance", "users", type_="check")
    op.drop_column("users", "calendario_alcance")
    op.drop_index("ix_calendario_entregas_aprobadas", table_name="calendario_entregas")
    op.drop_index("ix_calendario_entregas_momento", table_name="calendario_entregas")
    op.drop_column("calendario_entregas", "desarchivada_at")
    op.drop_column("calendario_entregas", "archivada_por_id")
    op.drop_column("calendario_entregas", "archivada_at")
    op.drop_column("calendario_entregas", "finalizada_at")
    op.drop_column("calendario_entregas", "iniciada_at")
    op.drop_index("ix_calendario_tareas_agencia", table_name="calendario_tareas")
    op.drop_constraint("ck_calendario_tareas_agencia", "calendario_tareas", type_="check")
    op.drop_constraint("ck_calendario_tareas_para", "calendario_tareas", type_="check")
    op.drop_column("calendario_tareas", "detalles")
    op.drop_column("calendario_tareas", "opciones")
    op.drop_column("calendario_tareas", "tipo")
    op.drop_column("calendario_tareas", "agencia")
    op.drop_column("calendario_tareas", "para")
