"""la familia de mecanica de un OFERTADET que el motor no reconoce

El Convertidor deduce la familia del texto de OFERTADET. Cuando gestion inventa
un tipo nuevo no la reconoce, y la fila pierde la mecanica entera: sin cocarda,
sin "Comprando N", sin unidad. Lo unico que queda es el aviso
`ofertadet_desconocido` en la grilla, que hay que mirar y resolver a mano cada
vez que ese mismo tipo vuelve a aparecer -- y vuelve todas las semanas, porque
es el mismo listado de gestion.

Esta tabla guarda la respuesta una vez que una persona la confirmo. Desde ahi
ese OFERTADET lo resuelve el codigo, igual que los que estan hardcodeados, solo
que aprendido.

Mismo patron que convertidor_header_aliases, para las columnas.

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cenefa_ofertadet_aliases",
        sa.Column("ofertadet_norm", sa.String(120), primary_key=True),
        sa.Column("familia", sa.String(20), nullable=False),
        sa.Column("ofertadet_display", sa.String(255), nullable=False, server_default=""),
        sa.Column("confirmado_por", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Una familia invalida no se puede resolver y dejaria la fila peor que
    # antes: sin aviso y sin mecanica. Se cierra en la base, no solo en el
    # Pydantic de la ruta.
    op.create_check_constraint(
        "ck_cenefa_ofertadet_familia",
        "cenefa_ofertadet_aliases",
        "familia IN ('combo', 'mxn', 'segunda', 'sin_mecanica')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cenefa_ofertadet_familia", "cenefa_ofertadet_aliases")
    op.drop_table("cenefa_ofertadet_aliases")
