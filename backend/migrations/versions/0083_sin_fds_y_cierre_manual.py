"""sin Super FDS desde diciembre, y el Cierre pasa a ser manual

Ivan (20/11/2026):
- "FDS no va a existir más, me confirman que ya no se va a usar (...) todo lo
  que es lanzar y cerrar FDS más la línea de FDS no debería de existir más a
  partir de diciembre".
- "El cierre común debería de quedar como una tarea manual a crear por Vale,
  ya que tema fechas es muy complejo (...) se creará manual y solo manual".

Lo único automático que queda en Redexpres es Lanzar (ver
app/services/controles_redexpres.py). Esta migración saca lo que habían dejado
las 0077 y 0078:

- los avisos de Cierre, Lanzar FDS y Cierre FDS;
- las tareas automáticas de Cierre, Lanzar FDS y Cierre FDS que todavía no
  estaban hechas y no tienen nada colgando (subtareas o entregas): si alguien
  ya las usó, quedan. Se reconocen por su id ("ta-ci-", "ta-cf-", "ta-lf-" y
  16 caracteres hexadecimales, que ningún otro lugar genera) y su título;
- los Super FDS de Redexpres de diciembre de 2026 en adelante (no debería
  haber ninguno: el Excel cargado termina en noviembre). La fila se sigue
  viendo hasta noviembre con lo que ya tenía (bandasRetiradas en
  frontend/lib/mundos.ts).

Revision ID: 0083
Revises: 0082
Create Date: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    con.execute(sa.text("DELETE FROM calendario_avisos WHERE control IN ('cierre', 'lanzar_fds', 'cierre_fds')"))
    con.execute(sa.text(
        r"""DELETE FROM calendario_tareas t
           WHERE t.id ~ '^ta-(ci|cf|lf)-[0-9a-f]{16}$'
             AND t.titulo IN ('Cierre', 'Cierre FDS', 'Lanzar FDS')
             AND t.estado <> 'hecha'
             AND NOT EXISTS (SELECT 1 FROM calendario_tareas h WHERE h.parent_id = t.id)
             AND NOT EXISTS (SELECT 1 FROM calendario_entregas e WHERE e.tarea_id = t.id)"""
    ))
    con.execute(sa.text(
        r"""DELETE FROM calendario_barras
           WHERE mundo = 'redexpres' AND seccion = 'comercial'
             AND lower(regexp_replace(trim(banda), '\s+', ' ', 'g')) = 'super fds'
             AND desde >= DATE '2026-12-01'"""
    ))
    # Que las pantallas abiertas de Redexpres se enteren.
    rev = con.execute(sa.text("UPDATE calendario_revision SET rev = rev + 1 WHERE id = 1 RETURNING rev")).scalar()
    if rev is not None:
        con.execute(sa.text(
            """INSERT INTO calendario_revision_mundo (mundo, rev) VALUES ('redexpres', :rev)
               ON CONFLICT (mundo) DO UPDATE SET rev = EXCLUDED.rev"""
        ), {"rev": rev})


def downgrade() -> None:
    # Lo borrado no vuelve: el código ya no los crea.
    pass
