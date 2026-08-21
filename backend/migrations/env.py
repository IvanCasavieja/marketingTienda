import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import Base, STAGING_SCHEMA

# Importar todos los modelos para que alembic los detecte
from app.models import (  # noqa: F401
    User, PlatformConnection,
    CampaignMetric, AuditLog, AIAnalysis,
    CenefaTemplate, CenefaTemplateV2, CenefaJob,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Convertir URL async → sync para alembic (usa psycopg2 en vez de asyncpg)
_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata

# Mismo aislamiento por schema que app/core/database.py (ver ahí el porqué)
# -- acá alcanza con fijarlo una sola vez al conectar, sin el event listener
# de "checkout" que usa la app: la migración corre de punta a punta en una
# única conexión/transacción larga, no atraviesa el reciclado de conexión
# del pooler que sí afecta a las conexiones de vida larga de la app.
# version_table_schema separa el tracking de versión de Alembic (tabla
# alembic_version) por schema -- sin esto, staging y producción pisarían la
# misma fila de versión y cada una vería el historial de migraciones de la
# otra como ya aplicado/pendiente incorrectamente.
_STAGING = settings.APP_ENV == "staging"


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema=STAGING_SCHEMA if _STAGING else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    connect_args = {"options": f"-c search_path={STAGING_SCHEMA}"} if _STAGING else {}
    connectable = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    with connectable.connect() as connection:
        if _STAGING:
            # El schema no existe hasta que alguien lo crea -- Postgres no lo
            # hace solo. Tiene que pasar ANTES de configurar el contexto de
            # Alembic: las tablas de destino (incluida alembic_version, por
            # version_table_schema) se crean ahí adentro.
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {STAGING_SCHEMA}"))
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table_schema=STAGING_SCHEMA if _STAGING else None,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
