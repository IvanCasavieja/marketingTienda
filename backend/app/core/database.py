from time import monotonic

from sqlalchemy import event, exc
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    # Sin pool_pre_ping: probaba la conexión con un viaje extra a la base en
    # CADA pedido, aunque se hubiera usado hace un segundo (medido el
    # 15/11/2026: la pregunta "¿hay cambios?" del calendario, cada 15 s, hacía
    # 13 viajes). Ahora se prueba solo la que estuvo quieta un rato, que es la
    # que el pooler pudo haber cortado: ver _probar_si_estuvo_quieta.
    pool_pre_ping=False,
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

# Una conexión que se devolvió hace menos que esto se usa sin probar.
SEGUNDOS_QUIETA_ANTES_DE_PROBAR = 30.0


@event.listens_for(engine.sync_engine, "checkin")
def _anotar_cuando_se_devolvio(dbapi_connection, connection_record):
    connection_record.info["devuelta"] = monotonic()


@event.listens_for(engine.sync_engine, "checkout")
def _probar_si_estuvo_quieta(dbapi_connection, connection_record, connection_proxy):
    """Lo mismo que pool_pre_ping, pero solo si la conexión estuvo quieta.

    Si la prueba falla, DisconnectionError hace que el pool la tire y abra
    otra (receta de "pessimistic disconnect handling" de SQLAlchemy): quien
    pidió no se entera. Una recién abierta no se prueba."""
    devuelta = connection_record.info.get("devuelta")
    if devuelta is None or monotonic() - devuelta < SEGUNDOS_QUIETA_ANTES_DE_PROBAR:
        return
    try:
        engine.dialect.do_ping(dbapi_connection)
    except Exception as e:
        # La que abra el pool en su lugar es nueva: esa no se prueba.
        connection_record.info.pop("devuelta", None)
        raise exc.DisconnectionError() from e


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
