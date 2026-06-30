import json
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def migrate_roles(conn: AsyncConnection) -> None:
    """Create roles table and seed default roles if they don't exist."""
    from app.models.role import DEFAULT_ROLES

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

    # Si FIRST_SUPERUSER_EMAIL está seteado, promover ese usuario como Superadmin.
    # Si no, promover el primer usuario creado en caso de que no haya ningún superusuario.
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
        await conn.execute(text("""
            UPDATE users
            SET is_superuser = TRUE,
                role_id = (SELECT id FROM roles WHERE name = 'Superadmin' LIMIT 1)
            WHERE id = (SELECT id FROM users ORDER BY id LIMIT 1)
              AND NOT EXISTS (SELECT 1 FROM users WHERE is_superuser = TRUE)
        """))

    # Asignar rol Superadmin a todos los is_superuser sin rol asignado
    await conn.execute(text("""
        UPDATE users
        SET role_id = (SELECT id FROM roles WHERE name = 'Superadmin' LIMIT 1)
        WHERE is_superuser = TRUE AND role_id IS NULL
    """))
