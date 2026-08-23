"""agrupar cenefas en lotes

Un lote junta las cenefas que se pidieron de una: varios Excel, cada uno
emparejado con varias plantillas. Cada combinacion sigue siendo un job propio
--reusa el pipeline entero de preview/confirmacion/render sin tocarlo-- y el
lote es solo la etiqueta que los agrupa para previsualizarlos juntos y
descargarlos en un ZIP.

excel_nombre y template_nombre se guardan en vez de deducirse al descargar: el
Excel no se persiste una vez usado, y la plantilla puede borrarse antes de que
alguien baje el resultado. Sin ellos el archivo del ZIP quedaria sin nombre.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-23

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cenefa_jobs", sa.Column("lote_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("cenefa_jobs", sa.Column("excel_nombre", sa.String(255), nullable=True))
    op.add_column("cenefa_jobs", sa.Column("template_nombre", sa.String(255), nullable=True))
    # El listado del lote filtra por esta columna en cada polling del preview.
    op.create_index("ix_cenefa_jobs_lote_id", "cenefa_jobs", ["lote_id"])


def downgrade() -> None:
    op.drop_index("ix_cenefa_jobs_lote_id", table_name="cenefa_jobs")
    op.drop_column("cenefa_jobs", "template_nombre")
    op.drop_column("cenefa_jobs", "excel_nombre")
    op.drop_column("cenefa_jobs", "lote_id")
