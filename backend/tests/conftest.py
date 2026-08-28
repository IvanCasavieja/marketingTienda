"""Config mínima para que los módulos de la app se puedan importar en los
tests sin una base ni secretos reales.

Settings() se instancia al importar app.core.config, así que las env vars
tienen que existir ANTES de cualquier import de la app — por eso van acá, en
conftest, que pytest ejecuta primero. Son los mismos dummies que usa el CI
para el chequeo de imports (ver .github/workflows/ci.yml).

Ningún test toca la base ni la red: prueban las funciones puras del motor de
cenefas (parseo de precios, mecánicas, importer, render). Lo que necesita
Postgres se prueba a mano contra producción, no acá.
"""
import os
import sys
import pathlib

os.environ.setdefault("APP_SECRET_KEY", "test-dummy-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_dummy")
os.environ.setdefault("ENCRYPTION_KEY", "Y2q_vIGd2FgQ4CqY3Fh3du3ZehOWmx4pVHPfpJC44bA=")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
