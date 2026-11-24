"""Crea (o pone al día) las cuentas del Equipo nocturno en una base de pruebas.

El servidor de pruebas lo hace solo al arrancar; esto es para la copia local
que levantan los agentes de noche (docs/equipo-nocturno/README.md). Se niega
si no está ENTORNO_DE_PRUEBAS=true: en producción estas cuentas no existen.

Uso, desde backend/ (con la base ya migrada):
    export ENTORNO_DE_PRUEBAS=true
    export CLAVE_EQUIPO_NOCTURNO=... CLAVE_AGENCIA_DE_PRUEBA=... CLAVE_LOCAL_DE_PRUEBA=...
    python scripts/cuentas_de_prueba.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.cuentas_de_prueba import claves_de, preparar  # noqa: E402


async def main() -> None:
    if not settings.ENTORNO_DE_PRUEBAS:
        raise SystemExit("No es el entorno de pruebas (falta ENTORNO_DE_PRUEBAS=true): no se crea nada.")
    async with AsyncSessionLocal() as db:
        for linea in await preparar(db, claves_de(settings)):
            print(linea)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
