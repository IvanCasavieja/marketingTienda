"""base de conocimiento del agente de cenefas

Lo que el modulo aprende de lo que se hace todos los dias: que quiso decir una
columna con nombre raro, que plantilla da problemas, que aviso no le sirve a
nadie. Hoy eso vive en la cabeza de quien lo uso y se pierde.

Nada se activa solo. Cada cosa nace como "propuesto", con de donde salio y
cuantas veces se vio; una persona aprueba, descarta o edita. Solo lo aprobado
entra al contexto del agente.

La unicidad es (tipo, clave): es lo que hace que registrar lo mismo dos veces
no cree un duplicado sino que suba el contador. Ver conocimiento.registrar().

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-24

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cenefa_conocimiento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # alias_columna | plantilla | aviso | correccion | preferencia
        sa.Column("tipo", sa.String(40), nullable=False),
        # Identidad normalizada dentro del tipo: dos registros con la misma
        # clave son lo mismo visto dos veces, no dos cosas distintas.
        sa.Column("clave", sa.String(200), nullable=False),
        # La frase que el agente va a leer. En castellano, una sola idea.
        sa.Column("contenido", sa.Text(), nullable=False),
        # Los datos crudos de respaldo, para poder revisar de donde salio.
        sa.Column("detalle", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="{}"),
        # De donde salio: revision_previa | mapeo | grilla | job | manual
        sa.Column("origen", sa.String(60), nullable=False),
        # propuesto | activo | descartado | archivado
        sa.Column("estado", sa.String(20), nullable=False, server_default="propuesto"),
        sa.Column("veces_visto", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("visto_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decidido_por", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decidido_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tipo", "clave", name="uq_cenefa_conocimiento_tipo_clave"),
    )
    # El agente lee lo activo y la pantalla lista lo propuesto: los dos filtran
    # por estado sobre toda la tabla.
    op.create_index("ix_cenefa_conocimiento_estado", "cenefa_conocimiento", ["estado"])


def downgrade() -> None:
    op.drop_index("ix_cenefa_conocimiento_estado", table_name="cenefa_conocimiento")
    op.drop_table("cenefa_conocimiento")
