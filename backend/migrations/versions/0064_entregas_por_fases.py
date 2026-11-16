"""entregas por fases con rondas de corrección

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-15

Pedido de Ivan (15/11/2026): una tarea "tiene fase 1, fase 2, fase 3…; se
entrega, se aprueba o vuelve con correcciones, la agencia devuelve con las
correcciones aplicadas, puede volver otra vez, hasta que se aprueba". Las
tablas y por qué son así están en app/models/entregas.py.

Todo cuelga de `calendario_tareas` con ON DELETE CASCADE: borrar la tarea (o
la acción) se lleva sus fases, versiones, imágenes, marcas y decisiones.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def _usuario(nombre: str, *, index: bool = False) -> sa.Column:
    return sa.Column(nombre, sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=index)


def _tarea() -> sa.Column:
    return sa.Column(
        "tarea_id", sa.String(64), sa.ForeignKey("calendario_tareas.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )


def _ahora(nombre: str = "created_at") -> sa.Column:
    return sa.Column(nombre, sa.DateTime(timezone=True), server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "calendario_entregas",
        sa.Column(
            "tarea_id", sa.String(64), sa.ForeignKey("calendario_tareas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tipo_pieza", sa.String(20), nullable=False),
        sa.Column("brief", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("aprobadores", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("momento", sa.String(20), nullable=False, server_default="produccion"),
        sa.Column("fase_actual_id", sa.String(64), nullable=True),
        sa.Column("ronda", sa.Integer(), nullable=False, server_default="0"),
        _usuario("aprobador_de_turno_id", index=True),
        _usuario("creado_por_id"),
        _ahora(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "calendario_fases",
        sa.Column("id", sa.String(64), primary_key=True),
        _tarea(),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("aprobada_at", sa.DateTime(timezone=True), nullable=True),
        _ahora(),
    )

    op.create_table(
        "calendario_versiones",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "fase_id", sa.String(64), sa.ForeignKey("calendario_fases.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        _tarea(),
        sa.Column("ronda", sa.Integer(), nullable=False),
        _usuario("subida_por_id"),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("link", sa.String(1000), nullable=True),
        sa.Column("corregidas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("estado", sa.String(20), nullable=False, server_default="revision"),
        sa.Column("decidida_at", sa.DateTime(timezone=True), nullable=True),
        _ahora(),
        sa.UniqueConstraint("fase_id", "ronda", name="uq_calendario_versiones_fase_ronda"),
    )

    op.create_table(
        "calendario_version_imagenes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "version_id", sa.String(64), sa.ForeignKey("calendario_versiones.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tipo_mime", sa.String(20), nullable=False),
        sa.Column("datos", sa.LargeBinary(), nullable=True),
        sa.Column("tipo_mime_miniatura", sa.String(20), nullable=False, server_default="image/jpeg"),
        sa.Column("miniatura", sa.LargeBinary(), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purgada_at", sa.DateTime(timezone=True), nullable=True),
        _ahora(),
    )

    op.create_table(
        "calendario_marcas",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "version_id", sa.String(64), sa.ForeignKey("calendario_versiones.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "imagen_id", sa.String(64), sa.ForeignKey("calendario_version_imagenes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _tarea(),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False, server_default="cambio"),
        _usuario("autor_id"),
        sa.Column("corregida", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("corregida_en_version_id", sa.String(64), nullable=True),
        sa.Column("corregida_at", sa.DateTime(timezone=True), nullable=True),
        _ahora(),
    )

    op.create_table(
        "calendario_decisiones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "version_id", sa.String(64), sa.ForeignKey("calendario_versiones.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        _usuario("aprobador_id"),
        _usuario("decidido_por_id"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        _ahora(),
    )


def downgrade() -> None:
    op.drop_table("calendario_decisiones")
    op.drop_table("calendario_marcas")
    op.drop_table("calendario_version_imagenes")
    op.drop_table("calendario_versiones")
    op.drop_table("calendario_fases")
    op.drop_table("calendario_entregas")
