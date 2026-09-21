"""validación de redes sociales (CatTi): tablas y permisos

Nueva área "Redes sociales" -> "Validación de RRSS": se cargan las placas de
una campaña junto al mailing original y CatTi (el agente de la familia Tino)
las compara una por una. Ver backend/app/services/rrss/.

rrss_validaciones guarda cada corrida; rrss_validacion_paginas las páginas del
mailing ya renderizadas y rrss_validacion_imagenes cada placa con su
resultado. No se guardan los archivos originales (ver el modelo).

rrss.view / rrss.validate son permisos nuevos: DEFAULT_ROLES solo siembra
roles NUEVOS, así que las filas existentes de Superadmin/Admin (y de sus
usuarios) se backfillean acá, mismo criterio que 0035_facturacion_permissions.
"Usuario"/"Viewer" quedan sin tocar: se otorga puntual desde el panel.

Revision ID: 0055
Revises: 0054
Create Date: 2026-09-21
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

_NUEVOS = ["rrss.view", "rrss.validate"]


def _con_nuevos(permissions) -> tuple[list, bool]:
    permisos = list(permissions or [])
    cambio = False
    for p in _NUEVOS:
        if p not in permisos:
            permisos.append(p)
            cambio = True
    return permisos, cambio


def upgrade() -> None:
    op.create_table(
        "rrss_validaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre_mailing", sa.String(255), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="en_proceso"),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("mailing", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("resumen", postgresql.JSONB(), nullable=True),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    op.create_table(
        "rrss_validacion_paginas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("validacion_id", sa.Integer(), sa.ForeignKey("rrss_validaciones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("ancho", sa.Integer(), nullable=False),
        sa.Column("alto", sa.Integer(), nullable=False),
        sa.Column("imagen", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_rrss_validacion_paginas_validacion_id", "rrss_validacion_paginas", ["validacion_id"])
    op.create_table(
        "rrss_validacion_imagenes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("validacion_id", sa.Integer(), sa.ForeignKey("rrss_validaciones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nombre_archivo", sa.String(255), nullable=False),
        sa.Column("ancho", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alto", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("formato", sa.String(20), nullable=False, server_default=""),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("resultado", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("vista", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    op.create_index("ix_rrss_validacion_imagenes_validacion_id", "rrss_validacion_imagenes", ["validacion_id"])

    conn = op.get_bind()
    admin_role_ids = {
        r[0] for r in conn.execute(
            text("SELECT id FROM roles WHERE name IN ('Superadmin', 'Admin')")
        ).fetchall()
    }
    if not admin_role_ids:
        return

    for row_id, permissions in conn.execute(
        text("SELECT id, permissions FROM roles WHERE id = ANY(:ids)"),
        {"ids": list(admin_role_ids)},
    ).fetchall():
        permisos, cambio = _con_nuevos(permissions)
        if cambio:
            conn.execute(
                text("UPDATE roles SET permissions = CAST(:perms AS json) WHERE id = :id"),
                {"perms": json.dumps(permisos), "id": row_id},
            )

    for row_id, permissions in conn.execute(
        text("SELECT id, permissions FROM users WHERE role_id = ANY(:ids)"),
        {"ids": list(admin_role_ids)},
    ).fetchall():
        permisos, cambio = _con_nuevos(permissions)
        if cambio:
            conn.execute(
                text("UPDATE users SET permissions = CAST(:perms AS json) WHERE id = :id"),
                {"perms": json.dumps(permisos), "id": row_id},
            )


def downgrade() -> None:
    # Los permisos no se quitan: pudieron tildarse/destildarse a mano después
    # de aplicar esto (mismo criterio que 0031 y 0035).
    op.drop_index("ix_rrss_validacion_imagenes_validacion_id", table_name="rrss_validacion_imagenes")
    op.drop_table("rrss_validacion_imagenes")
    op.drop_index("ix_rrss_validacion_paginas_validacion_id", table_name="rrss_validacion_paginas")
    op.drop_table("rrss_validacion_paginas")
    op.drop_table("rrss_validaciones")
