"""persistir estado entre preview y confirmacion + resultado final de cenefa_jobs

Hasta ahora ese estado vivia SOLO en dicts en memoria del proceso backend
(_job_products/_job_results en jobs.py) -- documentado ahi mismo como una
decision consciente (se probo Redis el 15/07, no habia Redis provisionado
en Render, se revirtio a memoria el 16/07 para no bloquear la herramienta).
Contrapartida ya conocida: un job confirmado justo cuando el backend
redespliega (o si hay mas de una instancia sirviendo trafico) queda
inaccesible -- "el resultado ya fue descargado o el servidor se reinicio"
(410) sin haber sido descargado nunca. Se persiste en Postgres (ya
provisionado, sin costo extra) en vez de reintroducir la dependencia de
Redis que ya se probo fragil en este entorno.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cenefa_jobs", sa.Column("staged_data", postgresql.JSONB(), nullable=True))
    op.add_column("cenefa_jobs", sa.Column("staged_source_pptx", sa.LargeBinary(), nullable=True))
    op.add_column("cenefa_jobs", sa.Column("staged_excel_bytes", sa.LargeBinary(), nullable=True))
    op.add_column("cenefa_jobs", sa.Column("result_bytes", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("cenefa_jobs", "result_bytes")
    op.drop_column("cenefa_jobs", "staged_excel_bytes")
    op.drop_column("cenefa_jobs", "staged_source_pptx")
    op.drop_column("cenefa_jobs", "staged_data")
