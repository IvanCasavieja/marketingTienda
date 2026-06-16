import json
import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.security import encrypt_token

DEFAULT_TEAM_NAME = "Tienda Inglesa"
DEFAULT_TEAM_SLUG = "tienda-inglesa"
DEFAULT_GROUP_NAME = "Medios Digitales"


async def migrate_roles(conn: AsyncConnection) -> None:
    """Create roles table and seed default roles if they don't exist."""
    from app.models.role import ALL_PERMISSIONS, DEFAULT_ROLES

    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS roles (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) UNIQUE NOT NULL,
            description VARCHAR(500) NOT NULL DEFAULT '',
            permissions JSON NOT NULL DEFAULT '[]',
            is_system   BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """))

    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INTEGER REFERENCES roles(id) ON DELETE SET NULL"
    ))

    for role in DEFAULT_ROLES:
        await conn.execute(text("""
            INSERT INTO roles (name, description, permissions, is_system)
            VALUES (:name, :desc, CAST(:perms AS json), :sys)
            ON CONFLICT (name) DO UPDATE
                SET description = EXCLUDED.description,
                    permissions  = EXCLUDED.permissions,
                    is_system    = EXCLUDED.is_system
        """), {
            "name": role["name"],
            "desc": role["description"],
            "perms": json.dumps(role["permissions"]),
            "sys": role["is_system"],
        })

    # Bootstrap: si no existe ningún superusuario, promover el primer usuario
    # (o el indicado por FIRST_SUPERUSER_EMAIL) como Superadmin.
    import os
    first_su_email = os.environ.get("FIRST_SUPERUSER_EMAIL", "").strip().lower()
    if first_su_email:
        await conn.execute(text("""
            UPDATE users
            SET is_superuser = TRUE,
                role_id = (SELECT id FROM roles WHERE name = 'Superadmin' LIMIT 1)
            WHERE LOWER(email) = :email
              AND (
                NOT EXISTS (SELECT 1 FROM users WHERE is_superuser = TRUE)
                OR LOWER(email) = :email
              )
        """), {"email": first_su_email})
    else:
        # Promover el primer usuario creado si no hay ningún superusuario
        await conn.execute(text("""
            UPDATE users
            SET is_superuser = TRUE,
                role_id = (SELECT id FROM roles WHERE name = 'Superadmin' LIMIT 1)
            WHERE id = (SELECT id FROM users ORDER BY id LIMIT 1)
              AND NOT EXISTS (SELECT 1 FROM users WHERE is_superuser = TRUE)
        """))

    # Assign Superadmin role to all is_superuser users that have no role yet
    await conn.execute(text("""
        UPDATE users
        SET role_id = (SELECT id FROM roles WHERE name = 'Superadmin' LIMIT 1)
        WHERE is_superuser = TRUE AND role_id IS NULL
    """))


async def migrate_default_team(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS teams (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """
        )
    )
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_teams_slug ON teams (slug)"))

    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS team_groups (
                id SERIAL PRIMARY KEY,
                team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                join_code VARCHAR(500) NOT NULL,
                team_type VARCHAR(20) NOT NULL DEFAULT 'medios',
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """
        )
    )
    # AÃ±adir team_type a grupos existentes (si ya existÃ­a la tabla sin esa columna)
    await conn.execute(
        text("ALTER TABLE team_groups ADD COLUMN IF NOT EXISTS team_type VARCHAR(20) NOT NULL DEFAULT 'medios'")
    )

    await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS team_group_id INTEGER"))
    await conn.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint c
                    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                    WHERE c.contype = 'f'
                      AND c.conrelid = 'users'::regclass
                      AND a.attname = 'team_group_id'
                ) THEN
                    ALTER TABLE users
                    ADD CONSTRAINT fk_users_team_group_id
                    FOREIGN KEY (team_group_id) REFERENCES team_groups(id) ON DELETE SET NULL;
                END IF;
            END $$;
            """
        )
    )

    team_id = await conn.scalar(
        text(
            """
            INSERT INTO teams (name, slug)
            VALUES (:name, :slug)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """
        ),
        {"name": DEFAULT_TEAM_NAME, "slug": DEFAULT_TEAM_SLUG},
    )

    group_id = await conn.scalar(
        text(
            """
            SELECT id
            FROM team_groups
            WHERE team_id = :team_id AND name = :name
            LIMIT 1
            """
        ),
        {"team_id": team_id, "name": DEFAULT_GROUP_NAME},
    )
    if not group_id:
        group_id = await conn.scalar(
            text(
                """
                INSERT INTO team_groups (team_id, name, join_code)
                VALUES (:team_id, :name, :join_code)
                RETURNING id
                """
            ),
            {
                "team_id": team_id,
                "name": DEFAULT_GROUP_NAME,
                "join_code": encrypt_token(secrets.token_urlsafe(16)),
            },
        )

    await conn.execute(
        text("UPDATE users SET team_group_id = :group_id WHERE team_group_id IS NULL"),
        {"group_id": group_id},
    )

    await _migrate_owned_table(conn, "platform_connections", group_id)
    await _migrate_owned_table(conn, "campaign_metrics", group_id)


async def _migrate_owned_table(conn: AsyncConnection, table_name: str, default_group_id: int) -> None:
    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS team_group_id INTEGER"))
    has_user_id = await conn.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = :table_name AND column_name = 'user_id'
            )
            """
        ),
        {"table_name": table_name},
    )
    if has_user_id:
        await conn.execute(
            text(
                f"""
                UPDATE {table_name} owned
                SET team_group_id = COALESCE(users.team_group_id, :default_group_id)
                FROM users
                WHERE owned.user_id = users.id
                  AND owned.team_group_id IS NULL
                """
            ),
            {"default_group_id": default_group_id},
        )
    await conn.execute(
        text(f"UPDATE {table_name} SET team_group_id = :group_id WHERE team_group_id IS NULL"),
        {"group_id": default_group_id},
    )
    await conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint c
                    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                    WHERE c.contype = 'f'
                      AND c.conrelid = '{table_name}'::regclass
                      AND a.attname = 'team_group_id'
                ) THEN
                    ALTER TABLE {table_name}
                    ADD CONSTRAINT fk_{table_name}_team_group_id
                    FOREIGN KEY (team_group_id) REFERENCES team_groups(id) ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )
    )
    await conn.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN team_group_id SET NOT NULL"))
    if has_user_id:
        await conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS user_id CASCADE"))

