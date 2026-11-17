"""Config mínima para que los módulos de la app se puedan importar en los
tests sin una base ni secretos reales.

Settings() se instancia al importar app.core.config, así que las env vars
tienen que existir ANTES de cualquier import de la app — por eso van acá, en
conftest, que pytest ejecuta primero. Son los mismos dummies que usa el CI
para el chequeo de imports (ver .github/workflows/ci.yml).

Casi todos los tests son puros: no tocan la base ni la red. Los que necesitan
Postgres (test_tablero_agencia_api.py, test_agencia_externa_api.py) usan la
base de TEST_DATABASE_URL, en la última migración, y corren adentro de una
transacción que se deshace; sin esa variable se saltean. Desde el 16/11/2026
el CI levanta una base vacía, la migra y los corre (ver
.github/workflows/ci.yml): antes se salteaban siempre, y lo que cuidan —quién
ve qué en el tablero y en el calendario— quedaba sin protección. Nunca contra
producción.
"""
import os
import sys
import pathlib

os.environ.setdefault("APP_SECRET_KEY", "test-dummy-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_dummy")
os.environ.setdefault("ENCRYPTION_KEY", "Y2q_vIGd2FgQ4CqY3Fh3du3ZehOWmx4pVHPfpJC44bA=")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
