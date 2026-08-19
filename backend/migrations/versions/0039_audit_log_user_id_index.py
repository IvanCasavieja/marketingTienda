"""agregar indice por user_id a audit_logs

audit_logs solo tenia indice por created_at (0027, para el listado global
ORDER BY created_at DESC). Las estadisticas de actividad por usuario
(listado de usuarios con ultimo ingreso/cantidad de ingresos, filtro por
usuario en /admin/audit-log, conteo de logins en /admin/users/{id}/stats)
agregan queries nuevas por user_id -- sin indice, table scan completo en una
tabla que ya recibe escrituras reales en produccion.

Indice compuesto (user_id, action) en vez de solo user_id: la query mas
frecuente de las nuevas (contar/ordenar logins) filtra por AMBAS columnas
(WHERE user_id = X AND action = 'user.login'), asi que el compuesto la cubre
sin necesitar un indice aparte solo para user_id.

CONCURRENTLY + autocommit_block(), mismo patron que 0027 (misma tabla, mismo
motivo: no bloquear escrituras mientras se construye).

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-19

"""
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_audit_logs_user_id_action",
            "audit_logs",
            ["user_id", "action"],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index("ix_audit_logs_user_id_action", table_name="audit_logs", postgresql_concurrently=True)
