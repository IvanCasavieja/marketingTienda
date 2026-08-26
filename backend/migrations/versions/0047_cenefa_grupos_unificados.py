"""grupos unificados con su lista de SKU

Un grupo unificado es un conjunto de SKU que comparten UN cartel ("Coca-Cola
Light o Zero 2.25 L"). Hasta ahora se guardaba en `sku_descripciones` usando el
codigo COMBINADO como si fuera un SKU ("63009 / 211797").

Eso alcanza para que el mismo Excel vuelva a resolver igual, y falla para todo
lo demas: si manana la promo trae DOS de esos tres SKU, o los mismos tres en
otro orden, esa clave no matchea y el grupo se pierde. Peor: la descripcion
guardada menciona productos que hoy no estan en oferta, y un cartel de gondola
no puede anunciar algo que no se vende a ese precio.

Guardando la LISTA se puede detectar el subconjunto y avisar que hay que
reescribir la descripcion con los que si vinieron. Las descripciones
INDIVIDUALES de cada SKU siguen en `sku_descripciones` -- son las que permiten
rearmar el texto del grupo parcial.

El indice GIN sobre `skus` es para poder preguntar "que grupos tocan alguno de
estos 100 SKU" en una sola consulta, que es lo que hace el Convertidor al
preparar la grilla.

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-26

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cenefa_grupos_unificados",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("skus", postgresql.ARRAY(sa.String(60)), nullable=False),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_cenefa_grupos_skus", "cenefa_grupos_unificados", ["skus"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_cenefa_grupos_skus", table_name="cenefa_grupos_unificados")
    op.drop_table("cenefa_grupos_unificados")
