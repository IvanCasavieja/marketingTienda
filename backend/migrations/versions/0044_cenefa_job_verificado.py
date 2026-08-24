"""marcar una corrida como verificada por una persona

La validacion automatica dice si una cenefa se pudo armar, no si quedo bien.
Para eso hace falta que alguien abra el PPTX y lo confirme, y que esa
confirmacion quede registrada: el informe de produccion tiene que poder
separar "el motor no encontro problemas" de "una persona lo miro y esta bien".

Se marca la CORRIDA entera, no cada cenefa: una corrida es un archivo que se
abre y se revisa de una, y marcar 29.000 cenefas de a una no lo haria nadie.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-24

"""
import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cenefa_jobs",
        sa.Column("verificado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "cenefa_jobs",
        sa.Column("verificado_por", sa.Integer(), nullable=True),
    )
    op.add_column(
        "cenefa_jobs",
        sa.Column("verificado_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cenefa_jobs_verificado_por_users", "cenefa_jobs", "users",
        ["verificado_por"], ["id"], ondelete="SET NULL",
    )
    # El informe filtra y agrupa por esta columna sobre toda la tabla.
    op.create_index("ix_cenefa_jobs_verificado", "cenefa_jobs", ["verificado"])


def downgrade() -> None:
    op.drop_index("ix_cenefa_jobs_verificado", table_name="cenefa_jobs")
    op.drop_constraint("fk_cenefa_jobs_verificado_por_users", "cenefa_jobs", type_="foreignkey")
    op.drop_column("cenefa_jobs", "verificado_at")
    op.drop_column("cenefa_jobs", "verificado_por")
    op.drop_column("cenefa_jobs", "verificado")
