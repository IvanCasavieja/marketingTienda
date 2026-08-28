"""los campos de entrada del Convertidor pasan a camelCase

Los 12 campos de entrada (los "casilleros" a los que se mapea una columna del
export de gestion: precio, ofertaDet, nombreArticulo...) eran claves internas
en snake_case que terminaron expuestas en la pantalla de Tinin. La regla de la
plataforma es que todo el vocabulario visible va en camelCase (decision de
Ivan, 2026-08-29), asi que se renombraron de punta a punta.

Esta migracion actualiza lo GUARDADO con los nombres viejos: los alias
aprendidos de convertidor_header_aliases.field_name ("REGULAR" ->
"precio_anterior" pasa a "precioAnterior"). Sin esto, el codigo nuevo no
reconoce el alias y esa columna se vuelve a preguntar -- no rompe nada, pero
tira a la basura lo ya confirmado.

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-29
"""
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

# viejo (snake) -> nuevo (camelCase). Solo los 7 que cambian; codigo, moneda,
# precio, oferta y comprador ya eran una sola palabra.
_RENAMES = {
    "nombre_articulo":   "nombreArticulo",
    "descripcion_excel": "descripcionExcel",
    "descripcion_web":   "descripcionWeb",
    "precio_anterior":   "precioAnterior",
    "oferta_det":        "ofertaDet",
    "fecha_inicio":      "fechaInicio",
    "fecha_fin":         "fechaFin",
}


def upgrade() -> None:
    for viejo, nuevo in _RENAMES.items():
        op.execute(
            f"UPDATE convertidor_header_aliases SET field_name = '{nuevo}' "
            f"WHERE field_name = '{viejo}'"
        )


def downgrade() -> None:
    for viejo, nuevo in _RENAMES.items():
        op.execute(
            f"UPDATE convertidor_header_aliases SET field_name = '{viejo}' "
            f"WHERE field_name = '{nuevo}'"
        )
