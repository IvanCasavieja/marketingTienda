"""las acciones de la fila TIENDA FARMA pasan al mundo Tienda Farma

Revision ID: 0062
Revises: 0061
Create Date: 2026-11-15

Ivan, 15/11/2026: "Si, todo lo que sea tienda farma se muda a tienda farma,
sin lugar a dudas."

Desde la 0060 Tienda Farma es un mundo propio, pero lo cargado antes seguia en
el calendario de Tienda Inglesa, en la fila "TIENDA FARMA", marcado "Ya no se
usa". Esto lo muda:

- Las acciones del calendario comercial de Tienda Inglesa cuya categoria es
  TIENDA FARMA (con cualquier mayuscula o espacio de mas, como la compara el
  front) pasan al mundo tienda_farma. Sus piezas, avisos y tareas van con
  ellas: cuelgan de la accion.
- Llegan "Sin categoria": en Farma las categorias son otras (Campanas,
  Promociones...) y "TIENDA FARMA" ahi no dice nada. La elige quien trabaje en
  Farma, adentro de la accion, como cualquier accion nueva.
- Sube la revision del calendario, asi una pestana abierta se entera.

No le da el mundo Tienda Farma a nadie: se tilda a mano desde el panel (regla
de la 0060). Quien tenga una tarea o un aviso en estas acciones y no entre a
Farma deja de verla hasta que se lo tilden.

La vuelta atras no se puede hacer con seguridad (no queda marcado cuales
vinieron de Tienda Inglesa y despues pudo haber acciones nuevas en Farma sin
categoria): no hace nada.
"""
from alembic import op
from sqlalchemy import text

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

SIN_CATEGORIA = "Sin categoría"


def upgrade() -> None:
    conn = op.get_bind()
    movidas = conn.execute(
        text(
            """
            UPDATE calendario_barras
               SET mundo = 'tienda_farma', banda = :sin
             WHERE mundo = 'tienda_inglesa'
               AND seccion = 'comercial'
               AND regexp_replace(upper(btrim(banda)), '\\s+', ' ', 'g') = 'TIENDA FARMA'
            RETURNING id
            """
        ),
        {"sin": SIN_CATEGORIA},
    ).fetchall()
    if movidas:
        conn.execute(text("UPDATE calendario_revision SET rev = rev + 1 WHERE id = 1"))


def downgrade() -> None:
    pass
