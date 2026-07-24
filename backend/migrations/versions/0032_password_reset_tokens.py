"""create password_reset_tokens table

Reemplaza el guardado en Redis del token de /auth/forgot-password: el
proyecto nunca configuró REDIS_URL en producción (Render), lo que rompía
la recuperación de contraseña con un 500. En vez de sumar Redis como
dependencia dura solo para esto, el token se guarda acá — Postgres/Supabase
ya es infraestructura existente y el resto del proyecto ya trata a Redis
como opcional.

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-24

"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    # Respalda el DELETE de limpieza de vencidos en cada /forgot-password
    # (ver auth.py) — sin esto, esa query hace full scan a medida que crece
    # la tabla.
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_expires_at", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
