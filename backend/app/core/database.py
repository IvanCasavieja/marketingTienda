from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

_db_url = settings.DATABASE_URL
if settings.APP_ENV == "staging" and "?schema=" not in _db_url:
    _db_url += "?schema=staging"

engine = create_async_engine(
    _db_url,
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
