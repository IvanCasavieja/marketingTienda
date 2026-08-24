"""Lo que el modulo de cenefas aprende de como se lo usa.

Tres reglas que no se negocian:

1. **Nada se activa solo.** Todo nace `propuesto`. Una persona aprueba. Un
   agente que se auto-alimenta sin control aprende tambien los errores, y
   despues los repite con confianza.
2. **Registrar lo mismo dos veces no duplica: suma.** La unicidad es
   (tipo, clave), asi que la repeticion se vuelve evidencia. Una columna que se
   llamo igual en cuatro listados vale mucho mas que una que aparecio una vez.
3. **Lo descartado no vuelve.** Si alguien dijo que no, registrarlo de nuevo
   sube el contador pero no lo revive. Sin esto, cada corrida resucitaria lo
   que se acaba de rechazar.

De donde sale
-------------
De lo que ya pasa, sin pedirle nada a nadie:

- **mapeo**: alguien dijo explicitamente "esta columna es esta variable" en la
  pantalla de mapeo. Es la fuente mas confiable que hay: lo decidio una persona.
- **revision_previa**: apareci una columna que el motor no reconoce y hay una
  variable que se le parece. Es una sospecha, no un hecho.
- **job**: como salio una corrida con una plantilla.
- **grilla**: una correccion hecha a mano sobre lo que propuso el sistema.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cenefa_conocimiento import CenefaConocimiento

# Cuantas veces hay que ver algo antes de que valga la pena proponerlo. Uno
# solo suele ser ruido: un typo en el encabezado de un Excel suelto no es
# conocimiento, es un error de esa vez.
MINIMO_PARA_PROPONER = 2

# Confianza de cada origen. Un mapeo lo decidio una persona; una sospecha de la
# revision previa la dedujo un algoritmo de parecido.
_CONFIANZA = {"mapeo": "alta", "grilla": "alta", "manual": "alta",
              "revision_previa": "media", "job": "media"}


def normalizar(t: str) -> str:
    s = unicodedata.normalize("NFD", str(t)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s.lower())


async def registrar(
    db: AsyncSession,
    *,
    tipo: str,
    clave: str,
    contenido: str,
    origen: str,
    detalle: dict[str, Any] | None = None,
) -> CenefaConocimiento:
    """Anota algo aprendido. Si ya estaba, suma una vista en vez de duplicar.

    No commitea: lo hace el caller junto con el resto de su transacción, así
    aprender nunca puede dejar a medias la operación real.
    """
    clave_norm = normalizar(clave)[:200]
    existente = (await db.execute(
        select(CenefaConocimiento).where(
            CenefaConocimiento.tipo == tipo,
            CenefaConocimiento.clave == clave_norm,
        )
    )).scalar_one_or_none()

    if existente is not None:
        existente.veces_visto += 1
        existente.visto_at = func.now()
        # Lo descartado NO revive: alguien ya dijo que no. Se sigue contando
        # para saber cuántas veces volvió a aparecer, que es información útil
        # cuando se revisa una decisión vieja.
        if existente.estado == "propuesto":
            existente.contenido = contenido
            existente.detalle = {**(existente.detalle or {}), **(detalle or {})}
        return existente

    nuevo = CenefaConocimiento(
        tipo=tipo,
        clave=clave_norm,
        contenido=contenido,
        origen=origen,
        detalle={**(detalle or {}), "confianza": _CONFIANZA.get(origen, "media")},
        estado="propuesto",
        veces_visto=1,
    )
    db.add(nuevo)
    return nuevo


async def listar(
    db: AsyncSession, estado: str | None = None, tipo: str | None = None, limite: int = 200,
) -> list[CenefaConocimiento]:
    stmt = select(CenefaConocimiento)
    if estado:
        stmt = stmt.where(CenefaConocimiento.estado == estado)
    if tipo:
        stmt = stmt.where(CenefaConocimiento.tipo == tipo)
    # Lo más visto primero: es lo que más evidencia tiene y lo que más rinde
    # revisar si hay poco tiempo.
    stmt = stmt.order_by(CenefaConocimiento.veces_visto.desc(),
                         CenefaConocimiento.visto_at.desc()).limit(limite)
    return list((await db.execute(stmt)).scalars().all())


async def decidir(
    db: AsyncSession, id_: Any, estado: str, user_id: int, contenido: str | None = None,
) -> CenefaConocimiento | None:
    """Aprueba, descarta o archiva. `contenido` permite corregir el texto al aprobar."""
    if estado not in ("activo", "descartado", "archivado", "propuesto"):
        raise ValueError(f"estado desconocido: {estado}")
    item = await db.get(CenefaConocimiento, id_)
    if item is None:
        return None
    item.estado = estado
    item.decidido_por = user_id
    item.decidido_at = func.now()
    if contenido and contenido.strip():
        item.contenido = contenido.strip()
    return item


async def contexto_para_el_agente(db: AsyncSession, limite: int = 60) -> str:
    """Lo aprobado, como texto para meter en el prompt del agente.

    Solo lo `activo`: lo propuesto todavía no lo miró nadie y lo descartado se
    rechazó. Vacío si no hay nada aprobado -- el agente funciona igual, esto
    suma contexto, no lo reemplaza.
    """
    items = await listar(db, estado="activo", limite=limite)
    if not items:
        return ""
    por_tipo: dict[str, list[str]] = {}
    for i in items:
        por_tipo.setdefault(i.tipo, []).append(i.contenido)
    partes = ["Lo que este equipo ya aprendió trabajando con cenefas "
              "(aprobado por una persona, tratalo como cierto):"]
    for tipo, frases in sorted(por_tipo.items()):
        partes.append(f"\n{tipo}:")
        partes.extend(f"  - {f}" for f in frases)
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# Captura: de lo que pasa, a una propuesta
# ---------------------------------------------------------------------------

async def aprender_de_mapeo(
    db: AsyncSession, mapeo: dict[str, str], destino: str | None = None,
) -> int:
    """Una persona dijo en la pantalla de mapeo que tal columna es tal variable.

    Es la fuente más confiable que hay: no es una deducción, es una decisión.
    """
    n = 0
    for variable, columna in (mapeo or {}).items():
        if not columna or not str(columna).strip():
            continue
        await registrar(
            db,
            tipo="alias_columna",
            clave=f"{columna}->{variable}",
            contenido=f'La columna «{columna}» es la variable {variable}'
                      + (f' (en {destino})' if destino else ""),
            origen="mapeo",
            detalle={"columna": columna, "variable": variable, "destino": destino},
        )
        n += 1
    return n


async def aprender_de_revision(
    db: AsyncSession, hallazgos: list[dict[str, str]], excel: str | None = None,
) -> int:
    """Sospechas de la revisión previa: una columna sin reconocer que se parece
    a una variable.

    Solo las que traen una sugerencia concreta. "No sé qué es esta columna" no
    es conocimiento; "esta columna probablemente sea precioRegular" sí.
    """
    n = 0
    # Una misma corrida puede reportar la misma columna en dos avisos distintos
    # ("no se usa" y "las N cenefas salen sin X"). Es el mismo hecho visto una
    # vez: si se contara dos, el contador de evidencia mentiria el doble.
    ya = set()
    for h in hallazgos or []:
        if h.get("tipo") not in ("columna_no_reconocida", "variable_vacia"):
            continue
        d = h.get("detalle_datos") or {}
        columna, variable = d.get("columna"), d.get("variable")
        if not columna or not variable:
            continue
        if (columna, variable) in ya:
            continue
        ya.add((columna, variable))
        await registrar(
            db,
            tipo="alias_columna",
            clave=f"{columna}->{variable}",
            contenido=f'La columna «{columna}» parece ser la variable {variable}',
            origen="revision_previa",
            detalle={"columna": columna, "variable": variable, "excel": excel},
        )
        n += 1
    return n


async def aprender_de_plantilla(
    db: AsyncSession, nombre: str, observacion: str, detalle: dict | None = None,
) -> CenefaConocimiento:
    """Algo que una plantilla hace y conviene saber antes de usarla."""
    return await registrar(
        db,
        tipo="plantilla",
        clave=f"{nombre}::{observacion[:60]}",
        contenido=f'Plantilla «{nombre}»: {observacion}',
        origen="job",
        detalle={**(detalle or {}), "plantilla": nombre},
    )
