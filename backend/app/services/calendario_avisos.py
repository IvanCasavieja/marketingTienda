"""Avisos del calendario: los que alguien configuró en la ficha de una acción.

Hasta el 28/09/2026 había un aviso automático, 10 días antes de CADA acción y
a TODOS los que veían el calendario (salieron 308 así, a 14 personas). Ivan lo
pidió apagar: "tomarlo de manera automática genera errores, nos van a llegar
notificaciones de cosas que no valen la pena y la gente le va a dejar de dar
bolilla. Cuando realmente nos llegue una notificación, es porque alguien la
configuró". Ahora no sale nada que no esté en `calendario_avisos`.

Cada aviso dice cuántos días antes de que arranque su acción y a quién. Se
guarda la anticipación y no la fecha, así que si la acción se corre el aviso
se corre con ella.

La ventana sigue siendo "faltan N días o menos y todavía no arrancó", no
"faltan exactamente N": si el servidor estuvo caído un par de días, el aviso
sale igual en vez de perderse. Y si alguien configura un aviso cuya fecha ya
pasó (10 días antes de algo que arranca en 5), sale en el momento.

Una sola vez por aviso y por persona DENTRO DE SU VENTANA. Si la acción se
corre un día y el aviso ya había salido en esta ventana, no vuelve a salir
(sería ruido). Si se corre lejos —de octubre a diciembre— la ventana nueva
arranca después del aviso viejo, y el aviso vuelve a valer para la fecha nueva.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.calendario import CalendarioAviso, CalendarioBarra
from app.models.notificacion import Notificacion
from app.models.user import User

logger = logging.getLogger(__name__)

TIPO = "calendario_aviso"
ORIGEN = "calendario_aviso"

# Uruguay no tiene horario de verano desde 2015: siempre UTC-3. Se usa para que
# "hoy" sea el día de acá y no el de Greenwich, que entre las 21 y las 24 ya es
# mañana.
_URUGUAY = timezone(timedelta(hours=-3))

# El hito es un día entero, no una hora: revisar cada 6 horas alcanza y sobra.
# Se revisa también al arrancar, por si el proceso estuvo caído.
_HORAS_ENTRE_REVISIONES = 6

# Un número cualquiera, siempre el mismo, para el candado de Postgres que
# ordena a dos revisiones que corren a la vez (el loop y alguien configurando
# un aviso): sin él, las dos ven que falta el aviso y lo mandan dos veces.
_CANDADO = 2026_09_28


def hoy_en_uruguay() -> date:
    return datetime.now(_URUGUAY).date()


def toca_avisar(inicio: date, dias_antes: int, hoy: date) -> bool:
    """Si hoy cae entre el día del aviso y el día en que arranca la acción."""
    return inicio - timedelta(days=dias_antes) <= hoy <= inicio


def inicio_de_ventana(inicio: date, dias_antes: int) -> datetime:
    """El momento desde el que un aviso cuenta como "ya salió": las 0 horas
    (de Uruguay) del día del aviso."""
    return datetime.combine(inicio - timedelta(days=dias_antes), time(0), tzinfo=_URUGUAY)


def referencia(barra_id: str, aviso_id: str) -> str:
    """Empieza por el id de la acción: es lo que usa la campanita para llevar
    a su ficha (ver `resolverDestino` en el Sidebar)."""
    return f"{barra_id}:{aviso_id}"


# Cómo se nombra el canal de un envío suelto en el aviso.
_CANAL = {"email": "Email", "whatsapp": "WhatsApp", "push": "Push"}


def mensaje(
    nombre: str, banda: str, inicio: date, hoy: date, quien: str | None, es_envio: bool = False,
) -> str:
    """El texto del aviso. Una acción "arranca"; un envío suelto "sale"."""
    faltan = (inicio - hoy).days
    verbo = "sale" if es_envio else "arranca"
    cuando = (
        f"{verbo} hoy" if faltan <= 0
        else f"{verbo} mañana" if faltan == 1
        else f"{verbo} en {faltan} días"
    )
    etiqueta = _CANAL.get(banda, banda) if es_envio else banda
    tipo = f" ({etiqueta})" if etiqueta else ""
    firma = f" Aviso configurado por {quien}." if quien else ""
    return f"{nombre or 'Sin nombre'}{tipo} {cuando}, el {inicio.strftime('%d/%m')}.{firma}"


def puede_ver_el_calendario(usuario: User) -> bool:
    return bool(usuario.is_active) and (
        usuario.is_superuser or "calendario.view" in (usuario.permissions or [])
    )


def _ids(destinatarios) -> list[int]:
    """Los ids de un aviso, sin repetir y sin lo que no sea un número."""
    out: list[int] = []
    for u in destinatarios or []:
        try:
            n = int(u)
        except (TypeError, ValueError):
            continue
        if n not in out:
            out.append(n)
    return out


async def revisar_avisos(
    db: AsyncSession,
    hoy: date | None = None,
    barra_id: str | None = None,
) -> int:
    """Crea las notificaciones de los avisos que tocan hoy. Devuelve cuántas.

    Con `barra_id` mira solo los de esa acción: es lo que se corre apenas
    alguien configura un aviso o le cambia la fecha a una acción, para no
    esperar a la próxima vuelta del loop."""
    hoy = hoy or hoy_en_uruguay()
    # El candado dura hasta el commit (o el rollback) de esta transacción, así
    # que la transacción se cierra siempre, haya o no avisos.
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CANDADO})
    try:
        creadas = await _revisar(db, hoy, barra_id)
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    if creadas:
        logger.info("calendario_avisos: %d avisos nuevos", creadas)
    return creadas


async def _revisar(db: AsyncSession, hoy: date, barra_id: str | None) -> int:
    """Lo de adentro del candado: qué avisos tocan y a quién le faltan."""
    consulta = (
        select(CalendarioAviso, CalendarioBarra)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioAviso.barra_id)
        .where(CalendarioBarra.desde >= hoy)
    )
    if barra_id is not None:
        consulta = consulta.where(CalendarioBarra.id == barra_id)
    pares = [
        (aviso, barra) for aviso, barra in (await db.execute(consulta)).all()
        if toca_avisar(barra.desde, aviso.dias_antes, hoy)
    ]
    if not pares:
        return 0

    ids = {u for aviso, _ in pares for u in _ids(aviso.destinatarios)}
    ids |= {aviso.creado_por_id for aviso, _ in pares if aviso.creado_por_id}
    usuarios = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()
    } if ids else {}

    # Cuándo le salió a cada uno cada aviso, para saber si ya salió en
    # esta ventana.
    refs = [referencia(barra.id, aviso.id) for aviso, barra in pares]
    salidos: dict[tuple[int, str], datetime] = {}
    for n in (await db.execute(
        select(Notificacion).where(
            Notificacion.origen_tipo == ORIGEN,
            Notificacion.origen_ref.in_(refs),
        )
    )).scalars():
        clave = (n.user_id, n.origen_ref)
        if n.created_at and (clave not in salidos or n.created_at > salidos[clave]):
            salidos[clave] = n.created_at

    creadas = 0
    for aviso, barra in pares:
        ref = referencia(barra.id, aviso.id)
        desde_cuando = inicio_de_ventana(barra.desde, aviso.dias_antes)
        creador = usuarios.get(aviso.creado_por_id) if aviso.creado_por_id else None
        texto = mensaje(
            barra.nombre, barra.banda, barra.desde, hoy, creador.full_name if creador else None,
            es_envio=barra.seccion == "envio",
        )
        for uid in _ids(aviso.destinatarios):
            usuario = usuarios.get(uid)
            # Alguien a quien le sacaron el calendario después de que se
            # configuró el aviso no recibe avisos de algo que no puede abrir.
            if usuario is None or not puede_ver_el_calendario(usuario):
                continue
            ultimo = salidos.get((uid, ref))
            if ultimo is not None and ultimo >= desde_cuando:
                continue
            db.add(Notificacion(
                user_id=uid,
                tipo=TIPO,
                mensaje=texto,
                origen_tipo=ORIGEN,
                origen_ref=ref,
            ))
            creadas += 1
    return creadas


async def run_calendario_avisos_loop() -> None:
    """Loop perpetuo, arranca con FastAPI igual que los otros."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await revisar_avisos(db)
        except Exception as exc:
            logger.error("calendario_avisos: error en el loop: %s", exc, exc_info=True)
        await asyncio.sleep(_HORAS_ENTRE_REVISIONES * 3_600)
