"""El calendario de Core Tienda en Outlook, Google Calendar o el iPhone.

Idea aprobada por Ivan el 15/11/2026: cada persona ve en el calendario de su
teléfono o de Outlook las acciones de sus mundos y sus tareas, sin entrar a la
plataforma. Encaja con el paso a Microsoft.

Cómo funciona: Outlook (o Google, o el iPhone) se "suscribe" a un link y lo
vuelve a leer solo cada tanto. Ese pedido no trae sesión, así que el link lleva
una firma: el id de la persona y un HMAC con la clave del servidor y su
`calendario_link_version`. Quien no tiene el link exacto no ve nada (404).
"Generar otro link" sube el número y el anterior deja de andar.

Lo que sale es de solo lectura y respeta lo mismo que la pantalla: calendario
habilitado, solo los mundos que la persona puede abrir. Va desde dos meses
atrás hasta un año adelante; para una cuenta externa (la agencia, 0069), solo
su ventana alrededor del mes actual (app/core/externos.py), igual que en la
pantalla: el link lo puede pegar en cualquier calendario y no puede ser la
puerta de atrás para ver lo que viene en tres meses.
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import externos
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.mundos import MUNDOS, mundos_de, puede_abrir
from app.models.calendario import CalendarioBarra, CalendarioTarea
from app.models.user import User
from app.services.calendario_avisos import puede_ver_el_calendario

router = APIRouter(prefix="/calendario", tags=["calendario"])

DIAS_PARA_ATRAS = 60
DIAS_PARA_ADELANTE = 400
_CANALES = {"email": "mail", "whatsapp": "WhatsApp", "push": "push"}


# ---------------------------------------------------------------------------
# La firma del link
# ---------------------------------------------------------------------------

def _clave() -> bytes:
    return (settings.JWT_SECRET_KEY or settings.APP_SECRET_KEY).encode()


def firma_del_link(user_id: int, version: int) -> str:
    mensaje = f"core-tienda-calendario:{user_id}:{version}".encode()
    return hmac.new(_clave(), mensaje, hashlib.sha256).hexdigest()[:40]


def ruta_del_link(usuario: User) -> str:
    return f"/calendario/ical/{usuario.id}/{firma_del_link(usuario.id, usuario.calendario_link_version or 0)}.ics"


# ---------------------------------------------------------------------------
# El archivo .ics (RFC 5545), sin dependencias
# ---------------------------------------------------------------------------

def escapar(texto: str) -> str:
    return (
        texto.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


def plegar(linea: str) -> str:
    """Las líneas de un .ics no pasan de 75 bytes: las largas siguen en la
    próxima con un espacio adelante. Sin cortar una letra con tilde al medio."""
    partes: list[str] = []
    actual, tam, limite = "", 0, 75
    for letra in linea:
        largo = len(letra.encode("utf-8"))
        if tam + largo > limite:
            partes.append(actual)
            actual, tam, limite = " ", 1, 75
        actual += letra
        tam += largo
    partes.append(actual)
    return "\r\n".join(partes)


def armar_ics(nombre: str, eventos: list[dict], ahora: datetime) -> str:
    sello = ahora.strftime("%Y%m%dT%H%M%SZ")
    lineas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Tienda Inglesa//Core Tienda//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escapar(nombre)}",
        "X-WR-TIMEZONE:America/Montevideo",
        # Cada cuánto conviene volver a leerlo (Outlook igual decide).
        "REFRESH-INTERVAL;VALUE=DURATION:PT2H",
        "X-PUBLISHED-TTL:PT2H",
    ]
    for e in eventos:
        lineas += [
            "BEGIN:VEVENT",
            f"UID:{e['uid']}",
            f"DTSTAMP:{sello}",
            f"DTSTART;VALUE=DATE:{e['inicio'].strftime('%Y%m%d')}",
            # Fin exclusivo: una acción del 1 al 3 termina el 4 a las 0 h.
            f"DTEND;VALUE=DATE:{(e['fin'] + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{escapar(e['titulo'])}",
        ]
        if e.get("descripcion"):
            lineas.append(f"DESCRIPTION:{escapar(e['descripcion'])}")
        if e.get("url"):
            lineas.append(f"URL:{e['url']}")
        lineas += ["TRANSP:TRANSPARENT", "END:VEVENT"]
    lineas.append("END:VCALENDAR")
    return "\r\n".join(plegar(linea) for linea in lineas) + "\r\n"


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@router.get("/ical/link")
async def mi_link(current_user: User = Depends(require_permission("calendario.view"))):
    """La ruta del link (el front le pone adelante la dirección de la API)."""
    return {"ruta": ruta_del_link(current_user)}


@router.post("/ical/link/nuevo")
async def link_nuevo(
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Otro link: el anterior deja de andar (por si se compartió sin querer)."""
    current_user.calendario_link_version = (current_user.calendario_link_version or 0) + 1
    db.add(current_user)
    return {"ruta": ruta_del_link(current_user)}


@router.get("/ical/{user_id}/{firma}.ics")
async def calendario_ics(user_id: int, firma: str, db: AsyncSession = Depends(get_db)):
    usuario = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if (
        usuario is None
        or not hmac.compare_digest(firma, firma_del_link(user_id, usuario.calendario_link_version or 0))
        or not puede_ver_el_calendario(usuario)
    ):
        # Lo mismo exista o no la persona: el link no dice nada de quién es.
        raise HTTPException(status_code=404, detail="Not found")

    mundos = [m for m in mundos_de(usuario) if puede_abrir(usuario, m)]
    if externos.es_externo(usuario):
        desde, hasta = externos.ventana_de_hoy()
    else:
        hoy = datetime.now(timezone.utc).date()
        desde, hasta = hoy - timedelta(days=DIAS_PARA_ATRAS), hoy + timedelta(days=DIAS_PARA_ADELANTE)
    varios = len(mundos) > 1
    eventos: list[dict] = []

    if mundos:
        barras = (await db.execute(
            select(CalendarioBarra).where(
                CalendarioBarra.mundo.in_(mundos),
                CalendarioBarra.seccion.in_(("comercial", "envio")),
                CalendarioBarra.hasta >= desde,
                CalendarioBarra.desde <= hasta,
            ).order_by(CalendarioBarra.desde)
        )).scalars().all()
        eventos += [_evento_de_accion(b, varios) for b in barras]

        consulta_tareas = (
            select(CalendarioTarea, CalendarioBarra)
            .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
            .where(
                CalendarioTarea.asignado_a_id == usuario.id,
                CalendarioTarea.estado != "hecha",
                CalendarioTarea.vence.is_not(None),
                CalendarioTarea.vence >= desde,
                CalendarioTarea.vence <= hasta,
                CalendarioBarra.mundo.in_(mundos),
            )
        )
        if externos.es_externo(usuario):
            # Además de que venza en la ventana, la acción tiene que tocarla:
            # el título lleva el nombre de la acción.
            consulta_tareas = consulta_tareas.where(
                externos.condicion_de_ventana(CalendarioBarra, (desde, hasta)),
            )
        tareas = (await db.execute(consulta_tareas)).all()
        eventos += [_evento_de_tarea(t, b) for t, b in tareas]

    nombre = "Core Tienda" if varios or not mundos else f"Core Tienda · {MUNDOS.get(mundos[0], mundos[0])}"
    return Response(
        content=armar_ics(nombre, eventos, datetime.now(timezone.utc)),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "private, max-age=900",
            "Content-Disposition": 'inline; filename="core-tienda.ics"',
        },
    )


def _abrir(barra_id: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/calendario?accion={barra_id}"


def _evento_de_accion(b: CalendarioBarra, varios: bool) -> dict:
    prefijo = f"[{MUNDOS.get(b.mundo, b.mundo)}] " if varios else ""
    if b.seccion == "envio":
        canal = _CANALES.get(b.banda, b.banda)
        titulo = f"{prefijo}Envío por {canal}: {b.nombre}" + (f" ({b.hora})" if b.hora else "")
        descripcion = f"{b.formato or 'Envío'} por {canal}."
    else:
        titulo = f"{prefijo}{b.nombre}"
        descripcion = f"Categoría: {b.banda}."
    return {
        "uid": f"accion-{b.id}@coretienda",
        "inicio": b.desde, "fin": b.hasta if b.seccion != "envio" else b.desde,
        "titulo": titulo,
        "descripcion": f"{descripcion}\nAbrir en Core Tienda: {_abrir(b.id)}",
        "url": _abrir(b.id),
    }


def _evento_de_tarea(t: CalendarioTarea, b: CalendarioBarra) -> dict:
    return {
        "uid": f"tarea-{t.id}@coretienda",
        "inicio": t.vence, "fin": t.vence,
        "titulo": f"Tarea: {t.titulo} · {b.nombre}",
        "descripcion": (f"{t.descripcion}\n" if t.descripcion else "") + f"Abrir en Core Tienda: {_abrir(b.id)}",
        "url": _abrir(b.id),
    }
