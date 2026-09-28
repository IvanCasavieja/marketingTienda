"""los envios sueltos: un mailing, un WhatsApp o una push sin una accion detras

Pedido de Ivan (28/09/2026): "de repente no hay una promocion y tenemos que
salir con un email marketing, con una push, con un WhatsApp, y no podemos
hacerlo porque al no estar ligado con una promocion no lo podemos crear".

Hasta aca un envio salia SIEMPRE de la pieza de una accion. Ahora tambien
puede ser una barra propia, de la seccion 'envio', con el canal en `banda`
('email', 'whatsapp', 'push') y lo que en un envio de accion lleva la pieza:
el formato, la hora y el estado. Tres columnas nuevas, todas opcionales: las
barras que ya existen no cambian en nada.

Revision ID: 0058
Revises: 0057
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendario_barras", sa.Column("formato", sa.String(100), nullable=True))
    op.add_column("calendario_barras", sa.Column("hora", sa.String(5), nullable=True))
    op.add_column("calendario_barras", sa.Column("estado", sa.String(20), nullable=True))


def downgrade() -> None:
    # Los envios sueltos no se borran: sin estas columnas pierden el formato,
    # la hora y el estado, pero quedan (nombre, canal y fecha), y la version
    # anterior del front simplemente no los muestra.
    op.drop_column("calendario_barras", "estado")
    op.drop_column("calendario_barras", "hora")
    op.drop_column("calendario_barras", "formato")
