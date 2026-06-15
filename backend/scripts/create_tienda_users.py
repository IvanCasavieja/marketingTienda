"""
Script para crear usuarios de Tienda Inglesa.
Ejecutar desde la carpeta backend/:  python scripts/create_tienda_users.py

Requiere el .env configurado en backend/.env
"""
import asyncio
import sys
import os

# Asegurar que Python encuentra los módulos de la app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User

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
        for u in USERS_TO_CREATE:
            existing = await db.execute(select(User).where(User.email == u["email"]))
            if existing.scalar_one_or_none():
                print(f"  SKIP  {u['email']} — ya existe")
                continue

            user = User(
                email=u["email"],
                full_name=u["full_name"],
                hashed_password=hash_password(u["password"]),
                is_superuser=u["is_superuser"],
                is_active=True,
            )
            db.add(user)
            await db.flush()
            print(f"  OK    {u['email']}  /  pwd: {u['password']}")

        await db.commit()
    print("\nListo. Guardá las contraseñas de arriba antes de cerrar.")


if __name__ == "__main__":
    asyncio.run(main())
