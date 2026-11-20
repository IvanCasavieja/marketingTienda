"""borrar las tareas de prueba de las acciones

Ivan (20/11/2026): "hay que eliminar también todas las tareas creadas para
las acciones, porque fueron todas de prueba". Eligió:

- Se borran todas las tareas, en todos los mundos, menos las Lanzar que
  Redexpres crea sola en cada acción (0077): salen del calendario real. Se
  reconocen por su id ("ta-la-" y 16 caracteres hexadecimales, que ningún
  otro lugar genera; ver controles_redexpres.id_de_tarea), aunque les hayan
  cambiado el nombre.
- Con cada tarea se va lo que cuelga de ella (la base lo hace en cascada):
  subtareas, la tarjeta del tablero, fases, rondas, imágenes, ZIPs, marcas,
  decisiones, comentarios y lo que dijo la IA. Las acciones quedan.
- Se borran también los avisos de la campanita que hablaban de esas tareas
  (asignaciones, "te pidió", entregas, comentarios): llevarían a nada. Se
  reconocen por su origen ('calendario_tarea' y 'calendario_entrega') y
  porque su referencia ("acción:tarea[:...]") apunta a una tarea que ya no
  existe.

Es una sola vez: no cambia nada del esquema.

Revision ID: 0085
Revises: 0084
Create Date: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    # Las subtareas de una Lanzar (cargadas a mano) también se van: se borran
    # todas las que no son Lanzar, sin mirar de quién cuelgan.
    con.execute(sa.text(r"DELETE FROM calendario_tareas WHERE id !~ '^ta-la-[0-9a-f]{16}$'"))
    con.execute(sa.text(
        """DELETE FROM notificaciones n
           WHERE n.origen_tipo IN ('calendario_tarea', 'calendario_entrega')
             AND NOT EXISTS (
               SELECT 1 FROM calendario_tareas t WHERE t.id = split_part(n.origen_ref, ':', 2)
             )"""
    ))
    # Que las pantallas abiertas (de todos los mundos) se enteren.
    rev = con.execute(sa.text("UPDATE calendario_revision SET rev = rev + 1 WHERE id = 1 RETURNING rev")).scalar()
    if rev is not None:
        con.execute(sa.text("UPDATE calendario_revision_mundo SET rev = :rev"), {"rev": rev})


def downgrade() -> None:
    # Lo borrado no vuelve.
    pass
