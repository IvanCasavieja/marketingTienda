"""el ZIP original de cada ronda

Pedido de Ivan (19/11/2026): "no es más fácil guardar el zip en vez de
guardar las imágenes? (…) cuando lo subís deberías de subir la carpeta
comprimida, no los archivos sueltos, porque pesan más". El ZIP que entrega la
agencia se guarda tal cual, como el original de esa ronda, en un lugar propio:
`calendario_version_zips`, una fila por versión con el nombre del archivo, lo
que pesa, la fecha y los bytes. Es lo que más adelante se va a subir a
SharePoint. Las imágenes de la ronda (1600 px) siguen aparte: son las que se
miran y se marcan.

Es una tabla de la base y no Supabase Storage porque el servidor no usa
Storage para nada: todo archivo vive en Postgres (las imágenes de las
entregas, los PDF de facturación). `datos` es NULL cuando el ZIP no se guardó
porque la base estaba llena (la entrega se hizo igual). Cuelga de la versión
con ON DELETE CASCADE, como sus imágenes. Ver app/models/entregas.py
(CalendarioVersionZip).

Revision ID: 0081
Revises: 0080
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendario_version_zips",
        sa.Column(
            "version_id", sa.String(64), sa.ForeignKey("calendario_versiones.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False),
        sa.Column("datos", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("calendario_version_zips")
