"""el link privado del calendario para Outlook, Google o el iPhone

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-15

Cada persona puede suscribir su calendario de Core Tienda en Outlook (o Google
Calendar, o el calendario del iPhone) con un link privado. El link va firmado
con un número por persona: "Generar otro link" lo sube y el anterior deja de
andar (por si se compartió sin querer).
"""
from alembic import op
import sqlalchemy as sa

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("calendario_link_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "calendario_link_version")
