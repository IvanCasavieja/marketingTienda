"""Las agencias que ya existen: los tres tableros y las empresas de las
cuentas externas.

Pedido de Ivan (19/11/2026): la empresa de una cuenta externa se escribía a
mano en el panel de usuarios, y con una letra de diferencia («Disenadores»
sin ñ, «diseñadores » con un espacio) la cuenta quedaba en otra agencia y no
veía sus tarjetas. "¿No debería ser una selección?". Sí:

- El panel la elige de esta lista (GET /admin/agencias). Quien administra
  puede agregar una nueva.
- Lo que se guarda pasa por `como_ya_esta`: si lo escrito es una agencia que
  ya existe (sin mirar tildes, la ñ, mayúsculas ni espacios de más), se
  guarda con el nombre que ya tiene. Vale para la cuenta y para la agencia
  de una tarjeta.
- Lo que ya estaba guardado no se toca: las comparaciones son sin tildes ni
  mayúsculas (app/core/externos.py, `misma_empresa` y `empresa_en_sql`), así
  que una cuenta vieja con «Disenadores» ve igual las tarjetas de
  «Diseñadores».

«Diseñadores» es una AGENCIA EXTERNA, como Publicis y Another Monday: no son
los diseñadores de Tienda.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import externos
from app.core.mundos import MUNDOS, es_mundo, exigir_mundo
from app.core.tableros import TABLEROS
from app.models.user import User


async def existentes(db: AsyncSession, *, menos: int | None = None) -> list[str]:
    """Las agencias, cada una una sola vez: primero los tres tableros
    (Publicis, Another Monday, Diseñadores), escritos como en
    app/core/tableros.py, y después las empresas de las cuentas externas,
    escritas como en su primera cuenta (la que se guardó antes).

    `menos`: una cuenta que no cuenta (la que se está editando). Si es la
    única de su agencia, se le puede corregir cómo se escribe ("Agencia
    Oceano" -> "Agencia Océano"); si no, se la deja como la tiene el resto."""
    consulta = (
        select(User.empresa)
        .where(User.es_externo.is_(True), User.empresa.isnot(None))
        .group_by(User.empresa)
        .order_by(func.min(User.id))
    )
    if menos is not None:
        consulta = consulta.where(User.id != menos)
    empresas = (await db.execute(consulta)).scalars().all()
    return externos.sin_repetir([*TABLEROS, *empresas])


async def como_ya_esta(db: AsyncSession, texto: str | None, *, menos: int | None = None) -> str | None:
    """El nombre con el que se guarda la agencia `texto`: el de la que ya
    existe, si es la misma (ver externos.empresa_como_ya_esta); si no, el
    escrito, sin espacios de más. None si viene vacío."""
    if not externos.clave_de_empresa(texto):
        return None
    return externos.empresa_como_ya_esta(texto, await existentes(db, menos=menos))


async def mundos_con_trabajo(db: AsyncSession, usuario) -> list[str]:
    """Los mundos donde una cuenta externa tiene trabajo: los de las acciones
    de sus tareas (las suyas o las de su agencia, incluidas las tarjetas sin
    acción), en el orden del catálogo. Se calcula, no se elige (25/11/2026,
    Ivan: elegirle mundos a una agencia "sería al pedo"): es lo que ve del
    calendario si se lo habilitan, y lo que dice /auth/me."""
    from app.models.calendario import CalendarioBarra, CalendarioTarea

    if not externos.es_externo(usuario):
        return []
    hay = set((await db.execute(
        select(CalendarioBarra.mundo)
        .join(CalendarioTarea, CalendarioTarea.barra_id == CalendarioBarra.id)
        .where(externos.condicion_tarea_propia(CalendarioTarea, usuario))
        .distinct()
    )).scalars())
    return [m for m in MUNDOS if m in hay]


async def exigir_mundo_del_calendario(db: AsyncSession, usuario, mundo: str) -> str:
    """Para lo que muestra el calendario de un mundo (no una tarjeta): alguien
    del equipo, sus mundos (exigir_mundo); una cuenta externa, los mundos
    donde su agencia tiene trabajo (mundos_con_trabajo). Si no, 422 o 403."""
    if not externos.es_externo(usuario):
        return exigir_mundo(usuario, mundo)
    if not es_mundo(mundo):
        raise HTTPException(status_code=422, detail="Ese mundo no existe")
    if mundo not in await mundos_con_trabajo(db, usuario):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"No tenés acceso a {MUNDOS[mundo]}")
    return mundo
