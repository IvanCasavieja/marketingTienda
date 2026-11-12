"""los mundos (un calendario por negocio) y las tareas asignadas de cada accion

Pedido de Ivan (12/11/2026). Dos cosas que van juntas porque las dos cambian
quien ve que en el calendario:

1. **Mundos.** Cada barra pasa a ser de un negocio (`calendario_barras.mundo`)
   y cada persona tiene la lista de los que puede abrir (`users.mundos`). Todo
   lo que ya estaba cargado es de Tienda Inglesa, que era el unico calendario.

   Quien ya podia ver el calendario queda con Tienda Inglesa: no pierde nada.
   Quien ademas administra Redexpres (`redexpres.manage`) queda tambien con el
   mundo Redexpres. Los demas mundos se dan a mano desde el panel de
   administracion; nadie los recibe solo.

2. **Tareas.** `calendario_tareas`: lo que quien lidera le asigna a cada
   persona dentro de una accion, con subtareas. El permiso nuevo
   `calendario.tareas` (crear, asignar y borrar tareas) va a Superadmin y
   Admin, igual que se hizo con los permisos de Facturacion (0035, 0037).

Revision ID: 0060
Revises: 0059
Create Date: 2026-11-12
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_PERMISO = "calendario.tareas"


def upgrade() -> None:
    op.add_column(
        "calendario_barras",
        sa.Column("mundo", sa.String(32), nullable=False, server_default="tienda_inglesa"),
    )
    op.create_index("ix_calendario_barras_mundo", "calendario_barras", ["mundo"])

    op.add_column("users", sa.Column("mundos", sa.JSON(), nullable=False, server_default="[]"))

    op.create_table(
        "calendario_tareas",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("barra_id", sa.String(64),
                  sa.ForeignKey("calendario_barras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.String(64),
                  sa.ForeignKey("calendario_tareas.id", ondelete="CASCADE"), nullable=True),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("asignado_a_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vence", sa.Date(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_por_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calendario_tareas_barra_id", "calendario_tareas", ["barra_id"])
    op.create_index("ix_calendario_tareas_parent_id", "calendario_tareas", ["parent_id"])
    op.create_index("ix_calendario_tareas_asignado_a_id", "calendario_tareas", ["asignado_a_id"])

    conn = op.get_bind()

    # Los mundos de quien ya usaba el calendario.
    for user_id, permissions in conn.execute(text("SELECT id, permissions FROM users")).fetchall():
        permisos = set(permissions or [])
        mundos = []
        if "calendario.view" in permisos:
            mundos.append("tienda_inglesa")
            if "redexpres.manage" in permisos:
                mundos.append("redexpres")
        if mundos:
            conn.execute(
                text("UPDATE users SET mundos = CAST(:m AS json) WHERE id = :id"),
                {"m": json.dumps(mundos), "id": user_id},
            )

    # El permiso de tareas, a los roles de administracion y a quienes los tienen.
    ids = [r[0] for r in conn.execute(
        text("SELECT id FROM roles WHERE name IN ('Superadmin', 'Admin')")
    ).fetchall()]
    if not ids:
        return
    for tabla, columna in (("roles", "id"), ("users", "role_id")):
        for row_id, permissions in conn.execute(
            text(f"SELECT id, permissions FROM {tabla} WHERE {columna} = ANY(:ids)"), {"ids": ids},
        ).fetchall():
            permisos = list(permissions or [])
            if _PERMISO not in permisos:
                permisos.append(_PERMISO)
                conn.execute(
                    text(f"UPDATE {tabla} SET permissions = CAST(:p AS json) WHERE id = :id"),
                    {"p": json.dumps(permisos), "id": row_id},
                )


def downgrade() -> None:
    # Las barras de los otros mundos quedan en la tabla: sin la columna, la
    # version anterior las mostraria todas juntas en el unico calendario. Si
    # se vuelve atras con otros mundos ya cargados, hay que decidir a mano que
    # se hace con ellas. Los permisos no se sacan (se pudieron tocar a mano).
    op.drop_table("calendario_tareas")
    op.drop_column("users", "mundos")
    op.drop_index("ix_calendario_barras_mundo", table_name="calendario_barras")
    op.drop_column("calendario_barras", "mundo")
