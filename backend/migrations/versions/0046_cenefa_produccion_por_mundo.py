"""separar la produccion de cenefas por mundo

El informe de produccion contaba todo junto: pruebas, Redexpres y trabajo
facturable en el mismo total. Faltaban tres datos para poder separarlos.

1. `cenefa_jobs.categoria` -- el mundo en el que se genero la corrida.
   Hasta ahora el mundo solo vivia en la plantilla (`cenefa_templates_v2.
   category`), y el job la referencia con ON DELETE SET NULL: al borrar las
   30 plantillas viejas el 23/08 quedaron 237 corridas sin forma de saber a
   que mundo pertenecian. Copiarlo al job en el momento de crearlo corta esa
   dependencia -- borrar una plantilla ya no borra la historia.

   El backfill recupera lo que todavia se puede (los jobs cuyo template_id
   sobrevivio). El resto queda en NULL a proposito: son las corridas de junio
   al 23/08 y no hay dato en ninguna parte para atribuirlas. El informe las
   muestra como "sin clasificar", no las reparte a dedo.

2. `cenefa_destinos.cobrable` -- si el trabajo de ese mundo se valoriza.
   Redexpres no tiene costo, y el mundo de pruebas tampoco. Es del mundo y no
   del job: no se decide corrida por corrida.

3. `cenefa_destinos.cenefas_previas` -- produccion anterior al registro.
   Parrilla y Vinos se hizo entera antes de que el sistema guardara nada
   util, asi que su cifra no se puede medir, solo declarar. Se guarda como
   dato del mundo, separada y etiquetada como declarada, en vez de inventar
   corridas o de repartir las 24.615 sin clasificar.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-25

"""
import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. El mundo, guardado en el job ───────────────────────────────────
    op.add_column("cenefa_jobs", sa.Column("categoria", sa.String(50), nullable=True))
    op.create_index("ix_cenefa_jobs_categoria", "cenefa_jobs", ["categoria"])

    # Lo que todavia se puede recuperar: los jobs cuya plantilla sigue viva.
    op.execute(
        """
        UPDATE cenefa_jobs j
           SET categoria = t.category
          FROM cenefa_templates_v2 t
         WHERE t.id = j.template_id
           AND t.category IS NOT NULL
        """
    )

    # Segunda pasada, por NOMBRE de plantilla. 26 corridas de Mega Rompe
    # Precios quedaron con template_id en NULL (la plantilla se reemplazo
    # despues de generarlas) pero conservan el nombre. Se exige que ese nombre
    # resuelva a un unico mundo: si dos mundos tienen una plantilla que se
    # llama igual, la corrida se queda sin atribuir antes que atribuirse mal.
    op.execute(
        """
        UPDATE cenefa_jobs j
           SET categoria = u.category
          FROM (
                SELECT name, MIN(category) AS category
                  FROM cenefa_templates_v2
                 WHERE category IS NOT NULL
                 GROUP BY name
                HAVING COUNT(DISTINCT category) = 1
               ) u
         WHERE j.categoria IS NULL
           AND j.template_nombre = u.name
        """
    )

    # ── 2. Mundos que no se valorizan ─────────────────────────────────────
    op.add_column(
        "cenefa_destinos",
        sa.Column("cobrable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Redexpres no tiene costo -- decision de Ivan, 2026-08-25.
    op.execute("UPDATE cenefa_destinos SET cobrable = false WHERE slug = 'redexpres'")

    # ── 3. Produccion declarada, anterior al registro ─────────────────────
    op.add_column(
        "cenefa_destinos",
        sa.Column("cenefas_previas", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cenefa_destinos",
        sa.Column("cenefas_previas_nota", sa.String(300), nullable=False, server_default=""),
    )
    # Parrilla y Vinos: ~2.700 cenefas (1.200 x 2 + ~300), cifra que dio Ivan
    # el 2026-08-25. No es medible desde la base: sus plantillas se borraron y
    # sus corridas quedaron sin atribucion.
    op.execute(
        """
        UPDATE cenefa_destinos
           SET cenefas_previas = 2700,
               cenefas_previas_nota = 'Declarada por Ivan el 2026-08-25: '
                                      '1.200 x 2 + ~300. Anterior al registro '
                                      'de plantilla en el job.'
         WHERE slug = 'parrilla_y_vinos'
        """
    )


    # ── 4. El mundo de pruebas ────────────────────────────────────────────
    # Las corridas de prueba se hacian en el mismo mundo que el trabajo real y
    # despues no habia forma de distinguirlas. Con un mundo propio, marcado sin
    # costo, todo lo que se genere ahi queda fuera del total sin que nadie
    # tenga que acordarse de nada.
    op.execute(
        """
        INSERT INTO cenefa_destinos (slug, nombre, descripcion, icono, color, orden, cobrable)
        VALUES ('pruebas', 'Pruebas',
                'Corridas de prueba. No suman al informe de produccion.',
                'Sparkles', 'amber', 999, false)
        ON CONFLICT (slug) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM cenefa_destinos WHERE slug = 'pruebas'")
    op.drop_column("cenefa_destinos", "cenefas_previas_nota")
    op.drop_column("cenefa_destinos", "cenefas_previas")
    op.drop_column("cenefa_destinos", "cobrable")
    op.drop_index("ix_cenefa_jobs_categoria", table_name="cenefa_jobs")
    op.drop_column("cenefa_jobs", "categoria")
