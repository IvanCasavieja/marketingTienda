"""los mundos (la plataforma entera, separada por negocio) y las tareas asignadas de cada accion

Pedido de Ivan (12/11/2026). Dos cosas que van juntas porque las dos cambian
quien ve que:

1. **Mundos.** "Los mundos tienen que ser de toda la plataforma. La persona que
   entra a ese mundo va a ver todo hecho para ese mundo". Cada persona tiene la
   lista de los mundos a los que entra (`users.mundos`), y lo que se guarda por
   negocio dice de cual es:

   - `calendario_barras.mundo`: todo lo cargado es de Tienda Inglesa, que era
     el unico calendario.
   - `cenefa_destinos.mundo`: el destino `redexpres` pasa al mundo Redexpres y
     los demas (Rompe Precios, Parrilla y Vinos, Pruebas...) quedan en Tienda
     Inglesa. El selector de cenefas ya no los mezcla.

   **Nadie pierde nada de lo que usaba** (la misma regla que
   `app/core/mundos.py::mundos_iniciales`, copiada aca para que la migracion no
   cambie si un dia cambia la regla):

   - un login de sucursal de Redexpres queda solo en Redexpres;
   - quien tiene algun permiso de Redexpres queda en Redexpres, porque la
     planilla de pedidos pasa a verse solo ahi;
   - todos los demas quedan en Tienda Inglesa, que es donde estaba todo.

   Tienda Express, Tienda Viajes y Tienda Farma no se le dan a nadie solos: se
   tildan a mano desde el panel de administracion.

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


def _mundos_iniciales(permissions, es_sucursal_de_redexpres: bool) -> list[str]:
    if es_sucursal_de_redexpres:
        return ["redexpres"]
    permisos = set(permissions or [])
    de_redexpres = {p for p in permisos if p.startswith("redexpres.")}
    mundos = []
    if not permisos or permisos - de_redexpres:
        mundos.append("tienda_inglesa")
    if de_redexpres:
        mundos.append("redexpres")
    return mundos


def upgrade() -> None:
    op.add_column(
        "calendario_barras",
        sa.Column("mundo", sa.String(32), nullable=False, server_default="tienda_inglesa"),
    )
    op.create_index("ix_calendario_barras_mundo", "calendario_barras", ["mundo"])

    op.add_column(
        "cenefa_destinos",
        sa.Column("mundo", sa.String(32), nullable=False, server_default="tienda_inglesa"),
    )
    op.create_index("ix_cenefa_destinos_mundo", "cenefa_destinos", ["mundo"])
    op.execute("UPDATE cenefa_destinos SET mundo = 'redexpres' WHERE slug = 'redexpres'")

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

    # El permiso de tareas, a los roles de administracion y a quienes los
    # tienen. Va ANTES de repartir los mundos: no cambia a que mundo entra
    # nadie (no es un permiso de Redexpres), pero asi los permisos que se leen
    # abajo ya son los definitivos.
    ids = [r[0] for r in conn.execute(
        text("SELECT id FROM roles WHERE name IN ('Superadmin', 'Admin')")
    ).fetchall()]
    if ids:
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

    # A que mundos entra cada persona que ya estaba. TODOS quedan con al menos
    # uno: sin mundo no se puede entrar a la plataforma.
    sucursales_de_redexpres = {
        r[0] for r in conn.execute(
            text("SELECT DISTINCT user_id FROM local_asignaciones WHERE tipo = 'redex'")
        ).fetchall()
    }
    for user_id, permissions in conn.execute(text("SELECT id, permissions FROM users")).fetchall():
        mundos = _mundos_iniciales(permissions, user_id in sucursales_de_redexpres)
        conn.execute(
            text("UPDATE users SET mundos = CAST(:m AS json) WHERE id = :id"),
            {"m": json.dumps(mundos), "id": user_id},
        )


def downgrade() -> None:
    # Las barras de los otros mundos quedan en la tabla: sin la columna, la
    # version anterior las mostraria todas juntas en el unico calendario. Si
    # se vuelve atras con otros mundos ya cargados, hay que decidir a mano que
    # se hace con ellas. Los permisos no se sacan (se pudieron tocar a mano).
    op.drop_table("calendario_tareas")
    op.drop_column("users", "mundos")
    op.drop_index("ix_cenefa_destinos_mundo", table_name="cenefa_destinos")
    op.drop_column("cenefa_destinos", "mundo")
    op.drop_index("ix_calendario_barras_mundo", table_name="calendario_barras")
    op.drop_column("calendario_barras", "mundo")
