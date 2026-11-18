"""los avisos de la campanita, también por mail

Pedido de Ivan (18/11/2026): "es muy bueno que los avisos lleguen por mail".
Eligió: todos los avisos, al momento (uno por aviso), y que cada persona los
pueda apagar desde su perfil (prendidos por defecto).

- `notificaciones.mail_pendiente`: el aviso todavía tiene que salir por mail.
  Lo marca el modelo al crear cada aviso nuevo; los que ya existen quedan en
  false (no se mandan por mail los avisos viejos).
- `notificaciones.mail_enviado_at` y `mail_intentos`: cuándo salió y cuántas
  veces se intentó (se reintenta si el proveedor falla).
- `users.avisos_por_mail`: si la persona los quiere por mail.

Ver app/services/avisos_por_mail.py.

Revision ID: 0079
Revises: 0078
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notificaciones", sa.Column("mail_pendiente", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("notificaciones", sa.Column("mail_enviado_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notificaciones", sa.Column("mail_intentos", sa.SmallInteger(), nullable=False, server_default="0"))
    # El loop busca solo los pendientes: un índice parcial, chiquito.
    op.create_index(
        "ix_notificaciones_mail_pendiente", "notificaciones", ["id"],
        postgresql_where=sa.text("mail_pendiente"),
    )
    op.add_column("users", sa.Column("avisos_por_mail", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("users", "avisos_por_mail")
    op.drop_index("ix_notificaciones_mail_pendiente", table_name="notificaciones")
    op.drop_column("notificaciones", "mail_intentos")
    op.drop_column("notificaciones", "mail_enviado_at")
    op.drop_column("notificaciones", "mail_pendiente")
