"""
Crea un usuario por sucursal de Redexpres — el "email" (login) es
literalmente el nombre del local (ej. "Nativo Florida"), la contraseña es
el mismo texto. Sin rol ni permisos: el acceso a "Mi pedido" lo da
directamente tener una fila en LocalAsignacion, no un permiso.

Idempotente — se puede correr de nuevo sin duplicar: si ya existe un User
con ese email, lo saltea. Si el local ya está asignado a OTRO usuario, no
lo toca y lo reporta al final (mantiene 1 usuario = 1 sucursal aunque el
modelo no lo fuerce a nivel de DB).

Uso: python backend/scripts/create_sucursal_users.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.local_asignacion import LocalAsignacion
from app.api.routes.redexpres import LOCALES


async def main():
    creados = 0
    salteados = 0
    conflictos: list[str] = []

    async with AsyncSessionLocal() as db:
        for local in LOCALES:
            existing_user = await db.execute(select(User).where(User.email == local))
            if existing_user.scalar_one_or_none():
                salteados += 1
                continue

            existing_asig = await db.execute(
                select(LocalAsignacion).where(LocalAsignacion.local_nombre == local)
            )
            if existing_asig.scalar_one_or_none():
                conflictos.append(local)
                continue

            user = User(
                email=local,
                full_name=local,
                hashed_password=hash_password(local),
                is_active=True,
                is_superuser=False,
                permissions=[],
            )
            db.add(user)
            await db.flush()  # necesito user.id antes de crear la asignación

            db.add(LocalAsignacion(user_id=user.id, local_nombre=local))
            creados += 1

        await db.commit()

    print(f"Locales totales: {len(LOCALES)}")
    print(f"Usuarios creados: {creados}")
    print(f"Ya existían (salteados): {salteados}")
    if conflictos:
        print(f"Locales con asignación previa a otro usuario (no tocados): {len(conflictos)}")
        for c in conflictos:
            print(f"  - {c}")


if __name__ == "__main__":
    asyncio.run(main())
