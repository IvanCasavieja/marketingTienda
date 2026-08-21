from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# Nombre del schema de Postgres que aísla los datos de staging de los de
# producción -- misma DATABASE_URL/Supabase para las dos, separadas por
# schema (no hay una base de datos física distinta). Ver migrations/env.py
# para el CREATE SCHEMA + las migraciones apuntadas acá mismo.
STAGING_SCHEMA = "staging"

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=15,
    max_overflow=20,
    pool_recycle=3600,
    echo=settings.APP_ENV == "development",
    # statement_cache_size=0: requerido si DATABASE_URL apunta al pooler de
    # Supabase en modo "transaction" (puerto 6543) -- ese modo no soporta
    # prepared statements (cada query puede rutear a una conexion fisica
    # distinta del lado del pooler), asyncpg necesita este flag para no
    # romper con DuplicatePreparedStatementError. Inocuo si se sigue usando
    # el modo "session" (5432): ahi los prepared statements SI funcionan,
    # esto solo apaga el cacheo del lado del cliente (costo minimo).
    connect_args={"statement_cache_size": 0},
)

if settings.APP_ENV == "staging":
    # Fija el schema activo en CADA checkout de conexión del pool, no solo
    # al conectar -- intento previo (?schema=staging en la URL) además de no
    # ser un parámetro válido de asyncpg, tenía el mismo problema de fondo:
    # en el pooler de Supabase en modo "transaction" (ver connect_args de
    # arriba) la conexión física de Postgres detrás de una misma conexión
    # asyncpg puede reciclarse entre transacciones, así que un search_path
    # fijado una sola vez al conectar se podía perder a mitad de camino.
    # Re-fijarlo en "checkout" (se dispara en cada préstamo de conexión del
    # pool, no una sola vez por conexión física) sobrevive a ese reciclado.
    @event.listens_for(engine.sync_engine, "checkout")
    def _set_staging_search_path(dbapi_connection, connection_record, connection_proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET search_path TO {STAGING_SCHEMA}")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
