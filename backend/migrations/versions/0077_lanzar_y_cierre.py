"""Lanzar y Cierre: las tareas y los avisos que trae cada acción de Redexpres

Pedido de Ivan (18/11/2026): "una vez se crea una acción, la tarea de lanzar
y de cierre debe estar creada automáticamente", con aviso a todo el equipo de
Lanzar 60 y 30 días antes y de Cierre 4 semanas antes. Ver
app/services/controles_redexpres.py.

- `calendario_avisos.control`: 'lanzar' o 'cierre' en los avisos que trae la
  acción (le llegan a todo el equipo del mundo).
- A las acciones de Redexpres que todavía no arrancaron (menos "Super FDS" y
  "BOMBAS", que son semanales) se les suma lo que todavía está a tiempo: la
  tarea si su fecha no pasó y el aviso si todavía no tendría que haber salido.
  Lo vencido no se agrega: al publicar no le llueven al equipo avisos de cosas
  que seguramente ya se hicieron.

Revision ID: 0077
Revises: 0076
Create Date: 2026-11-18
"""
import hashlib
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

# Las mismas reglas e ids que app/services/controles_redexpres.py (copiadas:
# una migración no depende del código de la app, que cambia).
TAREAS = (
    ("lanzar", "Lanzar", 60, "Lanzar la acción: arrancar el pedido y avisar a quienes participan. Unos 2 meses antes."),
    ("cierre", "Cierre", 28, "Cerrar la acción: todo definido para mandar a producción. Unas 4 semanas antes."),
)
AVISOS = (("lanzar", 60), ("lanzar", 30), ("cierre", 28))


def _corto(texto):
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


def upgrade() -> None:
    op.add_column("calendario_avisos", sa.Column("control", sa.String(16), nullable=True))

    con = op.get_bind()
    hoy = datetime.now(timezone(timedelta(hours=-3))).date()
    barras = con.execute(sa.text(
        """SELECT id, desde, creado_por_id FROM calendario_barras
           WHERE mundo = 'redexpres' AND seccion = 'comercial' AND desde > :hoy
             AND lower(trim(banda)) NOT IN ('super fds', 'bombas')"""
    ), {"hoy": hoy}).all()
    for barra_id, desde, creado_por in barras:
        titulos = {
            (t or "").strip().casefold() for (t,) in con.execute(
                sa.text("SELECT titulo FROM calendario_tareas WHERE barra_id = :b"), {"b": barra_id}
            )
        }
        for orden, (control, titulo, dias, detalle) in enumerate(TAREAS):
            fecha = desde - timedelta(days=dias)
            if titulo.casefold() in titulos or fecha < hoy:
                continue
            con.execute(sa.text(
                """INSERT INTO calendario_tareas
                       (id, barra_id, titulo, descripcion, estado, vence, ancla, ancla_dias, orden, creado_por_id, para)
                   VALUES (:id, :b, :titulo, :detalle, 'pendiente', :vence, 'inicio', :dias, :orden, :creado_por, 'tienda')
                   ON CONFLICT (id) DO NOTHING"""
            ), {
                "id": f"ta-{control[:2]}-{_corto(barra_id)}", "b": barra_id, "titulo": titulo, "detalle": detalle,
                "vence": fecha, "dias": -dias, "orden": orden, "creado_por": creado_por,
            })
        for control, dias in AVISOS:
            if desde - timedelta(days=dias) <= hoy:
                continue
            con.execute(sa.text(
                """INSERT INTO calendario_avisos (id, barra_id, dias_antes, destinatarios, creado_por_id, control)
                   VALUES (:id, :b, :dias, '[]'::jsonb, :creado_por, :control)
                   ON CONFLICT (id) DO NOTHING"""
            ), {
                "id": f"av-{control[:2]}{dias}-{_corto(barra_id)}", "b": barra_id, "dias": dias,
                "creado_por": creado_por, "control": control,
            })
    if barras:
        rev = con.execute(sa.text("UPDATE calendario_revision SET rev = rev + 1 WHERE id = 1 RETURNING rev")).scalar()
        if rev is not None:
            con.execute(sa.text(
                """INSERT INTO calendario_revision_mundo (mundo, rev) VALUES ('redexpres', :rev)
                   ON CONFLICT (mundo) DO UPDATE SET rev = EXCLUDED.rev"""
            ), {"rev": rev})


def downgrade() -> None:
    op.execute("DELETE FROM calendario_avisos WHERE control IS NOT NULL")
    op.drop_column("calendario_avisos", "control")
