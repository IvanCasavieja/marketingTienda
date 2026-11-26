"""GET /admin/espacio (26/11/2026): cuánto ocupa la base y qué la llena.
Solo el superadmin; los demás, aunque administren, reciben 403."""
import os

import pytest

URL = os.environ.get("TEST_DATABASE_URL")

if URL:
    from test_tablero_agencia_api import Cliente, _persona, correr

_con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: esta prueba necesita una base Postgres")


@_con_base
def test_el_superadmin_ve_cuanto_ocupa_la_base_y_los_demas_no():
    async def prueba(d):
        promo = Cliente(d.http, d.promo)  # superadmin
        r = await promo.get("/admin/espacio")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["base_mb"] > 0 and j["tope_mb"] > 0
        assert j["tablas"] and {"tabla", "mb", "filas", "muertas"} <= set(j["tablas"][0])
        assert "users" in {t["tabla"] for t in j["tablas"]}
        assert isinstance(j["archivos"], list)
        assert {"con_archivo", "verificadas_con_archivo", "verificadas_mb", "archivo_mas_viejo"} <= set(j["cenefas"])
        admin = Cliente(d.http, await _persona(d, "Admin sin super", permisos=("platform.admin", "calendario.view")))
        assert (await admin.get("/admin/espacio")).status_code == 403
    correr(prueba)
