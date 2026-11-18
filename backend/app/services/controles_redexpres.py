"""Lanzar y Cierre: los dos controles de cada acción de Redexpres.

Pedido de Ivan (18/11/2026), a partir de la hoja "Valen" del Excel de
Redexpres (las tareas de Valentina en cada acción):

- "Lanzar" (unos 2 meses antes): "esto podemos hacer que llegue una
  notificación 60 días antes de que la acción llegue (...) si el tiempo de
  registro de la acción es menor a 60 días tenemos que enviar la notificación
  de lanzar enseguida que se registra", y "una segunda notificación a los 30
  días antes también" (siempre, eligió después).
- "Cierre" (unas 4 semanas antes): "esto será aviso por notificación, 4
  semanas antes".
- "Una vez se crea una acción, la tarea de lanzar y de cierre debe estar
  creada automáticamente también como tarea dentro de la acción".

Solo Redexpres, y le llega a todo el equipo del mundo (lo eligió así). Los
avisos son los de siempre (`calendario_avisos`, ver
app/services/calendario_avisos.py) con `control` = 'lanzar' o 'cierre': la
anticipación se guarda y no la fecha (si la acción se corre, el aviso se corre
con ella) y uno cuya fecha ya pasó sale en el momento, que es justo "si se
registró con menos de 60 días, enseguida". Las tareas van ancladas al inicio
de la acción (como las de plantilla) y se mueven con ella.

No van en "Super FDS" ni en "BOMBAS": son semanales y en la hoja de Valentina
llevan sus propias tareas (Cierre FDS, Afiche bombas), con otros tiempos.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendario import CalendarioAviso, CalendarioBarra, CalendarioTarea

MUNDO = "redexpres"
FILAS_SIN_CONTROLES = frozenset({"super fds", "bombas"})

# (control, título de la tarea, días antes, qué es)
TAREAS = (
    ("lanzar", "Lanzar", 60, "Lanzar la acción: arrancar el pedido y avisar a quienes participan. Unos 2 meses antes."),
    ("cierre", "Cierre", 28, "Cerrar la acción: todo definido para mandar a producción. Unas 4 semanas antes."),
)
# (control, días antes). Lanzar avisa dos veces; si la acción se carga tarde,
# el de 60 sale en el momento (y el de 30 no repite si ya salió el otro).
AVISOS = (("lanzar", 60), ("lanzar", 30), ("cierre", 28))

NOMBRE_DEL_CONTROL = {"lanzar": "Lanzar", "cierre": "Cierre"}


def aplica(barra) -> bool:
    """Si esta acción lleva Lanzar y Cierre. Pura."""
    return (
        barra.mundo == MUNDO and barra.seccion == "comercial"
        and " ".join((barra.banda or "").split()).casefold() not in FILAS_SIN_CONTROLES
    )


def _corto(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


def id_de_tarea(barra_id: str, control: str) -> str:
    """Siempre el mismo para la misma acción: reintentar no duplica."""
    return f"ta-{control[:2]}-{_corto(barra_id)}"


def id_de_aviso(barra_id: str, control: str, dias: int) -> str:
    return f"av-{control[:2]}{dias}-{_corto(barra_id)}"


def tareas_nuevas(barra, titulos_existentes: set[str], creado_por: int | None, hoy: date) -> list[dict]:
    """Las tareas de control que le faltan a la acción. Pura.

    Si la fecha del control ya pasó (la acción se cargó tarde), vence hoy y no
    queda anclada: anclada vencería en el pasado y nacería "Vencida"."""
    out = []
    for orden, (control, titulo, dias, detalle) in enumerate(TAREAS):
        if titulo.casefold() in titulos_existentes:
            continue
        fecha = barra.desde - timedelta(days=dias)
        a_tiempo = fecha >= hoy
        out.append({
            "id": id_de_tarea(barra.id, control), "barra_id": barra.id, "titulo": titulo, "descripcion": detalle,
            "estado": "pendiente", "vence": fecha if a_tiempo else hoy,
            "ancla": "inicio" if a_tiempo else None, "ancla_dias": -dias if a_tiempo else None,
            "orden": orden, "creado_por_id": creado_por,
        })
    return out


def avisos_nuevos(barra, existentes: set[tuple[str, int]], creado_por: int | None) -> list[dict]:
    """Los avisos de control que le faltan a la acción. Pura."""
    return [
        {
            "id": id_de_aviso(barra.id, control, dias), "barra_id": barra.id, "dias_antes": dias,
            "destinatarios": [], "creado_por_id": creado_por, "control": control,
        }
        for control, dias in AVISOS if (control, dias) not in existentes
    ]


async def agregar(db: AsyncSession, barra: CalendarioBarra, creado_por: int | None, hoy: date) -> int:
    """Le suma a la acción las tareas y los avisos de control que le falten
    (no hace commit). Devuelve cuántas cosas agregó. Una tarea que ya se
    llama "Lanzar" o "Cierre" (copiada de otra acción, o creada a mano)
    cuenta como que ya está."""
    if not aplica(barra):
        return 0
    titulos = {
        (t or "").strip().casefold() for t in (await db.execute(
            select(CalendarioTarea.titulo).where(CalendarioTarea.barra_id == barra.id)
        )).scalars()
    }
    existentes = {
        (c, d) for c, d in (await db.execute(
            select(CalendarioAviso.control, CalendarioAviso.dias_antes).where(
                CalendarioAviso.barra_id == barra.id, CalendarioAviso.control.is_not(None),
            )
        )).all()
    }
    tareas = tareas_nuevas(barra, titulos, creado_por, hoy)
    avisos = avisos_nuevos(barra, existentes, creado_por)
    for t in tareas:
        if await db.get(CalendarioTarea, t["id"]) is None:
            db.add(CalendarioTarea(**t))
    for a in avisos:
        if await db.get(CalendarioAviso, a["id"]) is None:
            db.add(CalendarioAviso(**a))
    await db.flush()
    return len(tareas) + len(avisos)
