"""Lanzar FDS y Cierre FDS: los controles de los Super FDS de Redexpres

Pedido de Ivan (18/11/2026): "lanzamiento FDS y cierre FDS tienen que tener
otros tiempos, pero también convirtámoslo en notificación". Cierre FDS en
cada Super FDS, 14 días antes; Lanzar FDS uno por mes, 10 días antes del
primer Super FDS del mes. Tarea y aviso a todo el equipo, como Lanzar y
Cierre (0077). Ver app/services/controles_redexpres.py.

Sin columnas nuevas: a los Super FDS que todavía no arrancaron se les suma lo
que todavía está a tiempo (la tarea si su fecha no pasó, el aviso si todavía
no tendría que haber salido), igual que la 0077.

Revision ID: 0078
Revises: 0077
Create Date: 2026-11-18
"""
import hashlib
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

# Lo mismo que app/services/controles_redexpres.py (copiado: una migración no
# depende del código de la app, que cambia).
CIERRE = ("cf", "cierre_fds", "Cierre FDS", 14, 1,
          "Cerrar este Super FDS: productos y precios definidos. Dos semanas antes.")
LANZAR = ("lf", "lanzar_fds", "Lanzar FDS", 10, 0, "Lanzar los Super FDS del mes. 10 días antes del primero.")


def _corto(texto):
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


def upgrade() -> None:
    con = op.get_bind()
    hoy = datetime.now(timezone(timedelta(hours=-3))).date()
    fds = con.execute(sa.text(
        """SELECT id, desde, creado_por_id FROM calendario_barras
           WHERE mundo = 'redexpres' AND seccion = 'comercial'
             AND lower(regexp_replace(trim(banda), '\\s+', ' ', 'g')) = 'super fds'
           ORDER BY desde, id"""
    )).all()
    primeros = {}
    for barra_id, desde, _ in fds:
        primeros.setdefault((desde.year, desde.month), barra_id)

    def sumar(barra_id, desde, creado_por, control):
        prefijo, clave, titulo, dias, orden, detalle = control
        fecha = desde - timedelta(days=dias)
        ya = {
            (t or "").strip().casefold() for (t,) in con.execute(
                sa.text("SELECT titulo FROM calendario_tareas WHERE barra_id = :b"), {"b": barra_id}
            )
        }
        if titulo.casefold() not in ya and fecha >= hoy:
            con.execute(sa.text(
                """INSERT INTO calendario_tareas
                       (id, barra_id, titulo, descripcion, estado, vence, ancla, ancla_dias, orden, creado_por_id, para)
                   VALUES (:id, :b, :titulo, :detalle, 'pendiente', :vence, 'inicio', :dias, :orden, :creado_por, 'tienda')
                   ON CONFLICT (id) DO NOTHING"""
            ), {
                "id": f"ta-{prefijo}-{_corto(barra_id)}", "b": barra_id, "titulo": titulo, "detalle": detalle,
                "vence": fecha, "dias": -dias, "orden": orden, "creado_por": creado_por,
            })
        if fecha > hoy:
            con.execute(sa.text(
                """INSERT INTO calendario_avisos (id, barra_id, dias_antes, destinatarios, creado_por_id, control)
                   VALUES (:id, :b, :dias, '[]'::jsonb, :creado_por, :control)
                   ON CONFLICT (id) DO NOTHING"""
            ), {
                "id": f"av-{prefijo}{dias}-{_corto(barra_id)}", "b": barra_id, "dias": dias,
                "creado_por": creado_por, "control": clave,
            })

    tocadas = 0
    for barra_id, desde, creado_por in fds:
        if desde <= hoy:
            continue
        sumar(barra_id, desde, creado_por, CIERRE)
        if primeros.get((desde.year, desde.month)) == barra_id:
            sumar(barra_id, desde, creado_por, LANZAR)
        tocadas += 1
    if tocadas:
        rev = con.execute(sa.text("UPDATE calendario_revision SET rev = rev + 1 WHERE id = 1 RETURNING rev")).scalar()
        if rev is not None:
            con.execute(sa.text(
                """INSERT INTO calendario_revision_mundo (mundo, rev) VALUES ('redexpres', :rev)
                   ON CONFLICT (mundo) DO UPDATE SET rev = EXCLUDED.rev"""
            ), {"rev": rev})


def downgrade() -> None:
    op.execute("DELETE FROM calendario_avisos WHERE control IN ('lanzar_fds', 'cierre_fds')")
