"""Wrapper de migración: maneja el caso donde las tablas ya existen pero
alembic_version no está presente (BD creada sin alembic tracking)."""
import os
import sys

from sqlalchemy import create_engine, inspect, text


def main() -> None:
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("ERROR: DATABASE_URL no está configurado", file=sys.stderr)
        sys.exit(1)

    # Alembic necesita driver sync (psycopg2)
    sync_url = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    engine = create_engine(sync_url)
    with engine.connect() as conn:
        tables = inspect(engine).get_table_names()

        if "alembic_version" not in tables and "teams" in tables:
            # La BD tiene las tablas de 0001 pero no tiene tracking de alembic.
            # Stampeamos en 0001 para que upgrade solo aplique las migraciones nuevas.
            print("alembic_version no encontrada — stampeando en revision 0001...")
            conn.execute(text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL CONSTRAINT alembic_version_pkc PRIMARY KEY)"
            ))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0001')"))
            conn.commit()
            print("Stamp 0001 aplicado.")

    engine.dispose()

    # Correr migraciones pendientes
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    print("Migraciones completadas.")


if __name__ == "__main__":
    main()
