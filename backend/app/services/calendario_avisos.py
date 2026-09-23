"""Avisos del calendario: 10 días antes de cada acción del comercial.

Pedido de Ivan (23/09/2026): "tenemos fechas para las acciones, tenemos que
configurar que 10 días antes de cada acción del calendario promocional nos
llegue a nuestras notificaciones para estar al tanto".

No hay una bandeja aparte: el aviso entra en las notificaciones de la
plataforma, las mismas de la campanita del menú ("ya tenemos notificaciones
por personas"). Por eso escribe en `notificaciones` y nada más.

Quién lo recibe: todo usuario con `calendario.view`. Es el mismo criterio con
el que se decide si ve el calendario, así que nadie se entera de una acción
que no podría abrir.

Una vez por acción: `origen_ref` lleva el mes, el id de la barra y el hito, y
antes de crear nada se consulta qué referencias ya existen. Si el servidor
estuvo caído tres días, al volver igual avisa (la ventana es "faltan 10 días o
menos y todavía no arrancó"), en vez de perderse el aviso por no haber corrido
el día exacto.
"""
from __future__ import annotations

import asyncio
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.calendario_mes import CalendarioMes
from app.models.notificacion import Notificacion
from app.models.user import User

logger = logging.getLogger(__name__)

# Cuántos días antes se avisa.
DIAS_DE_AVISO = 10

TIPO = "calendario_accion"
ORIGEN = "calendario_accion"
HITO = "t-10"

# Cada cuánto se revisa. Una vez por día alcanza: el hito es un día entero, no
# una hora. Se revisa igual al arrancar, por si el proceso estuvo caído.
_HORAS_ENTRE_REVISIONES = 12


def _fecha(clave: str, dia: int) -> date | None:
    """La fecha real de un día del mes. Devuelve None si el día no existe en
    ese mes (un 31 en un mes de 30, que puede quedar de un import)."""
    try:
        anio, mes = (int(p) for p in clave.split("-"))
        tope = monthrange(anio, mes)[1]
        return date(anio, mes, min(max(dia, 1), tope))
    except (ValueError, TypeError):
        return None


def acciones_del_mes(clave: str, datos: dict) -> list[dict]:
    """Las acciones del calendario comercial de un mes, con su fecha de inicio.

    Solo el comercial: el de Retail Media son espacios vendidos y el header se
    deriva de los otros dos, así que avisar por esos sería avisar tres veces de
    lo mismo."""
    acciones: list[dict] = []
    for banda in datos.get("comercial") or []:
        for fila in banda.get("filas") or []:
            for barra in fila or []:
                inicio = _fecha(clave, barra.get("desde"))
                if inicio is None or not barra.get("id"):
                    continue
                acciones.append({
                    "id": barra["id"],
                    "nombre": (barra.get("nombre") or "").strip() or "Sin nombre",
                    "banda": banda.get("nombre") or "",
                    "inicio": inicio,
                    "fin": _fecha(clave, barra.get("hasta")) or inicio,
                })
    return acciones


def _mensaje(accion: dict, faltan: int) -> str:
    cuando = (
        "arranca mañana" if faltan == 1
        else "arranca hoy" if faltan == 0
        else f"arranca en {faltan} días"
    )
    tipo = f" ({accion['banda']})" if accion["banda"] else ""
    return (
        f"{accion['nombre']}{tipo} {cuando}, el "
        f"{accion['inicio'].strftime('%d/%m')}. Revisá que estén todas las piezas."
    )


async def _destinatarios(db: AsyncSession) -> list[User]:
    usuarios = (await db.execute(select(User).where(User.is_active == True))).scalars()  # noqa: E712
    return [
        u for u in usuarios
        if u.is_superuser or "calendario.view" in (u.permissions or [])
    ]


async def revisar_avisos(db: AsyncSession, hoy: date | None = None) -> int:
    """Crea los avisos que correspondan. Devuelve cuántos creó."""
    hoy = hoy or datetime.now(timezone.utc).date()
    limite = hoy + timedelta(days=DIAS_DE_AVISO)

    # Los meses que ya pasaron no se miran.
    meses = [
        m for m in (await db.execute(select(CalendarioMes))).scalars()
        if (_fecha(m.clave, 28) or hoy) >= hoy - timedelta(days=31)
    ]
    if not meses:
        return 0

    por_avisar: list[dict] = []
    for mes in meses:
        for accion in acciones_del_mes(mes.clave, mes.datos or {}):
            if hoy <= accion["inicio"] <= limite:
                accion["ref"] = f"{mes.clave}:{accion['id']}:{HITO}"
                por_avisar.append(accion)
    if not por_avisar:
        return 0

    destinatarios = await _destinatarios(db)
    if not destinatarios:
        return 0

    # Una sola consulta por todas las referencias en juego: sin esto serían
    # N acciones x M personas selects cada vez que corre.
    refs = [a["ref"] for a in por_avisar]
    ya_avisado = {
        (n.user_id, n.origen_ref)
        for n in (await db.execute(
            select(Notificacion).where(
                Notificacion.origen_tipo == ORIGEN,
                Notificacion.origen_ref.in_(refs),
            )
        )).scalars()
    }

    creadas = 0
    for accion in por_avisar:
        faltan = (accion["inicio"] - hoy).days
        mensaje = _mensaje(accion, faltan)
        for usuario in destinatarios:
            if (usuario.id, accion["ref"]) in ya_avisado:
                continue
            db.add(Notificacion(
                user_id=usuario.id,
                tipo=TIPO,
                mensaje=mensaje,
                origen_tipo=ORIGEN,
                origen_ref=accion["ref"],
            ))
            creadas += 1

    if creadas:
        await db.commit()
        logger.info("calendario_avisos: %d avisos nuevos", creadas)
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
