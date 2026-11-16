"""cuentas externas: la agencia adentro de Core Tienda, con la vista limitada

Revision ID: 0068
Revises: 0067
Create Date: 2026-11-15

Pedido de Ivan (15/11/2026): "que la agencia en un futuro tenga acceso a la
plataforma… limitar también las vistas… que solamente puedan ver el
calendario actual, no lo que viene dentro de 2 o 3 meses".

- `users.es_externo` y `users.empresa`: la cuenta de una agencia o de un
  diseñador de afuera. Es un usuario más (entra igual que todos; con Microsoft
  el día que se entre con Microsoft), marcado con el flag. Lo que puede ver lo
  cuida app/core/externos.py.
- Dos reglas que la base misma se niega a romper, por si algún camino futuro
  se olvida de mirar el flag: un externo nunca es superadmin, y sus permisos
  son como mucho `calendario.view`. Si algún día se le quiere dar otro (Don
  Tino, por ejemplo), se cambia esta regla en otra migración y la lista de
  app/core/externos.py, las dos juntas.
- `calendario_decisiones.nota_interna`: una nota de la decisión que la
  agencia no ve (las marcas y el comentario sí, que son para ella).
"""
from alembic import op
import sqlalchemy as sa

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("es_externo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("users", sa.Column("empresa", sa.String(length=120), nullable=True))
    op.create_check_constraint(
        "ck_users_externo_no_es_superadmin", "users", "NOT (es_externo AND is_superuser)",
    )
    # `permissions` es JSON (no JSONB): se compara como JSONB. Un JSON null o
    # una lista vacía también valen (un externo sin nada no ve nada).
    op.create_check_constraint(
        "ck_users_externo_solo_calendario", "users",
        "NOT es_externo OR permissions IS NULL OR permissions::jsonb = 'null'::jsonb "
        "OR permissions::jsonb <@ '[\"calendario.view\"]'::jsonb",
    )
    op.create_check_constraint(
        "ck_users_externo_con_empresa", "users",
        "NOT es_externo OR (empresa IS NOT NULL AND length(btrim(empresa)) > 0)",
    )
    op.add_column("calendario_decisiones", sa.Column("nota_interna", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendario_decisiones", "nota_interna")
    op.drop_constraint("ck_users_externo_con_empresa", "users", type_="check")
    op.drop_constraint("ck_users_externo_solo_calendario", "users", type_="check")
    op.drop_constraint("ck_users_externo_no_es_superadmin", "users", type_="check")
    op.drop_column("users", "empresa")
    op.drop_column("users", "es_externo")
