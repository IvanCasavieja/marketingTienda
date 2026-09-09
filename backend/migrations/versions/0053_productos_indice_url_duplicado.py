"""borra el indice unico duplicado de productos.url

La migracion 0003 declara la columna `url` con `unique=True` --que hace que
Postgres cree el indice de la constraint, `productos_url_key`-- y ademas hace
`op.create_index("ix_productos_url", ..., unique=True)`. Son dos indices unicos
btree IDENTICOS sobre la misma columna: el planner usa uno o el otro y le
alcanza con uno.

No es solo prolijidad. Medido en produccion el 2026-09-08: los dos pesaban
117 MB cada uno (los upserts del scraper los habian inflado 33x sobre los
3,5 MB que pesa un btree fresco de esas 36.975 URLs). La base estaba en
565 MB contra los 500 MB de cuota de Supabase, a un paso de que el proyecto
quedara en solo-lectura. Dropear el duplicado + REINDEX bajo la base a 269 MB
sin perder una fila.

El DROP ya se corrio a mano en produccion, de ahi el IF EXISTS: esta migracion
existe para que una base creada desde cero no vuelva a nacer con el duplicado.
La unicidad de `url` la sigue garantizando `productos_url_key`, que respalda la
constraint de la columna y no se toca.

Revision ID: 0053
Revises: 0052
Create Date: 2026-09-08

"""
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_productos_url")


def downgrade() -> None:
    # Vuelve a dejar el duplicado, para no mentirle al historial.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_productos_url "
        "ON public.productos USING btree (url)"
    )
