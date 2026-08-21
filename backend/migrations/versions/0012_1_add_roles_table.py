"""crear tabla roles y users.role_id

Faltaba en la cadena de migraciones: en producción, roles y users.role_id
existen desde antes de que la migración 0013 se escribiera, creados por
app/core/tenant_migration.py::migrate_roles() (corre en cada arranque del
backend, con CREATE TABLE/ADD COLUMN IF NOT EXISTS). Como esa función nunca
pasó por Alembic, migrar una base realmente vacía desde cero fallaba en 0013
("relation roles does not exist") — nunca se había notado porque producción
jamás corrió las migraciones desde cero. Esta migración solo formaliza lo que
tenant_migration.py ya crea (sin "view_only", que se agrega recién en 0013).
No afecta a producción: Alembic no reaplica revisiones ya pasadas, solo le
importa el puntero de versión actual.

Revision ID: 0012_1
Revises: 0012
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision      = "0012_1"
down_revision = "0012"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column(
        "users",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "role_id")
    op.drop_table("roles")
