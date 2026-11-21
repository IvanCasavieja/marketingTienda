"""Que el servidor no se duerma (Ivan, 21/11/2026): cada tanto se pide a sí
mismo /health por la dirección pública (app/services/despierto.py). Sin red:
el pedido se contesta con un transporte simulado de httpx."""
import asyncio

import httpx

from app.services import despierto


def test_la_direccion_es_la_configurada_o_la_de_render():
    assert despierto.direccion_publica("https://core.example/ ", {}) == "https://core.example"
    assert despierto.direccion_publica("", {"RENDER_EXTERNAL_URL": "https://marketingtienda.onrender.com"}) \
        == "https://marketingtienda.onrender.com"
    # La configurada manda sobre la de Render.
    assert despierto.direccion_publica("https://core.example", {"RENDER_EXTERNAL_URL": "https://otra.example"}) \
        == "https://core.example"
    # Sin ninguna (una PC, las pruebas), o algo que no es una dirección: nada.
    assert despierto.direccion_publica("", {}) is None
    assert despierto.direccion_publica("core.example", {}) is None


def _cliente(contestar):
    return httpx.AsyncClient(transport=httpx.MockTransport(contestar))


def test_una_vuelta_pide_health_por_la_direccion_publica():
    pedidos = []

    def contestar(request):
        pedidos.append(str(request.url))
        return httpx.Response(200, json={"status": "ok", "db": "ok"})

    async def probar():
        async with _cliente(contestar) as c:
            return await despierto.una_vuelta(c, "https://marketingtienda.onrender.com")

    assert asyncio.run(probar()) is True
    assert pedidos == ["https://marketingtienda.onrender.com/health"]


def test_una_vuelta_que_falla_no_levanta():
    def caido(request):
        raise httpx.ConnectError("sin red")

    def degradado(request):
        return httpx.Response(503, json={"status": "degraded"})

    async def probar(contestar):
        async with _cliente(contestar) as c:
            return await despierto.una_vuelta(c, "https://core.example")

    assert asyncio.run(probar(caido)) is False
    assert asyncio.run(probar(degradado)) is False


def test_el_loop_pide_cada_tantos_minutos(monkeypatch):
    vueltas, esperas = [], []

    async def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) > 3:
            raise asyncio.CancelledError

    async def una_vuelta(cliente, direccion):
        vueltas.append(direccion)
        return True

    monkeypatch.setattr(despierto.asyncio, "sleep", dormir)
    monkeypatch.setattr(despierto, "una_vuelta", una_vuelta)
    try:
        asyncio.run(despierto.run_despierto_loop("https://core.example", 10))
    except asyncio.CancelledError:
        pass
    # Arranca esperando (recién despierto no hace falta) y pide cada 10 minutos.
    assert esperas == [600, 600, 600, 600]
    assert vueltas == ["https://core.example"] * 3
