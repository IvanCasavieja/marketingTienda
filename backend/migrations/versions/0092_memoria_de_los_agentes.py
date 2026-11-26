"""la memoria de los agentes y quién firma cada informe de Clientes VIP

Ivan (25/11/2026): los agentes del Escuadrón Lechuza "deben de tener su
propio pensamiento… poder enseñarles, poder darles más información". Y los
informes de Clientes VIP ya no los escribe la plataforma: los escribe
Valentina, la economista del Escuadrón, desde la nube.

- agente_memoria: lo que cada agente aprendió, con de dónde salió (ver
  app/models/agente_memoria.py).
- vip_informes.autor: quién lo escribió («Valentina»; los de antes, «la
  plataforma»).
- vip_detalle: el detalle comprimido de cada carga para Valentina
  (cliente×mes×categoría, cliente×subcategoría, producto×mes, productos). Para
  lo que pidió Emilia (25/11/2026): qué incorporó o abandonó cada cliente,
  cómo cambió su frecuencia y su mix, próxima categoría, potencial.
- vip_cliente_valentina: lo que Valentina publica de cada cliente (riesgo de
  abandono, próxima categoría, potencial, qué descubrió y qué dejó, acción).
- users.clave_fija: cuenta de agente, sin cambio de contraseña (ni al entrar
  ni cada 60 días). Solo el superadmin la crea así (Ivan, 25/11/2026).

Revision ID: 0092
Revises: 0091
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agente_memoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agente", sa.String(40), nullable=False),
        sa.Column("ambito", sa.String(40), nullable=False),
        sa.Column("tema", sa.String(120), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("fuente", sa.String(240), nullable=False, server_default=""),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agente_memoria_ambito", "agente_memoria", ["ambito"])
    op.add_column("vip_informes", sa.Column("autor", sa.String(60), nullable=False, server_default="la plataforma"))
    op.add_column("users", sa.Column("clave_fija", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "vip_detalle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("carga_id", sa.Integer(), sa.ForeignKey("vip_cargas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("parte", sa.Integer(), nullable=False),
        sa.Column("filas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("datos", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_vip_detalle_carga_id", "vip_detalle", ["carga_id"])
    op.create_table(
        "vip_cliente_valentina",
        sa.Column("id_cliente", sa.BigInteger(), primary_key=True),
        sa.Column("mes", sa.Date(), nullable=False),
        sa.Column("riesgo_abandono", sa.Float(), nullable=True),
        sa.Column("proxima_categoria", sa.String(120), nullable=True),
        sa.Column("probabilidad_proxima", sa.Float(), nullable=True),
        sa.Column("potencial_mensual", sa.Integer(), nullable=True),
        sa.Column("descubrio", sa.String(400), nullable=True),
        sa.Column("dejo", sa.String(400), nullable=True),
        sa.Column("frecuencia", sa.String(240), nullable=True),
        sa.Column("mix", sa.String(400), nullable=True),
        sa.Column("accion", sa.String(400), nullable=True),
        sa.Column("actualizado", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_column("users", "clave_fija")
    op.drop_table("vip_cliente_valentina")
    op.drop_index("ix_vip_detalle_carga_id", table_name="vip_detalle")
    op.drop_table("vip_detalle")
    op.drop_column("vip_informes", "autor")
    op.drop_index("ix_agente_memoria_ambito", table_name="agente_memoria")
    op.drop_table("agente_memoria")
