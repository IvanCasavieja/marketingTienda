"""La foto de colocación: las reglas, sin la base.

Lo que está acá es puro a propósito (se prueba sin Postgres): qué locales le
tocan a cada mundo, en qué estado se muestra cada local, cuánto da el
porcentaje, si una foto es una foto de verdad y cuándo se borra. Las rutas
(api/routes/colocacion.py) lo usan; la purga de abajo es lo único que toca la
base.

Cuánto ocupa (la cuenta que pidió Ivan, con la base gratis de 500 MB)
--------------------------------------------------------------------
Cada foto se achica en el teléfono antes de subir: lado mayor 1024 px en JPEG
calidad 0.6, más una miniatura de 240 px. Una foto de una góndola así pesa
~80-120 KB y la miniatura ~10 KB: contamos 120 KB por foto, las dos juntas.
Postgres no las comprime: un JPEG ya viene comprimido.

- 60 locales × 4 acciones por mes × 1 foto = 240 fotos = ~29 MB por mes.
- Una foto vive desde que se sube (cerca del arranque de la acción) hasta 30
  días después de que la acción termina: algo más de un mes. Es la prueba de
  que se colocó; pasada la acción ya cumplió (el estado de cada local queda).
- En régimen: **~35 MB** con una foto por local; ~100 MB si todos suben las
  tres que se permiten.

La base gratis es de 500 MB para TODA la plataforma (calendario, cenefas,
precios...): si se llena, deja de aceptar escrituras y se cae todo. Por eso hay
dos frenos: un tope para las fotos (COLOCACION_TOPE_MB, 80 MB) y el general de
la base entera (BASE_TOPE_MB, 400 MB, en services/espacio.py). Pasado
cualquiera, el local no puede subir más y se le pide que avise. Si se queda
corto: bajar la retención (COLOCACION_RETENCION_DIAS) o mover las fotos a un
almacenamiento de archivos (Azure Blob, cuando se migre).
"""
from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Uruguay es UTC-3 todo el año (igual que en calendario_avisos): "hoy" y "el
# día en que llegó la foto" son los de acá, no los de Greenwich.
URUGUAY = timezone(timedelta(hours=-3))

# ---------------------------------------------------------------------------
# Qué locales tiene cada mundo
# ---------------------------------------------------------------------------
# El tipo es el de `local_asignaciones.tipo`. Hoy todos los logins de sucursal
# son de Redexpres ('redex'); los de Tienda Inglesa ('tienda') llegan más
# adelante y, cuando los den de alta en el panel de usuarios con ese tipo, el
# pedido de fotos ya los encuentra. Tienda Express, Viajes y Farma no tienen
# locales con login: ahí no se piden fotos.
TIPO_DE_LOCAL_POR_MUNDO: dict[str, str] = {
    "redexpres": "redex",
    "tienda_inglesa": "tienda",
}


def tipo_de_local(mundo: str) -> str | None:
    return TIPO_DE_LOCAL_POR_MUNDO.get(mundo)


# ---------------------------------------------------------------------------
# Los avisos de la campanita
# ---------------------------------------------------------------------------
# Al local: le pidieron una foto, o se la devolvieron. Le llegan por tener el
# local asignado: un login de sucursal no tiene permisos del calendario.
ORIGEN_PEDIDO = "colocacion_pedido"
ORIGEN_DEVUELTA = "colocacion_devuelta"
ORIGENES_DEL_LOCAL = (ORIGEN_PEDIDO, ORIGEN_DEVUELTA)
# A quien pidió: mandaron todos. Uno por pedido, no uno por foto.
ORIGEN_COMPLETA = "colocacion_completa"


# ---------------------------------------------------------------------------
# Estados
# ---------------------------------------------------------------------------
PENDIENTE, ENVIADA, APROBADA, DEVUELTA, ATRASADA = "pendiente", "enviada", "aprobada", "devuelta", "atrasada"
ESTADOS_GUARDADOS = (PENDIENTE, ENVIADA, APROBADA, DEVUELTA)

# Hasta cuántas fotos por local y por pedido. Las devueltas no cuentan: se
# borran cuando el local manda la nueva.
MAX_FOTOS_POR_LOCAL = 3


def limite_por_defecto(desde: date, hoy: date) -> date:
    """El día siguiente al inicio de la acción: la cartelería se pone para el
    arranque y al otro día ya tiene que estar. Si la acción ya arrancó (se
    pide la foto tarde), mañana: un límite que ya pasó dejaría a todos los
    locales atrasados apenas se pide."""
    return max(desde + timedelta(days=1), hoy + timedelta(days=1))


def estado_visible(estado: str, limite: date, hoy: date) -> str:
    """Lo que se muestra de un local: su estado, o "atrasada" si pasó la fecha
    límite y no tiene ninguna foto ni aprobada ni esperando revisión.

    Una foto ENVIADA después del límite no figura como atrasada: el local ya
    cumplió su parte y lo que falta es que promo la mire (se marca "tarde"
    aparte, ver mando_tarde). Si figurara como atrasada, la lista de
    atrasados mezclaría a quien no mandó nada con quien espera que lo revisen,
    y a los que hay que llamar son los primeros."""
    if estado in (PENDIENTE, DEVUELTA) and hoy > limite:
        return ATRASADA
    return estado


def mando_tarde(enviada_at: datetime | None, limite: date, zona) -> bool:
    """Si la última foto llegó después del día límite (en hora de Uruguay)."""
    return enviada_at is not None and enviada_at.astimezone(zona).date() > limite


def resumen(visibles: list[str]) -> dict:
    """Cuántos hay en cada estado y el porcentaje de cumplimiento, que es el
    de los APROBADOS: una foto enviada todavía puede no servir."""
    total = len(visibles)
    cuenta = {e: sum(1 for v in visibles if v == e) for e in (PENDIENTE, ENVIADA, APROBADA, DEVUELTA, ATRASADA)}
    return {
        "total": total,
        "pendientes": cuenta[PENDIENTE],
        "enviadas": cuenta[ENVIADA],
        "aprobadas": cuenta[APROBADA],
        "devueltas": cuenta[DEVUELTA],
        "atrasadas": cuenta[ATRASADA],
        "porcentaje": round(100 * cuenta[APROBADA] / total) if total else 0,
    }


def puede_subir(estado: str) -> bool:
    """Una vez aprobada no se toca: es la prueba de que se colocó."""
    return estado in (PENDIENTE, ENVIADA, DEVUELTA)


def mandaron_todos(estados: list[str]) -> bool:
    """Si todos los locales mandaron (o ya tienen aprobada) su foto: es lo que
    dispara el único aviso a quien pidió."""
    return bool(estados) and all(e in (ENVIADA, APROBADA) for e in estados)


def estado_al_sacar_la_ultima(estado: str, comentario: str | None) -> str:
    """Si el local saca su última foto antes de que la revisen, vuelve a como
    estaba: devuelta si se la habían devuelto alguna vez (sigue teniendo que
    arreglar algo), pendiente si no."""
    if estado != ENVIADA:
        return estado
    return DEVUELTA if comentario else PENDIENTE


# ---------------------------------------------------------------------------
# Las imágenes
# ---------------------------------------------------------------------------
# El teléfono la achica a ~1280 px y ~250 KB. 3 MB deja margen de sobra para
# una foto que no pasó por ahí (un PNG, un teléfono viejo) sin dejar subir
# cualquier cosa.
MAX_BYTES_FOTO = 3 * 1024 * 1024
MAX_BYTES_MINIATURA = 300 * 1024
# Más de esto no es una foto achicada (una de 1280 px son 1,2 millones), y
# decodificarla le cuesta memoria al servidor: una "bomba" de pocos KB puede
# declarar 100.000 × 100.000 px. 12 millones deja pasar la foto entera de un
# teléfono que no la achicó (4000 × 3000).
MAX_PIXELES = 12_000_000
MIN_LADO = 64
LADO_MINIATURA = 320

_FORMATO_DE_PILLOW = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def tipo_real(datos: bytes) -> str | None:
    """El tipo según los primeros bytes (los "bytes mágicos"), no según lo que
    dice el navegador ni el nombre del archivo, que se pueden inventar."""
    if datos[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(datos) >= 12 and datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


class ImagenInvalida(ValueError):
    """Una foto que no se acepta. El mensaje es para la persona."""


@dataclass(frozen=True)
class Imagen:
    tipo: str
    ancho: int
    alto: int


def validar_imagen(datos: bytes, maximo: int = MAX_BYTES_FOTO, que: str = "La foto") -> Imagen:
    """La foto si es una JPEG, PNG o WebP de verdad y de un tamaño razonable.
    Si no, ImagenInvalida con el mensaje para la persona.

    Además de los bytes mágicos se decodifica con Pillow: un archivo que
    empieza bien pero está cortado (se cayó la señal a mitad de la subida) o
    que es otra cosa con la cabecera de un JPEG no pasa. `verify()` no
    alcanza: con un JPEG cortado no dice nada. Un JPEG se decodifica a un
    octavo del tamaño (`draft`), que lee el archivo entero igual y no gasta
    memoria en la foto grande."""
    if not datos:
        raise ImagenInvalida(f"{que} llegó vacía. Probá de nuevo.")
    if len(datos) > maximo:
        raise ImagenInvalida(
            f"{que} pesa {len(datos) / 1024 / 1024:.1f} MB y el máximo es {maximo / 1024 / 1024:.0f} MB."
            if maximo >= 1024 * 1024 else
            f"{que} pesa {len(datos) // 1024} KB y el máximo es {maximo // 1024} KB."
        )
    tipo = tipo_real(datos)
    if tipo is None:
        raise ImagenInvalida(f"{que} no es una imagen JPEG, PNG o WebP.")
    from PIL import Image
    try:
        with Image.open(io.BytesIO(datos)) as im:
            formato, (ancho, alto) = im.format, im.size
            if ancho * alto > MAX_PIXELES:
                raise ImagenInvalida(f"{que} es demasiado grande ({ancho}×{alto}).")
            if formato == "JPEG":
                im.draft("RGB", (max(1, ancho // 8), max(1, alto // 8)))
            im.load()
    except ImagenInvalida:
        raise
    except Exception:  # lo que diga Pillow (en inglés) no le sirve a la persona
        raise ImagenInvalida(f"{que} está dañada o incompleta. Probá sacarla de nuevo.")
    if formato != _FORMATO_DE_PILLOW[tipo]:
        raise ImagenInvalida(f"{que} no es una imagen JPEG, PNG o WebP.")
    if min(ancho, alto) < MIN_LADO:
        raise ImagenInvalida(f"{que} es demasiado chica ({ancho}×{alto}).")
    return Imagen(tipo=tipo, ancho=ancho, alto=alto)


def hacer_miniatura(datos: bytes) -> bytes:
    """Una miniatura JPEG de LADO_MINIATURA px, para cuando el teléfono no
    mandó la suya (un navegador viejo, una subida a mano). Lo normal es que
    venga hecha: así el servidor no gasta en achicar fotos."""
    from PIL import Image, ImageOps
    try:
        with Image.open(io.BytesIO(datos)) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((LADO_MINIATURA, LADO_MINIATURA))
            salida = io.BytesIO()
            im.save(salida, format="JPEG", quality=70)
            return salida.getvalue()
    except Exception:
        raise ImagenInvalida("La foto está dañada o incompleta. Probá sacarla de nuevo.")


def entra_en_el_tope(ocupado: int, nuevo: int, tope_mb: int) -> bool:
    """Si una foto de `nuevo` bytes entra sin pasar el tope. Con tope 0, sin tope."""
    return tope_mb <= 0 or ocupado + nuevo <= tope_mb * 1024 * 1024


# ---------------------------------------------------------------------------
# La purga
# ---------------------------------------------------------------------------

def corte_de_purga(hoy: date, dias: int) -> date:
    """Las fotos de una acción que terminó ANTES de este día se borran."""
    return hoy - timedelta(days=dias)


async def purgar_fotos_vencidas(hoy: date | None = None, dias: int | None = None) -> int:
    """Borra las fotos de las acciones que terminaron hace más de `dias` días.
    Devuelve cuántas.

    Se van los bytes (que es lo que pesa); el estado de cada local queda, así
    el pedido sigue diciendo quién cumplió y quién no. Postgres no le devuelve
    el espacio al disco en el momento: lo reusa para lo que se guarde después
    (autovacuum), que para la cuota alcanza."""
    from app.models.calendario import CalendarioBarra
    from app.models.colocacion import ColocacionFoto, ColocacionLocal, ColocacionPedido
    from app.services.calendario_avisos import hoy_en_uruguay

    dias = settings.COLOCACION_RETENCION_DIAS if dias is None else dias
    if dias <= 0:
        return 0
    corte = corte_de_purga(hoy or hoy_en_uruguay(), dias)
    vencidos = (
        select(ColocacionLocal.id)
        .join(ColocacionPedido, ColocacionPedido.id == ColocacionLocal.pedido_id)
        .join(CalendarioBarra, CalendarioBarra.id == ColocacionPedido.barra_id)
        .where(CalendarioBarra.hasta < corte)
    )
    async with AsyncSessionLocal() as db:
        r = await db.execute(delete(ColocacionFoto).where(ColocacionFoto.local_id.in_(vencidos)))
        await db.commit()
        return r.rowcount or 0


async def run_purga_colocacion_loop() -> None:
    """Una pasada al arrancar y después una por día, como la de cenefas."""
    while True:
        try:
            borradas = await purgar_fotos_vencidas()
            if borradas:
                logger.info("purga_colocacion: %d foto(s) borradas", borradas)
        except Exception as exc:
            logger.error("purga_colocacion: falló la pasada -- %s", exc, exc_info=True)
        await asyncio.sleep(24 * 3600)
