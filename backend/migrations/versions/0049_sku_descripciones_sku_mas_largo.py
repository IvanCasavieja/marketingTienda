"""el codigo combinado de un grupo unificado no entraba en sku_descripciones.sku

Unificar N SKU en un solo cartel escribe una fila en `sku_descripciones` con el
codigo combinado como clave ("520221 - 512909 - 520220 - ..."). La columna era
VARCHAR(64), asi que un grupo de 11 acondicionadores ELVIVE (~130 caracteres) no
se podia guardar: la unificacion se cortaba con "este grupo tiene demasiados
SKUs" justo cuando mas sentido tenia hacerla. El tope de 64 del frontend era el
espejo de esta columna, no una regla de negocio.

600 da lugar a ~60 SKU de 6 digitos unidos por " - ", muy por encima de
cualquier grupo real, y sigue siendo un techo (la clave se manda en el path de
la URL y entra en un indice unico, no conviene dejarla sin limite).

En Postgres agrandar el limite de un varchar es un cambio de metadata: no
reescribe la tabla ni reconstruye el indice unico, y ningun dato existente se
toca. El downgrade solo puede volver atras si no quedo ninguna clave mas larga
que 64 -- si quedo, hay que borrar esas filas primero a mano, a proposito: es
dato del equipo y no se descarta solo.

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sku_descripciones",
        "sku",
        existing_type=sa.String(64),
        type_=sa.String(600),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "sku_descripciones",
        "sku",
        existing_type=sa.String(600),
        type_=sa.String(64),
        existing_nullable=False,
    )
