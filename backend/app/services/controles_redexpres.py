"""Lanzar: el control que trae sola cada acción de Redexpres.

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

El Cierre (4 semanas antes) también fue automático hasta el 20/11/2026: "el
cierre común debería quedar como una tarea manual a crear por Vale, ya que
tema fechas es muy complejo (...) se creará manual y solo manual". Desde ahí
lo crea Valentina como cualquier tarea; la 0083 sacó los automáticos.

Los Super FDS tuvieron sus propios controles (Lanzar FDS y Cierre FDS, del
18/11/2026) hasta que se dejaron de hacer: "FDS no va a existir más (...) la
línea de FDS no debería existir más a partir de diciembre" (Ivan, 20/11/2026).
La fila se ve hasta noviembre (ver bandasRetiradas en frontend/lib/mundos.ts)
y la 0083 borró sus controles.

Solo Redexpres, y le llega a todo el equipo del mundo (lo eligió así). Los
avisos son los de siempre (`calendario_avisos`, ver
app/services/calendario_avisos.py) con `control`: la anticipación se guarda y
no la fecha (si la acción se corre, el aviso se corre con ella) y uno cuya
fecha ya pasó sale en el momento, que es justo "si se registró con menos
tiempo, enseguida". Las tareas van ancladas al inicio de la acción (como las
de plantilla) y se mueven con ella. "BOMBAS" y los Super FDS no llevan.
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
)
# (control, días antes). Lanzar avisa dos veces; si la acción se carga tarde,
# el de 60 sale en el momento (y el de 30 no repite si ya salió el otro).
AVISOS = (("lanzar", 60), ("lanzar", 30))

NOMBRE_DEL_CONTROL = {"lanzar": "Lanzar"}
_PREFIJO = {"lanzar": "la"}


def _fila(barra) -> str:
    return " ".join((barra.banda or "").split()).casefold()


def aplica(barra) -> bool:
    """Si esta acción lleva Lanzar. Pura."""
    return barra.mundo == MUNDO and barra.seccion == "comercial" and _fila(barra) not in FILAS_SIN_CONTROLES


def _corto(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


def id_de_tarea(barra_id: str, control: str) -> str:
    """Siempre el mismo para la misma acción: reintentar no duplica."""
    return f"ta-{_PREFIJO.get(control, control[:2])}-{_corto(barra_id)}"


def id_de_aviso(barra_id: str, control: str, dias: int) -> str:
    return f"av-{_PREFIJO.get(control, control[:2])}{dias}-{_corto(barra_id)}"


def _tarea(barra, control: str, titulo: str, dias: int, detalle: str, orden: int, creado_por, hoy: date) -> dict:
    """Si la fecha del control ya pasó (la acción se cargó tarde), vence hoy y
    no queda anclada: anclada vencería en el pasado y nacería "Vencida"."""
    fecha = barra.desde - timedelta(days=dias)
    a_tiempo = fecha >= hoy
    return {
        "id": id_de_tarea(barra.id, control), "barra_id": barra.id, "titulo": titulo, "descripcion": detalle,
        "estado": "pendiente", "vence": fecha if a_tiempo else hoy,
        "ancla": "inicio" if a_tiempo else None, "ancla_dias": -dias if a_tiempo else None,
        "orden": orden, "creado_por_id": creado_por,
    }


def _aviso(barra, control: str, dias: int, creado_por) -> dict:
    return {
        "id": id_de_aviso(barra.id, control, dias), "barra_id": barra.id, "dias_antes": dias,
        "destinatarios": [], "creado_por_id": creado_por, "control": control,
    }


def tareas_nuevas(barra, titulos_existentes: set[str], creado_por: int | None, hoy: date) -> list[dict]:
    """La tarea Lanzar, si le falta a la acción. Pura."""
    return [
        _tarea(barra, control, titulo, dias, detalle, orden, creado_por, hoy)
        for orden, (control, titulo, dias, detalle) in enumerate(TAREAS)
        if titulo.casefold() not in titulos_existentes
    ]


def avisos_nuevos(barra, existentes: set[tuple[str, int]], creado_por: int | None) -> list[dict]:
    """Los avisos de Lanzar que le faltan a la acción. Pura."""
    return [_aviso(barra, control, dias, creado_por) for control, dias in AVISOS if (control, dias) not in existentes]


async def _lo_que_tiene(db: AsyncSession, barra_id: str) -> tuple[set[str], set[tuple[str, int]]]:
    titulos = {
        (t or "").strip().casefold() for t in (await db.execute(
            select(CalendarioTarea.titulo).where(CalendarioTarea.barra_id == barra_id)
        )).scalars()
    }
    avisos = {
        (c, d) for c, d in (await db.execute(
            select(CalendarioAviso.control, CalendarioAviso.dias_antes).where(
                CalendarioAviso.barra_id == barra_id, CalendarioAviso.control.is_not(None),
            )
        )).all()
    }
    return titulos, avisos


async def _guardar(db: AsyncSession, tareas: list[dict], avisos: list[dict]) -> int:
    n = 0
    for t in tareas:
        if await db.get(CalendarioTarea, t["id"]) is None:
            db.add(CalendarioTarea(**t))
            n += 1
    for a in avisos:
        if await db.get(CalendarioAviso, a["id"]) is None:
            db.add(CalendarioAviso(**a))
            n += 1
    await db.flush()
    return n


async def agregar(db: AsyncSession, barra: CalendarioBarra, creado_por: int | None, hoy: date) -> int:
    """Le suma a la acción las tareas y los avisos de control que le falten
    (no hace commit). Devuelve cuántas cosas agregó. Una tarea que ya se
    llama así (copiada de otra acción, o creada a mano) cuenta como que ya
    está."""
    if not aplica(barra):
        return 0
    titulos, existentes = await _lo_que_tiene(db, barra.id)
    return await _guardar(
        db, tareas_nuevas(barra, titulos, creado_por, hoy), avisos_nuevos(barra, existentes, creado_por),
    )
