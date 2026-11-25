"""Las tarjetas sin acción: lo que se pide fuera del calendario (24/11/2026).

Pedido de Ivan: "deberíamos poder crear acciones o tarjetas también de cosas
que estén por fuera del calendario, quizás mismo en los tableros podríamos
tener la opción de crear una tarjeta". En Tableros, "Nueva tarjeta" abre el
mismo formulario de una tarea (¿Qué se pide?, ¿Quién la hace?...) y la tarjeta
nace sin acción: aparece en el tablero de quien la hace y en Mis tareas, y no
en el calendario.

Cómo se guarda, y por qué así: cada mundo tiene UNA acción de sistema, oculta,
de la que cuelgan sus tarjetas sin acción (id fijo `sin-accion-<mundo>`, se
crea sola con la primera tarjeta). La otra forma era dejar `barra_id` en null
y darle a la tarea un mundo propio: hay unas treinta consultas que pasan por
la acción (el mundo, el alcance del calendario de 0070, la agencia, los
adjuntos, las entregas, el análisis, los avisos, Mis tareas, Don Tino) y cada
una habría que cambiarla; una que se olvidara dejaba afuera las tarjetas sin
acción o, peor, se salteaba un permiso. Con la acción de sistema todos esos
caminos siguen siendo los mismos de siempre, probados: la tarjeta es una
tarjeta más, con una acción de su mundo.

Lo que cuida esta acción para no ser "una acción más":
- Va del 01/01/2000 al 31/12/2099: toca cualquier ventana, así que nunca queda
  afuera del alcance de nadie que vea el calendario (0070). Quien no lo ve
  sigue viendo solo sus tarjetas, como con cualquier otra.
- No aparece en el calendario (/calendario/datos), ni en Don Tino como acción,
  ni se puede abrir, cambiar, borrar, copiar, ni cargarle piezas, avisos,
  plantillas o fotos: `_barra_o_404` la trata como inexistente salvo para
  cambiar una de sus tareas, y su id no se puede usar para crear una acción.
- Donde se nombra la acción de una tarea, dice "Sin acción" (su nombre) y la
  pantalla no ofrece abrirla (`sinAccion` en lo que viaja). En los avisos del
  calendario se dice "sin acción" y la IA de la revisión sabe que es un pedido
  suelto (no compara la pieza con una acción).
- Todo lo que nace ahí es una tarjeta: si no se eligió qué se pide ("Otra
  cosa"), el tipo es "otro", así tiene entregas y aparece en el tablero de
  quien la hace (si no, una tarea común quedaría solo en Mis tareas).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mundos import MUNDOS
from app.models.calendario import CalendarioBarra

PREFIJO = "sin-accion-"
NOMBRE = "Sin acción"
DESDE = date(2000, 1, 1)
HASTA = date(2099, 12, 31)
# Una sección que lleva tareas (las de `_CON_AVISOS` en las rutas). La banda
# es lo que se ve como categoría: nunca se muestra, pero que diga qué es.
SECCION = "comercial"
BANDA = NOMBRE
# Si no se eligió qué se pide: el tipo "Otro" del catálogo (tipos_de_tarea).
TIPO_POR_DEFECTO = "otro"


def id_de(mundo: str) -> str:
    return f"{PREFIJO}{mundo}"


# Las de todos los mundos: para sacarlas de lo que lista acciones. Pura.
IDS: tuple[str, ...] = tuple(id_de(m) for m in MUNDOS)


def es_sin_accion(barra_id: str | None) -> bool:
    """Si es la acción de sistema de las tarjetas sin acción. Se mira el
    prefijo (y no solo IDS) para que ningún id con esa forma se pueda usar
    como una acción común. Pura."""
    return bool(barra_id) and barra_id.startswith(PREFIJO)


def nombre_para_texto(barra) -> str | None:
    """El nombre de la acción para un aviso o para la IA: None si es la de
    las tarjetas sin acción (el texto dice "sin acción"). Pura."""
    return None if es_sin_accion(getattr(barra, "id", None)) else barra.nombre


async def la_de(db: AsyncSession, mundo: str, *, bloquear: bool = False) -> CalendarioBarra:
    """La acción de sistema del mundo; si todavía no existe, se crea. Dos
    tarjetas que nacen a la vez no chocan: el alta es "si no está" (ON
    CONFLICT DO NOTHING) y después se lee."""
    if mundo not in MUNDOS:
        raise ValueError(f"Mundo desconocido: {mundo}")
    await db.execute(
        insert(CalendarioBarra)
        .values(
            id=id_de(mundo), mundo=mundo, seccion=SECCION, banda=BANDA, carril=0,
            nombre=NOMBRE, desde=DESDE, hasta=HASTA,
        )
        .on_conflict_do_nothing(index_elements=[CalendarioBarra.id])
    )
    consulta = select(CalendarioBarra).where(CalendarioBarra.id == id_de(mundo))
    if bloquear:
        consulta = consulta.with_for_update()
    return (await db.execute(consulta)).scalar_one()
