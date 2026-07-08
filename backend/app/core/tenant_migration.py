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
            view_only   BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """))

    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INTEGER REFERENCES roles(id) ON DELETE SET NULL"
    ))
    # Defensivo — la migración Alembic 0013 ya agrega estas columnas, pero
    # esta función corre después de Alembic en todos los entornos así que
    # llegado este punto ya deberían existir; el IF NOT EXISTS solo cubre el
    # caso de un entorno nuevo donde Alembic todavía no corrió.
    await conn.execute(text(
        "ALTER TABLE roles ADD COLUMN IF NOT EXISTS view_only BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    await conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSON NOT NULL DEFAULT '[]'"
    ))

    for role in DEFAULT_ROLES:
        # ON CONFLICT DO NOTHING — a propósito: esto es un seed inicial, no un
        # sync perpetuo. Si hiciera DO UPDATE, cualquier permiso que un admin
        # haya tildado/destildado a mano para estos roles desde el panel se
        # revertiría en el próximo restart del backend.
        await conn.execute(text("""
            INSERT INTO roles (name, description, permissions, is_system, view_only)
            VALUES (:name, :desc, CAST(:perms AS json), :sys, :view_only)
            ON CONFLICT (name) DO NOTHING
        """), {
            "name": role["name"],
            "desc": role["description"],
            "perms": json.dumps(role["permissions"]),
            "sys": role["is_system"],
            "view_only": role.get("view_only", False),
        })

    # --- Migración de datos: rol "Editor" (eliminado) → "Usuario" ------------
    # Naturalmente idempotente: después de la primera corrida no quedan
    # usuarios con role_id apuntando a "Editor" ni la fila "Editor", así que
    # estas dos sentencias pasan a ser no-op en los restarts siguientes.
    await conn.execute(text("""
        UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'Usuario')
        WHERE role_id = (SELECT id FROM roles WHERE name = 'Editor')
    """))
    await conn.execute(text("DELETE FROM roles WHERE name = 'Editor'"))

    # --- Backfill: users.permissions ahora es la fuente de verdad -----------
    # Solo toca usuarios cuyo permissions sigue en el default '[]' — si ya
    # fueron editados a mano desde el perfil (o su rol no da nada, como
    # Usuario/Viewer) esto no los pisa. Caveat conocido: si alguna vez se
    # destildan A MANO todos los permisos de un usuario con rol Admin, este
    # backfill se los volvería a completar en el próximo restart (Admin
    # siempre tiene permissions no vacíos en su rol) — para dejarlo en cero
    # de verdad hay que bajarle el rol a Usuario.
    await conn.execute(text("""
        UPDATE users u
        SET permissions = r.permissions
        FROM roles r
        WHERE u.role_id = r.id
          AND u.permissions::text = '[]'
          AND r.permissions::text != '[]'
    """))

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
