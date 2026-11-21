"""Copiar una acción del calendario a otra fecha ("copiar del año pasado").

Pedido de Ivan (15/11/2026): las acciones comerciales se repiten cada año
(Ciberlunes, Día de la Madre...) y el Ciberlunes 2026 tiene que poder nacer
del 2025 con todo lo que tenía: sus piezas, sus tareas con sus subtareas y sus
avisos. Lo que estaba hecho el año pasado vuelve a pendiente; lo que tenía
fecha se corre lo mismo que la acción.

Acá está la parte que no toca la base, para probarla sin Postgres: qué valores
lleva cada fila nueva. La ruta (`POST /calendario/barras/{id}/copiar`, en
app/api/routes/calendario.py) busca las filas, decide quién sigue pudiendo
ver el mundo y guarda todo en una transacción.

Las columnas se copian de forma GENÉRICA, leyendo el modelo: todas salvo la
clave, los timestamps y las que se resetean a propósito. Así, cuando alguien
le agrega una columna a `calendario_tareas` o a `calendario_piezas` (el "ancla"
de vencimiento relativo, por ejemplo), la copia la lleva sola, sin que haya
que acordarse de venir a tocar esto. La regla para lo nuevo:

- una fecha (`Date`) se corre lo mismo que la acción;
- un momento (`DateTime`) es un timestamp de ESA fila ("cuándo se creó",
  "cuándo se tocó"): no se copia, lo pone la base;
- todo lo demás se copia tal cual.
"""
from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Date, DateTime, inspect

# 52 semanas: la copia cae el mismo día de la semana que la original (el
# Ciberlunes es lunes los dos años). 365 lo corría un día.
DIAS_AL_ANIO_QUE_VIENE = 364

# Los años que se reconocen en un nombre: los mismos que acepta una fecha.
_ANIO_MINIMO, _ANIO_MAXIMO = 2000, 2100
# Cuatro dígitos sueltos: "Ciberlunes 2025", "Fin de año 2025-2026". No el
# "20250" de un código ni el "12025" de otra cosa.
_ANIO = re.compile(r"(?<!\d)\d{4}(?!\d)")


def al_anio_que_viene(desde: date) -> date:
    return desde + timedelta(days=DIAS_AL_ANIO_QUE_VIENE)


def nombre_para_la_copia(nombre: str, desde: date, hasta: date, desde_nueva: date) -> str:
    """El nombre de la copia: si arranca en otro año que la original, los
    años del nombre se corren lo mismo ("Ciberlunes 2025" → "Ciberlunes 2026").

    Solo los años que tienen que ver con las fechas de la acción (de un año
    antes de que arranque a un año después de que termine): el "Mundial 2030"
    de una acción de 2025 no es el año de la acción y queda como está.
    Si la copia arranca en el mismo año, el nombre no cambia."""
    salto = desde_nueva.year - desde.year
    if salto == 0:
        return nombre

    def correr(m: re.Match) -> str:
        anio = int(m.group(0))
        if not (desde.year - 1 <= anio <= hasta.year + 1):
            return m.group(0)
        nuevo = anio + salto
        return str(nuevo) if _ANIO_MINIMO <= nuevo <= _ANIO_MAXIMO else m.group(0)

    return _ANIO.sub(correr, nombre)


def nuevo_id(prefijo: str) -> str:
    """Un id para una fila copiada. El de la acción nueva lo manda el front
    (así un reintento no la duplica); el de lo que cuelga de ella lo pone el
    servidor, que es quien lo crea."""
    return f"{prefijo}-{uuid.uuid4().hex[:20]}"


def valores_copiados(
    fila: Any,
    corrimiento: timedelta,
    fijos: dict[str, Any],
    excluir: Iterable[str] = (),
) -> dict[str, Any]:
    """Los valores de la copia de `fila`: todas las columnas de su modelo,
    salvo la clave, los timestamps y `excluir`; las fechas, corridas; y
    `fijos` encima de todo (el id nuevo, la acción nueva, lo que se resetea).

    Ver la regla en el docstring del módulo."""
    excluir = set(excluir)
    out: dict[str, Any] = {}
    for atributo in inspect(type(fila)).column_attrs:
        clave = atributo.key
        columna = atributo.columns[0]
        if clave in fijos or clave in excluir or columna.primary_key:
            continue
        if isinstance(columna.type, DateTime):
            continue
        valor = getattr(fila, clave)
        if isinstance(columna.type, Date) and valor is not None:
            valor = valor + corrimiento
        elif isinstance(valor, (list, dict)):
            # Una lista JSON compartida entre la original y la copia: tocar
            # una no tiene que tocar la otra.
            valor = copy.deepcopy(valor)
        out[clave] = valor
    out.update(fijos)
    return out


def fechas_corridas(valores: dict[str, Any], modelo: type) -> list[date]:
    """Las fechas que quedaron en la copia (las columnas `Date` de `modelo`),
    para revisar que sigan siendo de un año real."""
    out = []
    for atributo in inspect(modelo).column_attrs:
        if isinstance(atributo.columns[0].type, Date):
            v = valores.get(atributo.key)
            if isinstance(v, date):
                out.append(v)
    return out


# ---------------------------------------------------------------------------
# La acción y lo que cuelga de ella
# ---------------------------------------------------------------------------

def copiar_la_accion(
    origen: Any, barra_id: str, corrimiento: timedelta, nombre: str, carril: int, quien: int | None,
) -> dict[str, Any]:
    """La acción nueva: todos los campos de la original (mundo, sección,
    categoría, color, formato, hora...), con las fechas corridas, el nombre y
    el renglón que corresponden a las fechas nuevas, y firmada por quien copia.

    El estado de un envío suelto es como el de una pieza: vuelve a pendiente."""
    return valores_copiados(origen, corrimiento, {
        "id": barra_id,
        "nombre": nombre,
        "carril": carril,
        "estado": "pendiente" if origen.estado is not None or origen.seccion == "envio" else None,
        "creado_por_id": quien,
        "actualizado_por_id": quien,
    })

def copiar_piezas(
    piezas: Iterable[Any], barra_id: str, corrimiento: timedelta,
    hacer_id: Callable[[str], str] = nuevo_id,
) -> list[dict[str, Any]]:
    """Las piezas, en pendiente y sin la marca de SharePoint: lo del año
    pasado se publicó el año pasado. Sus fechas propias se corren con la
    acción."""
    return [
        valores_copiados(p, corrimiento, {
            "id": hacer_id("pz"), "barra_id": barra_id,
            "estado": "pendiente", "en_sharepoint": False,
        })
        for p in piezas
    ]


def en_orden_de_alta(tareas: Iterable[Any]) -> list[Any]:
    """Las tareas con cada madre antes que sus hijas: la subtarea apunta a su
    madre, que tiene que estar guardada primero. Dentro de cada nivel, en el
    orden de la ficha."""
    lista = list(tareas)
    padres = {t.id: t.parent_id for t in lista}

    def nivel(t) -> int:
        n, actual, vistos = 0, t.parent_id, set()
        # `vistos` corta un ciclo: no debería haber, pero no puede colgar esto.
        while actual is not None and actual in padres and actual not in vistos:
            vistos.add(actual)
            n += 1
            actual = padres[actual]
        return n

    return sorted(lista, key=lambda t: (nivel(t), t.orden or 0, t.id))


@dataclass
class TareasCopiadas:
    # En orden de alta (madres primero), listas para guardar.
    filas: list[dict[str, Any]] = field(default_factory=list)
    # Cuántas perdieron a su responsable porque ya no puede abrir el mundo,
    # o porque es de una agencia y la tarea es de Tienda (19/11/2026).
    sin_responsable: int = 0


def copiar_tareas(
    tareas: Iterable[Any], barra_id: str, corrimiento: timedelta,
    responsables_validos: set[int], creado_por: int | None,
    hacer_id: Callable[[str], str] = nuevo_id,
    *, de_agencias: Iterable[int] = (),
) -> TareasCopiadas:
    """Las tareas, en pendiente y con el vencimiento corrido. La estructura
    de subtareas se mantiene con ids nuevos. El responsable sigue solo si
    todavía puede abrir el mundo (`responsables_validos`): asignarle una tarea
    a alguien que no la vería no sirve, igual que al crearla.

    `de_agencias`: las cuentas externas (Publicis, Another Monday,
    Diseñadores... agencias de afuera de Tienda). Una tarea que no es "para
    la agencia" (de Tienda, o lo de una agencia de afuera, que carga alguien
    del equipo) no sigue a nombre de una de ellas: se copia sin responsable,
    como al aplicar una plantilla. Pasaba con alguien que llevaba la tarea y
    después pasó a ser de una agencia: la copia le nacía a su nombre, con su
    aviso y su tarjeta (revisión del 19/11/2026). La pieza de una agencia sí
    sigue a nombre de alguien de ella.

    `creado_por` es quien copia: es quien las está cargando ahora, y a quien
    le llega el aviso cuando alguien termina una."""
    externas = set(de_agencias)
    ordenadas = en_orden_de_alta(tareas)
    ids = {t.id: hacer_id("ta") for t in ordenadas}
    out = TareasCopiadas()
    for t in ordenadas:
        responsable = t.asignado_a_id
        de_tienda_a_una_agencia = responsable in externas and getattr(t, "para", "tienda") != "agencia"
        if responsable is not None and (responsable not in responsables_validos or de_tienda_a_una_agencia):
            responsable = None
            out.sin_responsable += 1
        out.filas.append(valores_copiados(t, corrimiento, {
            "id": ids[t.id], "barra_id": barra_id,
            # Una madre que no es de esta acción no debería existir; si
            # aparece, la copia queda suelta en vez de apuntar a otra acción.
            "parent_id": ids.get(t.parent_id) if t.parent_id else None,
            "estado": "pendiente",
            "asignado_a_id": responsable,
            "creado_por_id": creado_por,
        }))
    return out


def ids_de_personas(valores: Iterable[Any]) -> list[int]:
    """Los ids de una lista de destinatarios, sin repetir y sin lo que no sea
    un número (la lista es JSON: puede traer cualquier cosa)."""
    out: list[int] = []
    for v in valores or []:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n not in out:
            out.append(n)
    return out


@dataclass
class AvisosCopiados:
    filas: list[dict[str, Any]] = field(default_factory=list)
    # Personas sacadas de algún aviso porque ya no pueden abrir el mundo, o
    # porque ahora son de una agencia (21/11/2026).
    destinatarios_quitados: int = 0
    # Avisos que se quedaron sin nadie y por eso no se copiaron.
    sin_nadie: int = 0


def copiar_avisos(
    avisos: Iterable[Any], barra_id: str, corrimiento: timedelta,
    destinatarios_validos: set[int], creado_por: int | None,
    hacer_id: Callable[[str], str] = nuevo_id,
    piezas_copiadas: dict[str, str] | None = None,
    *, de_agencias: Iterable[int] = (),
) -> AvisosCopiados:
    """Los avisos, con los mismos días antes (el aviso guarda la anticipación,
    no la fecha: se corre solo con la acción). Quien ya no puede ver el mundo
    sale de la lista; un aviso que se queda sin nadie no se copia, porque no
    le llegaría a nadie (y al configurarlo a mano tampoco se puede).

    `de_agencias`: las cuentas externas (Publicis, Another Monday,
    Diseñadores... agencias de afuera de Tienda). Los avisos son internos: al
    configurarlos no se puede elegir una, y a una que ya estaba no le salen
    (calendario_avisos.puede_recibir_el_aviso). Pero quien estaba en un aviso
    y después pasó a ser de una agencia sigue abriendo el mundo, y la copia
    la dejaba en el aviso nuevo: ahora sale, y se cuenta con los demás que
    salen (revisión del 19/11/2026, arreglado el 21/11/2026).

    Un aviso contado desde un envío (0084) pasa a contarse desde el envío de
    la copia: `piezas_copiadas` dice qué pieza nueva es cada vieja. Sin ella
    (o si el envío no se copió), se cuenta desde que arranca la acción."""
    piezas_copiadas = piezas_copiadas or {}
    externas = set(de_agencias)
    out = AvisosCopiados()
    for a in avisos:
        pedidos = ids_de_personas(a.destinatarios)
        quedan = [u for u in pedidos if u in destinatarios_validos and u not in externas]
        out.destinatarios_quitados += len(pedidos) - len(quedan)
        if not quedan:
            out.sin_nadie += 1
            continue
        out.filas.append(valores_copiados(a, corrimiento, {
            "id": hacer_id("av"), "barra_id": barra_id,
            "destinatarios": quedan, "creado_por_id": creado_por,
            "pieza_id": piezas_copiadas.get(getattr(a, "pieza_id", None) or ""),
        }))
    return out


def tareas_por_responsable(filas: Iterable[dict[str, Any]], quien_copia: int | None) -> dict[int, list[dict[str, Any]]]:
    """Las tareas copiadas de cada responsable, en el orden de la ficha, para
    mandarle UN aviso a cada uno y no uno por tarea. Quien copia no se avisa
    a sí mismo, igual que al crear una tarea."""
    out: dict[int, list[dict[str, Any]]] = {}
    for f in filas:
        uid = f.get("asignado_a_id")
        if uid is not None and uid != quien_copia:
            out.setdefault(uid, []).append(f)
    return out
