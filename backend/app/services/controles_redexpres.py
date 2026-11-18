"""Lanzar y Cierre: los controles de cada acción de Redexpres.

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

Los Super FDS (fines de semana, una acción por semana) tienen los suyos, con
otros tiempos ("lanzamiento FDS y cierre FDS tienen que tener otros tiempos,
pero también convirtámoslo en notificación"):

- "Cierre FDS": en cada Super FDS, 14 días antes.
- "Lanzar FDS": uno por mes, 10 días antes del primer Super FDS del mes. Lo
  lleva el primero del mes; si cambia cuál es el primero (se carga uno antes,
  se mueve o se borra), pasa al nuevo (ver ordenar_lanzar_fds).

Solo Redexpres, y le llega a todo el equipo del mundo (lo eligió así). Los
avisos son los de siempre (`calendario_avisos`, ver
app/services/calendario_avisos.py) con `control`: la anticipación se guarda y
no la fecha (si la acción se corre, el aviso se corre con ella) y uno cuya
fecha ya pasó sale en el momento, que es justo "si se registró con menos
tiempo, enseguida". Las tareas van ancladas al inicio de la acción (como las
de plantilla) y se mueven con ella. "BOMBAS" no lleva ninguno.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendario import CalendarioAviso, CalendarioBarra, CalendarioTarea

MUNDO = "redexpres"
FILA_FDS = "super fds"
FILAS_SIN_CONTROLES = frozenset({FILA_FDS, "bombas"})

# (control, título de la tarea, días antes, qué es)
TAREAS = (
    ("lanzar", "Lanzar", 60, "Lanzar la acción: arrancar el pedido y avisar a quienes participan. Unos 2 meses antes."),
    ("cierre", "Cierre", 28, "Cerrar la acción: todo definido para mandar a producción. Unas 4 semanas antes."),
)
# (control, días antes). Lanzar avisa dos veces; si la acción se carga tarde,
# el de 60 sale en el momento (y el de 30 no repite si ya salió el otro).
AVISOS = (("lanzar", 60), ("lanzar", 30), ("cierre", 28))

CIERRE_FDS = ("cierre_fds", "Cierre FDS", 14, "Cerrar este Super FDS: productos y precios definidos. Dos semanas antes.")
LANZAR_FDS = ("lanzar_fds", "Lanzar FDS", 10, "Lanzar los Super FDS del mes. 10 días antes del primero.")
CONTROLES_FDS = ("lanzar_fds", "cierre_fds")

NOMBRE_DEL_CONTROL = {"lanzar": "Lanzar", "cierre": "Cierre", "lanzar_fds": "Lanzar FDS", "cierre_fds": "Cierre FDS"}
_PREFIJO = {"lanzar": "la", "cierre": "ci", "lanzar_fds": "lf", "cierre_fds": "cf"}


def _fila(barra) -> str:
    return " ".join((barra.banda or "").split()).casefold()


def aplica(barra) -> bool:
    """Si esta acción lleva Lanzar y Cierre. Pura."""
    return barra.mundo == MUNDO and barra.seccion == "comercial" and _fila(barra) not in FILAS_SIN_CONTROLES


def es_fds(barra) -> bool:
    """Si es un Super FDS de Redexpres (lleva Cierre FDS y, el primero del mes, Lanzar FDS). Pura."""
    return barra.mundo == MUNDO and barra.seccion == "comercial" and _fila(barra) == FILA_FDS


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
    """Las tareas Lanzar y Cierre que le faltan a la acción. Pura."""
    return [
        _tarea(barra, control, titulo, dias, detalle, orden, creado_por, hoy)
        for orden, (control, titulo, dias, detalle) in enumerate(TAREAS)
        if titulo.casefold() not in titulos_existentes
    ]


def avisos_nuevos(barra, existentes: set[tuple[str, int]], creado_por: int | None) -> list[dict]:
    """Los avisos de Lanzar y Cierre que le faltan a la acción. Pura."""
    return [_aviso(barra, control, dias, creado_por) for control, dias in AVISOS if (control, dias) not in existentes]


def controles_fds(
    barra, titulos_existentes: set[str], existentes: set[tuple[str, int]], creado_por: int | None, hoy: date,
    primero_del_mes: bool,
) -> tuple[list[dict], list[dict]]:
    """Las tareas y los avisos de un Super FDS que le faltan: Cierre FDS
    siempre; Lanzar FDS si es el primero del mes. Pura."""
    pares = [CIERRE_FDS] + ([LANZAR_FDS] if primero_del_mes else [])
    tareas = [
        _tarea(barra, control, titulo, dias, detalle, 1 if control == "cierre_fds" else 0, creado_por, hoy)
        for control, titulo, dias, detalle in pares if titulo.casefold() not in titulos_existentes
    ]
    avisos = [
        _aviso(barra, control, dias, creado_por)
        for control, _, dias, _ in pares if (control, dias) not in existentes
    ]
    return tareas, avisos


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
    if aplica(barra):
        titulos, existentes = await _lo_que_tiene(db, barra.id)
        return await _guardar(
            db, tareas_nuevas(barra, titulos, creado_por, hoy), avisos_nuevos(barra, existentes, creado_por),
        )
    if es_fds(barra):
        titulos, existentes = await _lo_que_tiene(db, barra.id)
        tareas, avisos = controles_fds(barra, titulos, existentes, creado_por, hoy, primero_del_mes=False)
        n = await _guardar(db, tareas, avisos)
        return n + await ordenar_lanzar_fds(db, {(barra.desde.year, barra.desde.month)}, creado_por, hoy)
    return 0


def _rango_del_mes(anio: int, mes: int) -> tuple[date, date]:
    primero = date(anio, mes, 1)
    siguiente = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    return primero, siguiente - timedelta(days=1)


async def ordenar_lanzar_fds(db: AsyncSession, meses: set[tuple[int, int]], creado_por: int | None, hoy: date) -> int:
    """Que en cada uno de esos meses Lanzar FDS lo lleve el primer Super FDS
    y ningún otro. Se corre al crear, mover o borrar uno. A uno que dejó de
    ser el primero se le saca: el aviso, y la tarea si no está hecha."""
    n = 0
    for anio, mes in sorted(meses):
        desde, hasta = _rango_del_mes(anio, mes)
        del_mes = [
            b for b in (await db.execute(
                select(CalendarioBarra).where(
                    CalendarioBarra.mundo == MUNDO, CalendarioBarra.seccion == "comercial",
                    CalendarioBarra.desde >= desde, CalendarioBarra.desde <= hasta,
                ).order_by(CalendarioBarra.desde, CalendarioBarra.id)
            )).scalars() if es_fds(b)
        ]
        if not del_mes:
            continue
        primero, otros = del_mes[0], del_mes[1:]
        titulos, existentes = await _lo_que_tiene(db, primero.id)
        tareas, avisos = controles_fds(primero, titulos, existentes, creado_por, hoy, primero_del_mes=True)
        tareas = [t for t in tareas if t["titulo"] == LANZAR_FDS[1]]
        avisos = [a for a in avisos if a["control"] == "lanzar_fds"]
        n += await _guardar(db, tareas, avisos)
        if otros:
            await _sacar(db, [b.id for b in otros], ("lanzar_fds",))
    return n


async def _sacar(db: AsyncSession, barra_ids: list[str], controles: tuple[str, ...]) -> None:
    titulos = [NOMBRE_DEL_CONTROL[c] for c in controles]
    await db.execute(delete(CalendarioAviso).where(
        CalendarioAviso.barra_id.in_(barra_ids), CalendarioAviso.control.in_(controles),
    ))
    await db.execute(delete(CalendarioTarea).where(
        CalendarioTarea.barra_id.in_(barra_ids), CalendarioTarea.titulo.in_(titulos),
        CalendarioTarea.estado != "hecha",
    ))
    await db.flush()


async def dejo_de_ser_fds(db: AsyncSession, barra: CalendarioBarra) -> None:
    """La pasaron de "Super FDS" a otra fila: se le sacan sus controles de FDS."""
    await _sacar(db, [barra.id], CONTROLES_FDS)
