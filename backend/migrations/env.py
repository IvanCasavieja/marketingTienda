import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import Base

# Importar todos los modelos para que alembic los detecte
from app.models import (  # noqa: F401
    User, PlatformConnection,
    CampaignMetric, AuditLog, AIAnalysis,
    CenefaTemplate, CenefaTemplateV2, CenefaJob,
)

config = context.config

# Configurar el logging SOLO cuando alembic corre desde la terminal. Adentro
# del backend (el lifespan de app/main.py llama a command.upgrade al arrancar)
# el proceso ya tiene su propio logging -- JSON, con sus niveles -- y fileConfig
# se lo pisaba entero: primero apagaba los loggers existentes, incluido el que
# escribe "Alembic migration failed", y despues dejaba todo en nivel WARNING,
# asi que tampoco salia "Alembic migrations completed". Hasta el 10/09/2026 una
# migracion rota en el servidor no dejaba NINGUNA linea en el log: Alembic
# deshacia todo, la base quedaba sin tocar y /health seguia respondiendo 200.
# El backend pide que no se toque el logging con el atributo configure_logger.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Convertir URL async → sync para alembic (usa psycopg2 en vez de asyncpg)
_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
