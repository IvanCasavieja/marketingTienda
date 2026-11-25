"""El cifrado de las contraseñas, más liviano (25/11/2026).

Ivan: "está como lenta la plataforma… cuando creo un usuario demora". En el
servidor de Render, bcrypt con 12 rondas tardaba ~2,5 s y frenaba a todos.
"""
import asyncio

from passlib.context import CryptContext

from app.core import security


def test_las_nuevas_van_con_10_rondas():
    assert security.hash_password("Clave-de-prueba-1").startswith("$2b$10$")


def test_una_vieja_de_12_se_sigue_aceptando_y_pide_actualizarse():
    vieja = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12).hash("Clave-de-prueba-1")
    assert security.verify_password("Clave-de-prueba-1", vieja)
    assert security.necesita_actualizar(vieja)
    assert not security.necesita_actualizar(security.hash_password("x"))


def test_las_versiones_en_otro_hilo_dan_lo_mismo():
    h = asyncio.run(security.hash_password_async("Clave-de-prueba-1"))
    assert asyncio.run(security.verify_password_async("Clave-de-prueba-1", h))
    assert not asyncio.run(security.verify_password_async("otra", h))
