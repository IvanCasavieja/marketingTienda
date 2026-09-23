"""el calendario en la base, cenefas.diccionario aparte y sucursales por tipo

Tres cambios que vienen del mismo pedido (23/09/2026), preparando la
capacitación:

1. El Diccionario deja de compartir permiso con el Convertidor. Hasta hoy los
   tres links de Materiales (Cenefas, Convertidor y Diccionario) se mostraban
   con `cenefas.view`, así que no había forma de darle a alguien el Diccionario
   solo. Se agrega `cenefas.diccionario` y se backfillea a TODO rol y usuario
   que ya tenga `cenefas.view`: nadie pierde ni gana acceso al aplicar esto.

2. `local_asignaciones` gana `tipo`. Los 60 logins de sucursal que hay son
   todos de Redexpres, pero la lista de usuarios pasa a mostrarse en pestañas
   (Usuarios / Sucursales Redex / Sucursales Tienda) y las de Tienda llegan más
   adelante: sin esta columna las dos quedarían mezcladas en la misma pestaña.

3. `calendario_meses`: el calendario deja el localStorage de cada navegador y
   pasa a la base. Sin esto el servidor no sabe que existe ninguna acción, y no
   puede avisar 10 días antes de que arranque — que es lo que se pidió.

Revision ID: 0056
Revises: 0055
Create Date: 2026-09-23
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

_NUEVO = "cenefas.diccionario"
_ORIGEN = "cenefas.view"


def _con_diccionario(permissions) -> tuple[list, bool]:
    """Agrega cenefas.diccionario si ya estaba cenefas.view. Devuelve
    (permisos, si cambió)."""
    permisos = list(permissions or [])
    if _ORIGEN in permisos and _NUEVO not in permisos:
        permisos.insert(permisos.index(_ORIGEN) + 1, _NUEVO)
        return permisos, True
    return permisos, False


def upgrade() -> None:
    op.create_table(
        "calendario_meses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clave", sa.String(7), nullable=False),
        sa.Column("datos", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("actualizado_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calendario_meses_clave", "calendario_meses", ["clave"], unique=True)

    op.add_column(
        "local_asignaciones",
        sa.Column("tipo", sa.String(20), nullable=False, server_default="redex"),
    )

    conn = op.get_bind()
    for tabla in ("roles", "users"):
        for row_id, permissions in conn.execute(
            text(f"SELECT id, permissions FROM {tabla}")
        ).fetchall():
            permisos, cambio = _con_diccionario(permissions)
            if cambio:
                conn.execute(
                    text(f"UPDATE {tabla} SET permissions = CAST(:perms AS json) WHERE id = :id"),
                    {"perms": json.dumps(permisos), "id": row_id},
                )


def downgrade() -> None:
    # El permiso no se quita: pudo tildarse o destildarse a mano después de
    # aplicar esto (mismo criterio que 0031, 0035 y 0055).
    op.drop_column("local_asignaciones", "tipo")
    op.drop_index("ix_calendario_meses_clave", table_name="calendario_meses")
    op.drop_table("calendario_meses")
