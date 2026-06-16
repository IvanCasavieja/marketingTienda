"""
Script para crear usuarios de Tienda Inglesa y asignarlos a un grupo.
Ejecutar desde la carpeta backend/:  python scripts/create_tienda_users.py

Requiere el .env configurado en backend/.env
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.team import TeamGroup

# Nombre del grupo al que asignar estos usuarios (debe existir en la BD)
TARGET_GROUP_NAME = "Medios Digitales"

USERS_TO_CREATE = [
    {
        "email":      "adonato@tiendainglesa.com.uy",
        "full_name":  "A. Donato",
        "password":   "Mkt!Ad24#rXkPq9z",
        "is_superuser": False,
    },
    {
        "email":      "dginard@tiendainglesa.com.uy",
        "full_name":  "D. Ginard",
        "password":   "Mkt!Dg24#nLsWv7x",
        "is_superuser": False,
    },
    {
        "email":      "iboretto@tiendainglesa.com.uy",
        "full_name":  "I. Boretto",
        "password":   "Mkt!Ib24#mJqTr5w",
        "is_superuser": False,
    },
]


async def main():
    async with AsyncSessionLocal() as db:
        # Buscar grupo por nombre
        result = await db.execute(
            select(TeamGroup).where(TeamGroup.name == TARGET_GROUP_NAME)
        )
        group = result.scalar_one_or_none()
        if not group:
            print(f"  ERROR  No se encontró el grupo '{TARGET_GROUP_NAME}'")
            print("         Grupos disponibles:")
            all_groups = await db.execute(select(TeamGroup).order_by(TeamGroup.id))
            for g in all_groups.scalars().all():
                print(f"           ID={g.id}  '{g.name}'  ({g.team_type})")
            return

        print(f"  Grupo encontrado: ID={group.id}  '{group.name}'")

        for u in USERS_TO_CREATE:
            existing = await db.execute(select(User).where(User.email == u["email"]))
            existing_user = existing.scalar_one_or_none()

            if existing_user:
                # Actualizar grupo si no está asignado
                if existing_user.team_group_id != group.id:
                    existing_user.team_group_id = group.id
                    db.add(existing_user)
                    print(f"  UPDATE {u['email']} → asignado a '{group.name}'")
                else:
                    print(f"  SKIP   {u['email']} — ya existe y ya está en el grupo correcto")
                continue

            user = User(
                email=u["email"],
                full_name=u["full_name"],
                hashed_password=hash_password(u["password"]),
                is_superuser=u["is_superuser"],
                is_active=True,
                team_group_id=group.id,
            )
            db.add(user)
            await db.flush()
            print(f"  OK     {u['email']}  /  pwd: {u['password']}  /  grupo: '{group.name}'")

        await db.commit()
    print("\nListo. Guardá las contraseñas de arriba antes de cerrar.")


if __name__ == "__main__":
    asyncio.run(main())
