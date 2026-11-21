"""Que el servidor no se duerma (Ivan, 21/11/2026).

Render, en el plan gratis, apaga el servidor después de 15 minutos sin que
le llegue ningún pedido de afuera, y el primero que entra después espera
casi un minuto a que se despierte (el login quedaba "Ingresando..." sin
contestar). Ivan: "que cada tanto le mandes una señal para que el servidor
parezca que está en línea en todo momento, lo mismo con la base de Supabase,
para evitar que se vuelva a pausar".

Cada MANTENER_DESPIERTO_MIN minutos (10: menos que los 15 de Render) el
servidor se pide a sí mismo /health por su dirección pública. Tiene que ser
por la dirección pública: lo que mantiene despierto a Render es un pedido
que entra desde afuera, y uno interno (localhost) no cuenta. Y /health hace
una consulta a la base (SELECT 1), así que Supabase también ve actividad
cada 10 minutos y no pausa el proyecto (el plan gratis lo pausa después de
una semana sin actividad).

La dirección la pone Render solo en RENDER_EXTERNAL_URL; en otro lado (Azure,
más adelante) se configura URL_PUBLICA. Sin ninguna de las dos, no hace nada.

Ojo con las horas: el plan gratis de Render da 750 horas por mes para todos
los servicios gratis de la cuenta, y uno despierto todo el mes usa unas 744.
Alcanza para este solo.

Si el servidor llegara a dormirse igual (un reinicio de Render, las horas del
mes agotadas), se despierta con el primer pedido que entre, y desde ahí este
loop lo vuelve a mantener despierto. Nunca levanta: un pedido que falla se
anota y se prueba en la vuelta siguiente.
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

# Lo que se espera la respuesta: si el servidor está ocupado, que no se acumulen.
ESPERA = 30.0


def direccion_publica(url_publica: str | None = None, entorno: dict | None = None) -> str | None:
    """La dirección pública del servidor, sin la barra final: URL_PUBLICA si
    está configurada, si no la que pone Render (RENDER_EXTERNAL_URL). None si
    no hay ninguna (una PC, las pruebas). Pura."""
    entorno = os.environ if entorno is None else entorno
    for valor in (url_publica, entorno.get("RENDER_EXTERNAL_URL")):
        valor = (valor or "").strip().rstrip("/")
        if valor.startswith(("http://", "https://")):
            return valor
    return None


async def una_vuelta(cliente: httpx.AsyncClient, direccion: str) -> bool:
    """Un pedido a /health por la dirección pública. True si contestó 200.
    Nunca levanta."""
    try:
        r = await cliente.get(f"{direccion}/health", timeout=ESPERA)
    except Exception as exc:
        logger.warning("despierto: /health no contestó (%s): %s", type(exc).__name__, exc)
        return False
    if r.status_code != 200:
        logger.warning("despierto: /health contestó %s", r.status_code)
        return False
    return True


async def run_despierto_loop(direccion: str, cada_min: int) -> None:
    """El loop: cada `cada_min` minutos, una vuelta. Arranca esperando (recién
    se despertó: no hace falta pedir ya)."""
    logger.info("despierto: cada %d min se pide %s/health para que Render no lo duerma", cada_min, direccion)
    async with httpx.AsyncClient(headers={"User-Agent": "CoreTienda-despierto/1.0"}) as cliente:
        while True:
            await asyncio.sleep(cada_min * 60)
            await una_vuelta(cliente, direccion)
