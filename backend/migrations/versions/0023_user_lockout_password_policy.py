"""add login lockout and password rotation fields to users

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill: para cuentas ya existentes, usamos su fecha de alta como punto
    # de partida de la rotación de 20 días — no sabemos cuándo cambiaron la
    # contraseña por última vez, así que created_at es la mejor aproximación
    # honesta disponible. No las marcamos must_change_password=True (eso
    # queda reservado a partir de ahora para cuentas nuevas/reseteadas).
    op.execute("UPDATE users SET password_changed_at = created_at WHERE password_changed_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
