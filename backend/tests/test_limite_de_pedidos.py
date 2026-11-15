"""El límite general de pedidos por minuto (200), con la app de verdad.

Desde FastAPI 0.139 el SlowAPIMiddleware no encontraba las rutas y dejaba todo
sin límite. Estos tests le pegan a una ruta real de la API (sin sesión da 401
antes de tocar la base, así que no hace falta Postgres) y fijan que:
- el límite vuelve a cortar con 429 (y no con un 401 ni dejando pasar todo);
- se cuenta por persona: el balde de una no se lo come otra de la misma IP.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import clave_de_quien_pide, limiter
from app.core.security import create_access_token, create_refresh_token
from app.main import app

RUTA = "/api/v1/calendario/mis-tareas"


@pytest.fixture(autouse=True)
def baldes_vacios():
    limiter.reset()
    yield
    limiter.reset()


def _pegar(cliente, veces, headers=None):
    return [cliente.get(RUTA, headers=headers or {}).status_code for _ in range(veces)]


def test_sin_sesion_el_201_ya_no_pasa():
    cliente = TestClient(app)
    codigos = _pegar(cliente, 201)
    assert codigos[:200] == [401] * 200  # pasan el límite y los frena la falta de sesión
    assert codigos[200] == 429


def _app_sin_base():
    """Una ruta que no toca la base, con el mismo límite que la API de verdad."""
    from fastapi import APIRouter, Depends, FastAPI
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from app.core.rate_limit import limite_general

    mini = FastAPI()
    mini.state.limiter = limiter
    mini.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    rutas = APIRouter()

    @rutas.get("/eco")
    async def eco():
        return {"ok": True}

    mini.include_router(rutas, prefix="/api", dependencies=[Depends(limite_general)])
    return TestClient(mini)


def test_cada_persona_tiene_su_balde_aunque_salgan_por_la_misma_ip():
    cliente = _app_sin_base()
    ana = {"Authorization": f"Bearer {create_access_token(1)}"}
    beto = {"Authorization": f"Bearer {create_access_token(2)}"}
    codigos_ana = [cliente.get("/api/eco", headers=ana).status_code for _ in range(201)]
    assert codigos_ana[:200] == [200] * 200
    assert codigos_ana[200] == 429
    # Beto, desde la misma IP, sigue entrando; y quien no inició sesión también.
    assert cliente.get("/api/eco", headers=beto).status_code == 200
    assert cliente.get("/api/eco").status_code == 200


def _request(headers=None, cookies=None):
    from starlette.requests import Request
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        raw.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    return Request({"type": "http", "method": "GET", "path": RUTA, "headers": raw, "client": ("9.9.9.9", 1)})


def test_la_clave_es_la_persona_por_header_o_por_cookie():
    token = create_access_token(42)
    assert clave_de_quien_pide(_request({"Authorization": f"Bearer {token}"})) == "usuario:42"
    assert clave_de_quien_pide(_request(cookies={"access_token": token})) == "usuario:42"


def test_un_token_trucho_vencido_o_de_renovacion_cae_en_la_ip():
    assert clave_de_quien_pide(_request({"Authorization": "Bearer trucho"})) == "9.9.9.9"
    vencido = create_access_token(42, expires_delta=timedelta(seconds=-5))
    assert clave_de_quien_pide(_request({"Authorization": f"Bearer {vencido}"})) == "9.9.9.9"
    assert clave_de_quien_pide(_request({"Authorization": f"Bearer {create_refresh_token(42)}"})) == "9.9.9.9"
    assert clave_de_quien_pide(_request({"X-Forwarded-For": "200.1.2.3"})) == "200.1.2.3"


def test_el_login_sigue_con_su_propio_limite_por_ip():
    """El login tiene @limiter.limit("10/minute"): el general no se le suma."""
    cliente = TestClient(app)
    codigos = [cliente.post("/api/v1/auth/login", json={"email": "no", "password": "x"}).status_code for _ in range(11)]
    assert codigos[10] == 429
    assert 429 not in codigos[:10]
