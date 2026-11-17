"""Mi agenda: el calendario de cada persona adentro de Core Tienda.

Pedido de Ivan (17/11/2026): "que la gente pueda importar su propio
calendario a la aplicación y que se vaya actualizando con los eventos que
vayan agregando". Y no al revés: "no me gusta que las acciones del calendario
de Tienda puedan estar en un calendario cualquiera" (por eso se sacó el link
que llevaba las acciones a Outlook).

Cada persona pega una vez el link de su calendario:

- Outlook: Configuración → Calendario → Calendarios compartidos → Publicar un
  calendario (con "Todos los detalles") → el link ICS.
- Google: Configuración → su calendario → "Dirección secreta en formato iCal".

El servidor lo lee, guarda los eventos de dos meses atrás a un año adelante y
lo vuelve a leer cuando alguien mira la agenda y pasaron 15 minutos. Solo los
ve su dueño (ver app/api/routes/mi_agenda.py). Las reuniones que se repiten
se expanden con `recurring_ical_events`.

El servidor sale a buscar un link que pegó una persona, así que se cuida:
solo https, solo a servidores de internet (no a direcciones internas como
localhost, 10.x o 192.168.x, ni en ninguna redirección), con tope de tamaño,
de tiempo y de redirecciones.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

MAX_BYTES = 5 * 1024 * 1024
TIEMPO_SEGUNDOS = 15.0
MAX_REDIRECCIONES = 3
VIGENCIA = timedelta(minutes=15)
DIAS_ATRAS = 60
DIAS_ADELANTE = 400
MAX_EVENTOS = 3000
LARGO_URL = 2000
_LARGO_TEXTO = 200
# Un evento "flotante" (sin zona) es de la hora de acá.
_URUGUAY = ZoneInfo("America/Montevideo")
_REDIRECCIONES = (301, 302, 303, 307, 308)


class AgendaInvalida(ValueError):
    """Algo del link o del calendario, con el mensaje para la persona."""


def normalizar_url(texto: str | None) -> str:
    """El link, listo para pedir: webcal:// pasa a https://; cualquier otra
    cosa que no sea https no se acepta. Pura."""
    url = (texto or "").strip()
    if not url:
        raise AgendaInvalida("Pegá el link de tu calendario")
    if len(url) > LARGO_URL:
        raise AgendaInvalida("El link es demasiado largo")
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    partes = urlsplit(url)
    if partes.scheme.lower() != "https" or not partes.hostname:
        raise AgendaInvalida("El link tiene que empezar con https:// (o webcal://)")
    return url


def ip_publica(ip: str) -> bool:
    """Si una dirección es de internet: ni privada, ni local, ni reservada. Pura."""
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return direccion.is_global and not direccion.is_multicast


async def exigir_host_publico(url: str) -> None:
    host = urlsplit(url).hostname
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise AgendaInvalida("No se encontró el servidor de ese link: revisá que esté bien copiado")
    if not infos or not all(ip_publica(info[4][0]) for info in infos):
        raise AgendaInvalida("Ese link no apunta a un calendario de internet")


async def bajar(url: str) -> bytes:
    """El contenido del link, siguiendo pocas redirecciones y controlando cada una."""
    actual = url
    async with httpx.AsyncClient(
        timeout=TIEMPO_SEGUNDOS, follow_redirects=False, headers={"User-Agent": "CoreTienda-Agenda/1.0"},
    ) as cliente:
        for _ in range(MAX_REDIRECCIONES + 1):
            await exigir_host_publico(actual)
            async with cliente.stream("GET", actual) as respuesta:
                if respuesta.status_code in _REDIRECCIONES and respuesta.headers.get("location"):
                    actual = normalizar_url(str(httpx.URL(actual).join(respuesta.headers["location"])))
                    continue
                if respuesta.status_code != 200:
                    raise AgendaInvalida(
                        f"El calendario no se pudo leer (el servidor contestó {respuesta.status_code}). "
                        "Revisá que siga publicado."
                    )
                datos = bytearray()
                async for parte in respuesta.aiter_bytes():
                    datos += parte
                    if len(datos) > MAX_BYTES:
                        raise AgendaInvalida("El calendario es demasiado grande para leerlo")
                return bytes(datos)
    raise AgendaInvalida("El link redirige demasiadas veces")


def _texto(valor) -> str | None:
    limpio = " ".join(str(valor or "").split())
    return limpio[:_LARGO_TEXTO] or None


def _a_iso(valor) -> tuple[str, bool]:
    """(fecha u hora en ISO, si es de todo el día). Las horas van en UTC."""
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=_URUGUAY)
        return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), False
    return valor.isoformat(), True


def leer_eventos(datos: bytes, hoy: date) -> list[dict]:
    """Los eventos del calendario entre dos meses atrás y un año adelante, con
    las repeticiones ya expandidas y sin los cancelados. Pura."""
    try:
        calendario = icalendar.Calendar.from_ical(datos)
    except Exception:
        raise AgendaInvalida("Ese link no es un calendario: tiene que ser el link ICS o iCal")
    if calendario.name != "VCALENDAR":
        raise AgendaInvalida("Ese link no es un calendario: tiene que ser el link ICS o iCal")
    desde = hoy - timedelta(days=DIAS_ATRAS)
    hasta = hoy + timedelta(days=DIAS_ADELANTE)
    try:
        ocurrencias = recurring_ical_events.of(calendario).between(desde, hasta)
    except Exception:
        raise AgendaInvalida("No se pudo leer el calendario: hay algo que no se entiende en sus eventos")

    eventos: list[dict] = []
    for evento in ocurrencias:
        if str(evento.get("STATUS", "")).upper() == "CANCELLED":
            continue
        dtstart = evento.get("DTSTART")
        if dtstart is None:
            continue
        inicio = dtstart.dt
        if evento.get("DTEND") is not None:
            fin = evento.get("DTEND").dt
        elif evento.get("DURATION") is not None:
            fin = inicio + evento.get("DURATION").dt
        else:
            fin = inicio
        inicio_iso, todo_el_dia = _a_iso(inicio)
        fin_iso, _ = _a_iso(fin)
        eventos.append({
            "uid": (_texto(evento.get("UID")) or "")[:_LARGO_TEXTO],
            "titulo": _texto(evento.get("SUMMARY")) or "(sin título)",
            "inicio": inicio_iso,
            "fin": fin_iso,
            "todoElDia": todo_el_dia,
            "lugar": _texto(evento.get("LOCATION")),
        })
        if len(eventos) >= MAX_EVENTOS:
            break
    eventos.sort(key=lambda e: (e["inicio"], e["titulo"]))
    return eventos


async def traer(url: str, hoy: date) -> list[dict]:
    """Baja el calendario del link y devuelve sus eventos. AgendaInvalida con
    el motivo, si no se puede."""
    try:
        datos = await bajar(url)
    except AgendaInvalida:
        raise
    except httpx.HTTPError:
        raise AgendaInvalida("No se pudo conectar con el calendario. Revisá el link y probá de nuevo.")
    return await asyncio.to_thread(leer_eventos, datos, hoy)
