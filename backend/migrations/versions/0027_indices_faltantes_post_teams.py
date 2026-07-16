"""agregar indices que se perdieron al sacar el sistema de equipos

campaign_metrics tenia indices (team_group_id, date, platform) y
(team_group_id, date) que se borraron enteros junto con la columna en
0009_remove_teams_and_groups, sin reponer un indice para las columnas que
quedaron (date, platform) — exactamente lo que filtra toda consulta de
dashboard/analytics (ver metrics_service.py). audit_logs nunca tuvo indice
y siempre se lee con ORDER BY created_at DESC + LIMIT/OFFSET. cenefa_jobs
perdio su indice sobre team_group_id en 0008_remove_team_group_from_cenefas
sin reponerlo sobre created_by, la columna que identifica al dueno del job.

Se crean CONCURRENTLY porque estas tres tablas reciben escrituras reales en
producción (sync de metricas cada 6hs, casi cualquier accion admin logueada
en audit_logs) — un CREATE INDEX normal toma un lock que bloquea escrituras
mientras construye el indice; CONCURRENTLY evita eso a cambio de no poder
correr dentro de la transacción que alembic abre por default, de ahi el
autocommit_block().

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-15

"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_campaign_metrics_date_platform",
            "campaign_metrics",
            ["date", "platform"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_audit_logs_created_at",
            "audit_logs",
            ["created_at"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_cenefa_jobs_created_by",
            "cenefa_jobs",
            ["created_by"],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index("ix_cenefa_jobs_created_by", table_name="cenefa_jobs", postgresql_concurrently=True)
        op.drop_index("ix_audit_logs_created_at", table_name="audit_logs", postgresql_concurrently=True)
        op.drop_index("ix_campaign_metrics_date_platform", table_name="campaign_metrics", postgresql_concurrently=True)
