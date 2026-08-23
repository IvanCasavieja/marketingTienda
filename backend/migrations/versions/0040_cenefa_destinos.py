"""destinos de cenefas como datos, no como codigo

Hasta ahora los "mundos" de cenefas (Redexpres, Rompe Precios, Parrilla y
Vinos) eran una union de strings hardcodeada en el frontend y en el backend:
sumar uno nuevo exigia tocar codigo y desplegar. Pasan a ser filas de esta
tabla, creables desde el selector de mundos.

El slug es la PK a proposito: es exactamente el valor que ya vive en
cenefa_templates_v2.category y el que viaja en la URL (?destino=...), asi que
usarlo como clave evita una capa de traduccion id->slug y hace que los
templates existentes queden asociados a su destino sin migrar dato alguno.

Se siembran los tres destinos que ya estaban hardcodeados, con los mismos
slugs que ya usan los templates guardados -- sin esto, las plantillas
existentes quedarian huerfanas de mundo.

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-23

"""
import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cenefa_destinos",
        sa.Column("slug", sa.String(50), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=False, server_default=""),
        sa.Column("icono", sa.String(40), nullable=False, server_default="Store"),
        sa.Column("color", sa.String(30), nullable=False, server_default="emerald"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    destinos = sa.table(
        "cenefa_destinos",
        sa.column("slug", sa.String),
        sa.column("nombre", sa.String),
        sa.column("descripcion", sa.String),
        sa.column("icono", sa.String),
        sa.column("color", sa.String),
        sa.column("orden", sa.Integer),
    )
    op.bulk_insert(destinos, [
        {
            "slug": "rompe_precios", "nombre": "Rompe Precios",
            "descripcion": "Cenefas de las promos del fin de semana",
            "icono": "PartyPopper", "color": "rose", "orden": 10,
        },
        {
            "slug": "parrilla_y_vinos", "nombre": "Parrilla y Vinos",
            "descripcion": "Cenefas con niveles de precio por cantidad",
            "icono": "Wine", "color": "purple", "orden": 20,
        },
        {
            "slug": "redexpres", "nombre": "Redexpres",
            "descripcion": "Cenefas de gondola de los locales Redexpres",
            "icono": "Store", "color": "emerald", "orden": 30,
        },
    ])


def downgrade() -> None:
    op.drop_table("cenefa_destinos")
