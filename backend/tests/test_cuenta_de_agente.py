"""Cuenta de agente (0092, 25/11/2026): sin cambio de contraseña.

Ivan: «un check… para que el usuario, una vez que yo lo cree, no tenga que
luego cambiar la contraseña después de la primera vez que entra», para la
cuenta de Valentina, que entra sola desde la nube. Cubre también el cambio
cada 60 días (si no, a los dos meses quedaría trabada sin que nadie se
entere). Solo el superadmin la crea, y nunca para una cuenta externa.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core import deps

URL = os.environ.get("TEST_DATABASE_URL")


def _pide(*, clave_fija: bool, primera_vez=False, dias: int | None = None) -> bool:
    cambiada = None if dias is None else datetime.now(timezone.utc) - timedelta(days=dias)
    u = SimpleNamespace(must_change_password=primera_vez, password_changed_at=cambiada, clave_fija=clave_fija)
    return asyncio.run(deps._needs_password_change(u, db=None, es_sucursal=False))


def test_a_una_cuenta_de_agente_no_se_le_pide_cambiar_la_contrasena():
    assert not _pide(clave_fija=True, primera_vez=True)
    assert not _pide(clave_fija=True, dias=400)


def test_a_las_demas_se_les_sigue_pidiendo():
    assert _pide(clave_fija=False, primera_vez=True)
    assert _pide(clave_fija=False, dias=61)
    assert not _pide(clave_fija=False, dias=10)


if URL:
    from app.models.user import User
    from test_tablero_agencia_api import API, Cliente, _persona, correr

_con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")


@_con_base
def test_el_superadmin_crea_la_cuenta_de_agente_y_entra_sin_cambiar_la_contrasena():
    async def prueba(d):
        promo = Cliente(d.http, d.promo)  # superadmin
        email, clave = f"valentina.{d.sufijo}@internal.prueba", "Clave-de-agente-1"
        r = await promo.post("/admin/users", json={"email": email, "full_name": "Valentina Agente", "password": clave,
                                                   "clave_fija": True})
        assert r.status_code == 201, r.text
        nuevo = r.json()["id"]
        async with d.Sesion() as s:
            u = await s.get(User, nuevo)
            assert u.clave_fija is True and u.must_change_password is False
        # Entra con la contraseña que le pusieron y usa la plataforma sin el cambio forzado.
        r = await d.http.post(API + "/auth/login", json={"email": email, "password": clave})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        r = await d.http.get(API + "/guia", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        # Ni a los 100 días se le pide.
        async with d.Sesion() as s:
            (await s.get(User, nuevo)).password_changed_at = datetime.now(timezone.utc) - timedelta(days=100)
            await s.commit()
        assert (await d.http.get(API + "/guia", headers={"Authorization": f"Bearer {token}"})).status_code == 200
        # En la lista del panel se ve que es de agente.
        lista = {x["id"]: x for x in (await promo.get("/admin/users")).json()}
        assert lista[nuevo]["clave_fija"] is True

        # Una común: la primera vez sí se le pide.
        r = await promo.post("/admin/users", json={"email": f"comun.{d.sufijo}@ti.uy", "full_name": "Comun",
                                                   "password": "Clave-comun-12"})
        assert r.status_code == 201
        r = await d.http.post(API + "/auth/login", json={"email": f"comun.{d.sufijo}@ti.uy", "password": "Clave-comun-12"})
        t2 = r.json().get("access_token")
        r = await d.http.get(API + "/guia", headers={"Authorization": f"Bearer {t2}"})
        assert r.status_code == 403 and "PASSWORD_CHANGE_REQUIRED" in r.text
    correr(prueba)


@_con_base
def test_solo_el_superadmin_y_nunca_una_externa():
    async def prueba(d):
        gestor = Cliente(d.http, await _persona(d, "Gestor Agentes", permisos=("platform.users.manage", "calendario.view")))
        r = await gestor.post("/admin/users", json={"email": f"x.{d.sufijo}@internal.prueba", "full_name": "X",
                                                    "password": "Clave-de-agente-1", "clave_fija": True})
        assert r.status_code == 403
        promo = Cliente(d.http, d.promo)
        r = await promo.post("/admin/users", json={"email": f"y.{d.sufijo}@pampa.uy", "full_name": "Y",
                                                   "password": "Clave-de-agente-1", "clave_fija": True,
                                                   "es_externo": True, "empresa": "Agencia Y"})
        assert r.status_code == 422
    correr(prueba)
