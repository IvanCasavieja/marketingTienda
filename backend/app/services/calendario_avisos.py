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
from app.core.mundos import puede_abrir
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

# Lo que lleva en `banda` una acción a la que todavía no se le eligió
# categoría (desde el 12/11/2026 una acción se crea sin preguntar de qué tipo
# es). El texto lo pone el front: es SIN_CATEGORIA en
# frontend/lib/calendario/categorias.ts. Si cambia, cambia en los dos.
SIN_CATEGORIA = "Sin categoría"


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
    # "Fiesta de Italia (Sin categoría) arranca..." no le dice nada a nadie: una
    # acción sin categoría va sin paréntesis, igual que una con la banda vacía.
    if not es_envio and (banda or "").strip().casefold() == SIN_CATEGORIA.casefold():
        etiqueta = ""
    tipo = f" ({etiqueta})" if etiqueta else ""
    firma = f" Aviso configurado por {quien}." if quien else ""
    return f"{nombre or 'Sin nombre'}{tipo} {cuando}, el {inicio.strftime('%d/%m')}.{firma}"


def mensaje_de_control(
    control: str, nombre: str, banda: str, inicio: date, hoy: date,
) -> str:
    """El texto de Lanzar o Cierre (0077): "Lanzar: Mailing diciembre (MAILING
    - 16 PAG EL PAIS) arranca en 60 días, el 01/12." Sin firma: no lo
    configuró nadie, lo trae la acción."""
    from app.services.controles_redexpres import NOMBRE_DEL_CONTROL
    titulo = NOMBRE_DEL_CONTROL.get(control, control.capitalize())
    return f"{titulo}: {mensaje(nombre, banda, inicio, hoy, None)}"


def edita_el_calendario(usuario: User) -> bool:
    """Del equipo que lleva el calendario: a quien le llegan Lanzar y Cierre."""
    return bool(usuario.is_superuser or "calendario.edit" in (usuario.permissions or []))


def puede_ver_el_calendario(usuario: User) -> bool:
    return bool(usuario.is_active) and (
        usuario.is_superuser or "calendario.view" in (usuario.permissions or [])
    )


def puede_recibir_el_aviso(usuario: User | None, mundo: str) -> bool:
    """Si a esa persona le sale hoy un aviso de una acción de ese mundo. A
    quien le sacaron el calendario, o el mundo de la acción, después de que se
    configuró el aviso no le llegan avisos de algo que no puede abrir.

    A una cuenta externa (la agencia) nunca: los avisos son del equipo y salen
    hasta un año antes de la acción, fuera de su ventana. La ficha ya no deja
    elegirla; esto cuida los avisos que se hayan configurado antes."""
    return (
        usuario is not None and not getattr(usuario, "es_externo", False)
        and puede_ver_el_calendario(usuario) and puede_abrir(usuario, mundo)
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
    # El de más días primero: si Lanzar a 60 y a 30 tocan a la vez (la acción
    # se cargó tarde), sale el de 60 y el de 30 ya lo encuentra salido.
    pares = sorted((
        (aviso, barra) for aviso, barra in (await db.execute(consulta)).all()
        if toca_avisar(barra.desde, aviso.dias_antes, hoy)
    ), key=lambda p: (p[1].id, -p[0].dias_antes))
    if not pares:
        return 0

    ids = {u for aviso, _ in pares for u in _ids(aviso.destinatarios)}
    ids |= {aviso.creado_por_id for aviso, _ in pares if aviso.creado_por_id}
    usuarios = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()
    } if ids else {}

    # Lanzar y Cierre (0077) le llegan a todo el equipo del mundo: quienes lo
    # abren y editan el calendario. Se calcula al avisar, así le llega también
    # a quien entró al equipo después de que se cargó la acción.
    equipo: dict[str, list[int]] = {}
    if any(aviso.control for aviso, _ in pares):
        todos = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
        for u in todos:
            usuarios.setdefault(u.id, u)
        for mundo in {barra.mundo for aviso, barra in pares if aviso.control}:
            equipo[mundo] = sorted(
                u.id for u in todos if puede_recibir_el_aviso(u, mundo) and edita_el_calendario(u)
            )
    # Un control es uno solo aunque tenga dos avisos (Lanzar a 60 y a 30): se
    # mira cuándo le salió a cada persona cualquiera de los dos.
    control_de_ref = {
        referencia(barra.id, aviso.id): (barra.id, aviso.control) for aviso, barra in pares if aviso.control
    }

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
        grupo = control_de_ref.get(n.origen_ref)
        if grupo and n.created_at:
            clave_c = (n.user_id, *grupo)
            if clave_c not in salidos or n.created_at > salidos[clave_c]:
                salidos[clave_c] = n.created_at

    creadas = 0
    ahora = datetime.now(timezone.utc)
    for aviso, barra in pares:
        ref = referencia(barra.id, aviso.id)
        desde_cuando = inicio_de_ventana(barra.desde, aviso.dias_antes)
        if aviso.control:
            texto = mensaje_de_control(aviso.control, barra.nombre, barra.banda, barra.desde, hoy)
        else:
            creador = usuarios.get(aviso.creado_por_id) if aviso.creado_por_id else None
            texto = mensaje(
                barra.nombre, barra.banda, barra.desde, hoy, creador.full_name if creador else None,
                es_envio=barra.seccion == "envio",
            )
        destinatarios = _ids(aviso.destinatarios)
        if aviso.control:
            destinatarios += [u for u in equipo.get(barra.mundo, []) if u not in destinatarios]
        for uid in destinatarios:
            usuario = usuarios.get(uid)
            if not puede_recibir_el_aviso(usuario, barra.mundo):
                continue
            clave = (uid, barra.id, aviso.control) if aviso.control else (uid, ref)
            ultimo = salidos.get(clave)
            if ultimo is not None and ultimo >= desde_cuando:
                continue
            db.add(Notificacion(
                user_id=uid,
                tipo=TIPO,
                mensaje=texto,
                origen_tipo=ORIGEN,
                origen_ref=ref,
            ))
            salidos[clave] = ahora
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
