"""/health: 503 si la base no contesta O si las migraciones de este arranque
fallaron (código nuevo sobre una base vieja). Es lo que mira Render para dar
por bueno un deploy y lo que mira el monitor de caídas."""
import pytest
from fastapi.testclient import TestClient

import app.core.database as database
import app.main as main


class _SesionQueContesta:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **k):
        return None


@pytest.fixture
def base_que_contesta(monkeypatch):
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _SesionQueContesta())


@pytest.fixture(autouse=True)
def estado_limpio():
    antes = dict(main.migraciones)
    yield
    main.migraciones.clear()
    main.migraciones.update(antes)


def test_todo_bien(base_que_contesta):
    main.migraciones["estado"] = "ok"
    r = TestClient(main.app).get("/health")
    assert r.status_code == 200
    assert r.json()["migraciones"] == "ok"


def test_mientras_corren_las_migraciones_sigue_sano(base_que_contesta):
    """Render mata la instancia si /health no contesta bien al arrancar."""
    main.migraciones["estado"] = "corriendo"
    assert TestClient(main.app).get("/health").status_code == 200


def test_si_las_migraciones_fallaron_da_503(base_que_contesta):
    main.migraciones["estado"] = "error"
    r = TestClient(main.app).get("/health")
    assert r.status_code == 503
    assert r.json() == {**r.json(), "status": "degraded", "db": "ok", "migraciones": "error"}


def test_sin_base_da_503():
    r = TestClient(main.app).get("/health")
    assert r.status_code == 503
    assert r.json()["db"] == "error"
