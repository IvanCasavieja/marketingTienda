"""Hasta dónde ve el calendario cada persona (0070).

Pedido de Ivan (16/11/2026): el calendario lo ve mucha gente y lo quiere
empezar a cerrar. Cada usuario (del equipo o de afuera) tiene un ALCANCE que
elige un admin en el panel de usuarios:

- 'nada'  — No lo ve: nada del calendario (los datos, el link de Outlook, Don
            Tino, ubicar una acción...). SÍ ve su tablero de tarjetas: es su
            trabajo, no "el calendario".
- '1m'    — 1 mes: el mes actual.
- '2m'    — 2 meses: el actual y el que viene.
- '12m'   — 12 meses: el actual y los 11 que siguen.
- 'todo'  — Todo: sin límite (2025, 2026, 2027... lo que haya).

N meses = el mes actual y los N−1 siguientes, MÁS los últimos 7 días del mes
anterior: una acción que terminó el 28 no desaparece de golpe el 1, en medio
de su cierre. Siempre en hora de Uruguay (a las 22 de un 31 en Montevideo ya
es 1 en Greenwich, y la ventana no puede cambiar de mes por eso).

Por defecto: las cuentas externas (la agencia) arrancan en 'nada' ("en un
inicio la agencia no va a tener acceso a ver el calendario"); las del equipo,
en 'todo' (no les cambia nada hasta que un admin las restrinja).

Qué se filtra con esto: TODO lo que muestra el calendario, para cualquiera
con alcance limitado, sea del equipo o de afuera. Una acción fuera de la
ventana, para esa persona, no existe: el mismo 404 que una borrada. Lo que
además restringe a una cuenta externa (solo sus tareas, sin avisos, sin las
herramientas internas) sigue en app/core/externos.py y depende de
`es_externo`, no de esto.

La excepción son las tarjetas propias del tablero (ver tarjeta_propia en
app/api/routes/entregas.py): se ven siempre, aunque la campaña quede fuera
del alcance, porque hay que trabajarlas con anticipación. Y a alguien del
equipo, sus tareas abiertas (`le_llega_siempre`): en Mis tareas y en Don Tino.

Este archivo es puro (sin base) a propósito: las cuentas se prueban en
tests/test_alcance_del_calendario.py sin levantar nada.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import false, or_, true

URUGUAY = ZoneInfo("America/Montevideo")

# En el orden en que se muestran en el panel.
ALCANCES: tuple[str, ...] = ("nada", "1m", "2m", "12m", "todo")
NOMBRES: dict[str, str] = {
    "nada": "No lo ve",
    "1m": "1 mes",
    "2m": "2 meses",
    "12m": "12 meses",
    "todo": "Todo",
}
MESES: dict[str, int] = {"1m": 1, "2m": 2, "12m": 12}
# Los días del mes anterior que entran en la ventana.
DIAS_DEL_MES_ANTERIOR = 7

POR_DEFECTO_EXTERNO = "nada"
POR_DEFECTO_INTERNO = "todo"

NO_LO_VE = "No tenés acceso al calendario. Si lo necesitás, pedíselo a quien administra Core Tienda."

Ventana = tuple[date, date]
# Una ventana que no toca ninguna fecha: la de quien no ve el calendario. Si
# una ruta se olvidara de frenarlo antes, igual no le saldría nada.
VACIA: Ventana = (date.max, date.min)


def por_defecto(es_externo: bool) -> str:
    return POR_DEFECTO_EXTERNO if es_externo else POR_DEFECTO_INTERNO


def alcance_de(usuario) -> str:
    """El alcance guardado, o el de su tipo de cuenta si no hay uno válido
    (una fila de antes de la 0070 en un test, un valor que no existe): ante
    la duda, lo que corresponde a su tipo, y una externa nunca de más."""
    valor = getattr(usuario, "calendario_alcance", None)
    if valor in ALCANCES:
        return valor
    return por_defecto(bool(getattr(usuario, "es_externo", False)))


def ve_el_calendario(usuario) -> bool:
    return alcance_de(usuario) != "nada"


def es_limitado(usuario) -> bool:
    """Si a esta persona se le recorta el calendario (cualquier cosa menos 'todo')."""
    return alcance_de(usuario) != "todo"


def exigir_calendario(usuario) -> None:
    """403 para quien no ve el calendario. Va al principio de cada ruta que
    muestra el calendario (no en las del tablero de tarjetas)."""
    if not ve_el_calendario(usuario):
        raise HTTPException(status_code=403, detail=NO_LO_VE)


# ---------------------------------------------------------------------------
# Las fechas
# ---------------------------------------------------------------------------

def hoy_en_uruguay(ahora: datetime | None = None) -> date:
    return (ahora or datetime.now(URUGUAY)).astimezone(URUGUAY).date()


def fin_de_mes(d: date) -> date:
    primero_del_siguiente = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return primero_del_siguiente - timedelta(days=1)


def sumar_meses(d: date, meses: int) -> date:
    """El primer día del mes que queda `meses` después del de `d`."""
    total = d.year * 12 + (d.month - 1) + meses
    return date(total // 12, total % 12 + 1, 1)


def ventana_de_alcance(hoy: date, alcance: str) -> Ventana | None:
    """Las fechas que ve un alcance, contadas desde `hoy`. Pura.

    None = sin límite ('todo'). VACIA = nada ('nada', o un valor que no
    existe: ante la duda, no se muestra)."""
    if alcance == "todo":
        return None
    meses = MESES.get(alcance)
    if meses is None:
        return VACIA
    primero = date(hoy.year, hoy.month, 1)
    desde = primero - timedelta(days=DIAS_DEL_MES_ANTERIOR)
    hasta = fin_de_mes(sumar_meses(primero, meses - 1))
    return desde, hasta


def ventana_de(usuario, ahora: datetime | None = None) -> Ventana | None:
    """La ventana de hoy para esta persona (ver ventana_de_alcance)."""
    return ventana_de_alcance(hoy_en_uruguay(ahora), alcance_de(usuario))


def toca(desde: date, hasta: date, v: Ventana | None) -> bool:
    """Si una acción que va de `desde` a `hasta` toca la ventana (aunque sea
    un día). Sin ventana, todo toca. Una con las fechas al revés se toma como
    de un solo día."""
    if v is None:
        return True
    if hasta < desde:
        hasta = desde
    return desde <= v[1] and hasta >= v[0]


def condicion(modelo, v: Ventana | None):
    """La misma regla que `toca`, para el WHERE de una consulta sobre una tabla
    con `desde` y `hasta` (las barras del calendario)."""
    if v is None:
        return true()
    if v == VACIA:
        return false()
    return (modelo.desde <= v[1]) & (modelo.hasta >= v[0])


def meses_de(v: Ventana | None) -> list[str] | None:
    """Las claves 'YYYY-MM' de los meses que toca la ventana. None = todos."""
    if v is None:
        return None
    if v == VACIA:
        return []
    claves = []
    y, m = v[0].year, v[0].month
    while (y, m) <= (v[1].year, v[1].month):
        claves.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return claves


def en_palabras(alcance: str) -> str:
    return NOMBRES.get(alcance, alcance)


# ---------------------------------------------------------------------------
# Lo propio: lo que le llega aunque quede fuera de su alcance
# ---------------------------------------------------------------------------

def le_llega_siempre(usuario, tarea) -> bool:
    """Si esta tarea le llega a esta persona aunque su acción quede fuera de
    lo que ve del calendario: a alguien del EQUIPO, sus tareas abiertas (si
    no, vencen sin que las vea nunca). Es la regla de Mis tareas, y la misma
    que usa Don Tino (19/11/2026, Ivan: "Don Tino debe amoldarse a cada
    usuario"). A una cuenta externa no: lo suyo es el tablero (ver
    es_tarjeta_propia en app/services/entregas.py). Sus tareas son las que
    tiene asignadas y las que lleva por Tienda (`responsable_id`, 0090). Pura."""
    mias = (usuario.id is not None and usuario.id in (
        getattr(tarea, "asignado_a_id", None), getattr(tarea, "responsable_id", None),
    ))
    return not getattr(usuario, "es_externo", False) and mias and tarea.estado != "hecha"


def condicion_le_llega_siempre(modelo, usuario):
    """La misma regla que `le_llega_siempre`, para el WHERE de una consulta
    sobre las tareas."""
    if getattr(usuario, "es_externo", False):
        return false()
    return or_(modelo.asignado_a_id == usuario.id, modelo.responsable_id == usuario.id) & (modelo.estado != "hecha")
