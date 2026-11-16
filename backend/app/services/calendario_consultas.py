"""Lo que Don Tino puede leer del calendario para contestar preguntas.

Pedido (15/11/2026): que a Don Tino se le pueda preguntar "¿qué piezas de
Express vencen esta semana y siguen sin aprobar?", "¿qué tengo que hacer hoy?",
"¿cómo viene el Ciberlunes?" o "¿quién está más cargado la semana que viene?",
y que arme el estado de una acción para mandarle a gerencia.

Tres reglas que cuida este módulo, y por qué:

1. **Lo mismo que la pantalla, ni una cosa más.** Don Tino contesta con los
   permisos de quien le pregunta: hace falta `calendario.view` y solo se mira
   en los mundos que esa persona abre (`mundos_de`). Los nombres de las
   personas salen de la misma regla que usa la pantalla (`/calendario/personas`):
   quien ya no ve ese calendario aparece como "alguien que ya no ve este
   calendario", igual que en la ficha. El filtro por mundo va en la consulta
   Y se vuelve a aplicar sobre lo que vuelve de la base: si un cambio futuro
   en una consulta se lo olvida, igual no se escapa nada de otro negocio.

2. **Respuestas chicas.** Lo que devuelve cada herramienta viaja entero al
   modelo en cada vuelta y se paga por token. Cada lista tiene tope, los
   textos largos se cortan y el JSON entero no pasa de MAX_BYTES. Si se
   recorta, se dice cuánto quedó afuera, para que el modelo lo aclare en vez
   de contestar como si fuera todo.

3. **Las fechas las resuelve el servidor, en hora de Uruguay.** "Esta semana"
   o "mañana" no quedan a la cuenta del modelo: la herramienta recibe el
   período por nombre y lo traduce acá, con America/Montevideo. A las 22 de un
   domingo en Montevideo ya es lunes en UTC, y "esta semana" no puede saltar a
   la siguiente por eso. La semana va de lunes a domingo.

Las lecturas a la base están todas en `FuenteCalendario`, aparte, para que las
pruebas las cambien por datos en memoria sin una base.

4. **Una cuenta externa (la agencia) ve lo mismo que en la pantalla.** Hoy no
   tiene Don Tino (ver PERMISOS_DE_EXTERNOS en app/core/externos.py), pero si
   algún día se le habilita, sus herramientas ya salen recortadas:
   `FuenteDeExterno` envuelve a la fuente y deja pasar solo las acciones que
   tocan su ventana, solo SUS tareas, ningún aviso y, de las personas, solo
   las de su empresa. La carga del equipo y los avisos no se le contestan.
"""
from __future__ import annotations

import json
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select

from app.core import externos
from app.core.mundos import MUNDOS, mundos_de, puede_abrir
from app.models.calendario import CalendarioAviso, CalendarioBarra, CalendarioPieza, CalendarioTarea
from app.models.user import User
from app.services.calendario_avisos import SIN_CATEGORIA, puede_ver_el_calendario

URUGUAY = ZoneInfo("America/Montevideo")

# Tope de lo que devuelve UNA herramienta, en bytes de JSON (UTF-8). ~3.000
# tokens: alcanza para una semana cargada y no llena el contexto de vueltas
# siguientes. El /datos de un mes entero ronda los 900 KB: eso nunca viaja.
MAX_BYTES = 12_000
# Tope de elementos por lista antes de medir bytes: nadie lee 300 renglones
# en un chat, y así el recorte por bytes casi nunca tiene que entrar.
MAX_ITEMS = 60
# Tope de filas por consulta: un freno, no un recorte esperable.
MAX_FILAS_SQL = 2_000
RANGO_MAXIMO_DIAS = 400

ESTADOS_PIEZA = ("pendiente", "en-proceso", "aprobado", "publicado")
SIN_APROBAR = ("pendiente", "en-proceso")
ESTADOS_TAREA = ("pendiente", "en-proceso", "hecha")
ABIERTAS = ("pendiente", "en-proceso")
SECCIONES = ("comercial", "envio", "retail", "header")
# Lo que se lista si no se pide una sección: los headers cargados a mano son
# casi todos derivados y no le dicen nada a nadie en un chat.
SECCIONES_POR_DEFECTO = ("comercial", "envio", "retail")

AREAS = {
    "web-home": "Web · Home",
    "web-landing": "Web · Landing de la acción",
    "fisico": "Físico",
    "email": "Email",
    "whatsapp": "WhatsApp",
    "push": "Push",
}

PERIODOS = (
    "hoy", "manana", "ayer", "esta_semana", "semana_que_viene", "semana_pasada",
    "este_mes", "mes_que_viene", "mes_pasado", "proximos_7_dias", "proximos_30_dias",
)

# Igual que la ficha (BloqueTareas / BloqueAvisos): de quien ya no abre ese
# calendario no se dice el nombre.
NADIE = "alguien que ya no ve este calendario"
SIN_ASIGNAR = "sin asignar"


class ConsultaInvalida(ValueError):
    """Un pedido que no se puede contestar (fecha mal escrita, mundo ajeno...).
    El mensaje va al modelo, que se lo explica a la persona."""


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------

def hoy_en_uruguay(ahora: datetime | None = None) -> date:
    return (ahora or datetime.now(URUGUAY)).astimezone(URUGUAY).date()


def _primero_de_mes(d: date, meses: int = 0) -> date:
    m = d.month - 1 + meses
    return date(d.year + m // 12, m % 12 + 1, 1)


def rango_de_periodo(periodo: str, hoy: date) -> tuple[date, date]:
    """El período por nombre, traducido a fechas. Pura, para probarla sin base."""
    p = (periodo or "").strip().lower().replace("ñ", "n").replace(" ", "_")
    un_dia = timedelta(days=1)
    lunes = hoy - timedelta(days=hoy.weekday())
    if p == "hoy":
        return hoy, hoy
    if p == "manana":
        return hoy + un_dia, hoy + un_dia
    if p == "ayer":
        return hoy - un_dia, hoy - un_dia
    if p == "esta_semana":
        return lunes, lunes + timedelta(days=6)
    if p == "semana_que_viene":
        return lunes + timedelta(days=7), lunes + timedelta(days=13)
    if p == "semana_pasada":
        return lunes - timedelta(days=7), lunes - un_dia
    if p == "este_mes":
        return _primero_de_mes(hoy), _primero_de_mes(hoy, 1) - un_dia
    if p == "mes_que_viene":
        return _primero_de_mes(hoy, 1), _primero_de_mes(hoy, 2) - un_dia
    if p == "mes_pasado":
        return _primero_de_mes(hoy, -1), _primero_de_mes(hoy) - un_dia
    if p == "proximos_7_dias":
        return hoy, hoy + timedelta(days=6)
    if p == "proximos_30_dias":
        return hoy, hoy + timedelta(days=29)
    raise ConsultaInvalida(
        f"No conozco el período '{periodo}'. Usá uno de: {', '.join(PERIODOS)}; o desde/hasta (AAAA-MM-DD)."
    )


def _fecha(texto: Any, campo: str) -> date:
    try:
        d = date.fromisoformat(str(texto).strip()[:10])
    except ValueError:
        raise ConsultaInvalida(f"La fecha '{texto}' ({campo}) no se entiende: va como AAAA-MM-DD.")
    if not 2000 <= d.year <= 2100:
        raise ConsultaInvalida(f"La fecha '{texto}' ({campo}) no parece real: revisá el año.")
    return d


def resolver_rango(args: dict, hoy: date, por_defecto: str | None = None) -> tuple[date, date] | None:
    """`desde`/`hasta` explícitos ganan; si no, el `periodo`; si no, el de
    por defecto (None = sin filtro de fechas). Con una sola de las dos fechas
    es ese día solo."""
    desde, hasta = args.get("desde"), args.get("hasta")
    if desde or hasta:
        d = _fecha(desde or hasta, "desde")
        h = _fecha(hasta or desde, "hasta")
        if h < d:
            raise ConsultaInvalida("La fecha 'hasta' es anterior a 'desde'.")
        if (h - d).days > RANGO_MAXIMO_DIAS:
            raise ConsultaInvalida(f"El período es demasiado largo (más de {RANGO_MAXIMO_DIAS} días): acotalo.")
        return d, h
    periodo = args.get("periodo") or por_defecto
    if not periodo:
        return None
    return rango_de_periodo(periodo, hoy)


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _dias(n: int, uno: str, varios: str) -> str:
    return uno if n == 1 else varios.format(n=n)


def cuando(desde: date, hasta: date, hoy: date, *, es_envio: bool = False) -> str:
    """Dónde está una acción respecto de hoy, en palabras: así el modelo no
    tiene que hacer la cuenta (y no se equivoca de día)."""
    if es_envio:
        if desde == hoy:
            return "sale hoy"
        if desde > hoy:
            return _dias((desde - hoy).days, "sale mañana", "sale en {n} días")
        return _dias((hoy - desde).days, "salió ayer", "salió hace {n} días")
    if desde <= hoy <= hasta:
        if hasta == hoy:
            return "en curso, termina hoy"
        return "en curso, " + _dias((hasta - hoy).days, "termina mañana", "termina en {n} días")
    if hoy < desde:
        return "arranca hoy" if desde == hoy else _dias((desde - hoy).days, "arranca mañana", "arranca en {n} días")
    return _dias((hoy - hasta).days, "terminó ayer", "terminó hace {n} días")


# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------

def normalizar(texto: Any) -> str:
    """Minúsculas y sin tildes: "Cíber Lunes" encuentra "ciber lunes"."""
    t = unicodedata.normalize("NFKD", str(texto or "")).casefold()
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def corto(texto: str | None, n: int) -> str | None:
    if texto is None:
        return None
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= n else texto[: n - 1].rstrip() + "…"


def link_de_accion(barra_id: str) -> str:
    """El link que abre la ficha de la acción en la app (ver AbrirAccionDeLaUrl
    en frontend/app/(dashboard)/calendario/page.tsx)."""
    return f"/calendario?accion={quote(barra_id, safe='')}"


def categoria(b) -> str | None:
    if b.seccion == "envio":
        return AREAS.get(b.banda, b.banda)
    if b.seccion == "header":
        return f"Header, {b.banda}"
    banda = (b.banda or "").strip()
    if not banda or banda.casefold() == SIN_CATEGORIA.casefold():
        return None
    return banda


def ref_accion(b) -> dict:
    """Cómo se nombra una acción dentro de otra cosa (una pieza, una tarea)."""
    out = {"id": b.id, "nombre": corto(b.nombre, 120), "mundo": MUNDOS.get(b.mundo, b.mundo),
           "link": link_de_accion(b.id)}
    cat = categoria(b)
    if cat:
        out["categoria"] = corto(cat, 60)
    return out


def coincide(texto: str, *campos: Any) -> bool:
    buscado = normalizar(texto)
    return bool(buscado) and any(buscado in normalizar(c) for c in campos if c)


def _coincide_accion(texto: str, b) -> bool:
    return coincide(texto, b.nombre, b.banda, MUNDOS.get(b.mundo))


# ---------------------------------------------------------------------------
# Mundos y personas: lo que la persona puede ver
# ---------------------------------------------------------------------------

def _clave_de_mundo(pedido: str) -> str | None:
    p = normalizar(pedido).replace(" ", "_")
    for clave, nombre in MUNDOS.items():
        if p in (clave, normalizar(nombre).replace(" ", "_")):
            return clave
    # "express" -> tienda_express, si hay uno solo que lo contiene.
    candidatos = [c for c in MUNDOS if p and p in c]
    return candidatos[0] if len(candidatos) == 1 else None


def mundos_a_mirar(usuario, pedido: str | None) -> list[str]:
    """Los mundos donde se busca: los de la persona, o el pedido si es suyo.
    Un mundo ajeno no se mira: se dice que no tiene acceso."""
    if not puede_ver_el_calendario(usuario):
        raise ConsultaInvalida(
            "Esta persona no tiene permiso para ver el calendario (calendario.view): "
            "no le cuentes nada del calendario."
        )
    propios = mundos_de(usuario)
    if not pedido or normalizar(pedido) in ("todos", "todos los mundos"):
        return propios
    clave = _clave_de_mundo(pedido)
    disponibles = ", ".join(f"{c} ({MUNDOS[c]})" for c in propios)
    if clave is None:
        raise ConsultaInvalida(f"No existe el mundo '{pedido}'. Los que ve esta persona: {disponibles}.")
    if clave not in propios:
        raise ConsultaInvalida(
            f"Esta persona no tiene acceso a {MUNDOS[clave]}: no le cuentes nada de ese mundo. "
            f"Puede ver: {disponibles}."
        )
    return [clave]


def personas_por_mundo(usuarios: Iterable, mundos: Iterable[str]) -> dict[str, dict[int, str]]:
    """Quiénes aparecen con nombre en el calendario de cada mundo: los activos
    que lo pueden abrir. La misma regla que /calendario/personas."""
    usuarios = list(usuarios)
    return {
        m: {
            u.id: (u.full_name or u.email)
            for u in usuarios
            if puede_ver_el_calendario(u) and puede_abrir(u, m)
        }
        for m in mundos
    }


def nombre_de(uid: int | None, mundo: str, personas: dict[str, dict[int, str]], yo: int | None) -> str:
    if uid is None:
        return SIN_ASIGNAR
    nombre = personas.get(mundo, {}).get(uid)
    if nombre is None:
        return NADIE
    return f"{nombre} (vos)" if uid == yo else nombre


# ---------------------------------------------------------------------------
# Tamaño
# ---------------------------------------------------------------------------

_AVISO_DE_RECORTE = (
    "La lista era larga y se cortó: decile a la persona que hay más y que puede pedir "
    "un período más corto o un solo mundo."
)


def con_tope(datos: dict, clave: str, lista: list, tope: int = MAX_ITEMS) -> None:
    """Pone la lista con su tope y, si lo pasó, lo deja dicho para `a_json`."""
    datos[clave] = lista[:tope]
    if len(lista) > tope:
        datos.setdefault("recortado", {})[clave] = {"mostrados": tope, "total": len(lista)}


def _dump(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"), default=str)


def a_json(datos: dict, listas: tuple[str, ...], max_bytes: int = MAX_BYTES) -> str:
    """Serializa la respuesta de una herramienta sin pasarse de `max_bytes`.

    Si no entra, saca elementos del final de la lista más larga (las listas
    vienen ordenadas: lo más urgente primero) hasta que entre, y deja dicho
    en `recortado` cuántos se mostraron de cuántos. Si ni así entra, devuelve
    un error corto en vez de algo cortado a la mitad que no es JSON.

    Si la herramienta ya había cortado una lista antes (por MAX_ITEMS), lo
    dice en `recortado` y acá se respeta el total de verdad."""
    datos = dict(datos)
    previos = datos.get("recortado") or {}
    totales = {k: (previos.get(k) or {}).get("total", len(datos.get(k) or [])) for k in listas}

    def marcar() -> None:
        cortadas = {c: {"mostrados": len(datos.get(c) or []), "total": totales[c]}
                    for c in listas if len(datos.get(c) or []) < totales[c]}
        if cortadas:
            datos["recortado"] = {"aviso": _AVISO_DE_RECORTE, **cortadas}

    marcar()
    texto = _dump(datos)
    if len(texto.encode("utf-8")) <= max_bytes:
        return texto
    for k in listas:
        if isinstance(datos.get(k), list):
            datos[k] = list(datos[k])
    while True:
        con_items = [k for k in listas if datos.get(k)]
        if not con_items:
            break
        k = max(con_items, key=lambda c: len(datos[c]))
        datos[k] = datos[k][:-1]
        marcar()
        texto = _dump(datos)
        if len(texto.encode("utf-8")) <= max_bytes:
            return texto
    return _dump({"error": "La respuesta era demasiado grande: pedí algo más acotado (otro período o un solo mundo)."})


# ---------------------------------------------------------------------------
# Lecturas a la base
# ---------------------------------------------------------------------------

class FuenteCalendario:
    """Todas las lecturas a la base que hacen las herramientas. Cada una
    filtra por mundo en la consulta; las herramientas lo vuelven a filtrar."""

    def __init__(self, db):
        self.db = db

    async def barras(self, mundos, *, rango=None, secciones=None, ids=None) -> list:
        q = select(CalendarioBarra).where(CalendarioBarra.mundo.in_(list(mundos)))
        if ids is not None:
            q = q.where(CalendarioBarra.id.in_(list(ids)))
        if rango is not None:
            q = q.where(CalendarioBarra.desde <= rango[1], CalendarioBarra.hasta >= rango[0])
        if secciones:
            q = q.where(CalendarioBarra.seccion.in_(list(secciones)))
        q = q.order_by(CalendarioBarra.desde, CalendarioBarra.id).limit(MAX_FILAS_SQL)
        return list((await self.db.execute(q)).scalars())

    async def piezas_de(self, barra_ids) -> list:
        if not barra_ids:
            return []
        q = (select(CalendarioPieza).where(CalendarioPieza.barra_id.in_(list(barra_ids)))
             .order_by(CalendarioPieza.orden, CalendarioPieza.id).limit(MAX_FILAS_SQL))
        return list((await self.db.execute(q)).scalars())

    async def tareas_de(self, barra_ids) -> list:
        if not barra_ids:
            return []
        q = (select(CalendarioTarea).where(CalendarioTarea.barra_id.in_(list(barra_ids)))
             .order_by(CalendarioTarea.orden, CalendarioTarea.created_at, CalendarioTarea.id).limit(MAX_FILAS_SQL))
        return list((await self.db.execute(q)).scalars())

    async def avisos_de(self, barra_ids) -> list:
        if not barra_ids:
            return []
        q = (select(CalendarioAviso).where(CalendarioAviso.barra_id.in_(list(barra_ids)))
             .order_by(CalendarioAviso.dias_antes.desc(), CalendarioAviso.id).limit(MAX_FILAS_SQL))
        return list((await self.db.execute(q)).scalars())

    async def piezas_con_accion(self, mundos, desde: date, hasta: date) -> list[tuple]:
        """Las piezas de las acciones de esos mundos que salen entre esas
        fechas: su fecha propia o, si no tiene, el arranque de su acción."""
        sale = func.coalesce(CalendarioPieza.desde, CalendarioBarra.desde)
        q = (
            select(CalendarioPieza, CalendarioBarra)
            .join(CalendarioBarra, CalendarioBarra.id == CalendarioPieza.barra_id)
            .where(CalendarioBarra.mundo.in_(list(mundos)), CalendarioBarra.seccion == "comercial",
                   sale >= desde, sale <= hasta)
            .order_by(sale, CalendarioBarra.nombre, CalendarioPieza.orden).limit(MAX_FILAS_SQL)
        )
        return [(p, b) for p, b in (await self.db.execute(q)).all()]

    async def tareas_con_accion(
        self, mundos, *, estados, rango, incluir_vencidas: bool, incluir_sin_fecha: bool, hoy: date,
    ) -> list[tuple]:
        q = (
            select(CalendarioTarea, CalendarioBarra)
            .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
            .where(CalendarioBarra.mundo.in_(list(mundos)), CalendarioTarea.estado.in_(list(estados)))
        )
        if rango is not None:
            condiciones = [and_(CalendarioTarea.vence >= rango[0], CalendarioTarea.vence <= rango[1])]
            if incluir_vencidas:
                condiciones.append(and_(CalendarioTarea.vence < hoy, CalendarioTarea.estado != "hecha"))
            if incluir_sin_fecha:
                condiciones.append(CalendarioTarea.vence.is_(None))
            q = q.where(or_(*condiciones))
        elif not incluir_sin_fecha:
            q = q.where(CalendarioTarea.vence.is_not(None))
        q = q.order_by(
            CalendarioTarea.vence.asc().nulls_last(), CalendarioBarra.desde, CalendarioTarea.orden, CalendarioTarea.id,
        ).limit(MAX_FILAS_SQL)
        return [(t, b) for t, b in (await self.db.execute(q)).all()]

    async def titulos_de_tareas(self, ids) -> dict[str, str]:
        if not ids:
            return {}
        q = select(CalendarioTarea.id, CalendarioTarea.titulo).where(CalendarioTarea.id.in_(list(ids)))
        return {i: t for i, t in (await self.db.execute(q)).all()}

    async def avisos_con_accion(self, mundos, arranque_desde: date, arranque_hasta: date) -> list[tuple]:
        q = (
            select(CalendarioAviso, CalendarioBarra)
            .join(CalendarioBarra, CalendarioBarra.id == CalendarioAviso.barra_id)
            .where(CalendarioBarra.mundo.in_(list(mundos)),
                   CalendarioBarra.desde >= arranque_desde, CalendarioBarra.desde <= arranque_hasta)
            .order_by(CalendarioBarra.desde, CalendarioAviso.dias_antes.desc()).limit(MAX_FILAS_SQL)
        )
        return [(a, b) for a, b in (await self.db.execute(q)).all()]

    async def personas_activas(self) -> list:
        return list((await self.db.execute(select(User).where(User.is_active == True))).scalars())  # noqa: E712


def _interseccion(rango, v):
    """El pedazo de `rango` que cae en la ventana `v`, o None si no se tocan.
    Sin rango, la ventana entera."""
    if rango is None:
        return v
    d, h = max(rango[0], v[0]), min(rango[1], v[1])
    return (d, h) if d <= h else None


class FuenteDeExterno:
    """La fuente de una cuenta externa (ver app/core/externos.py): envuelve a
    otra y deja pasar solo lo que la persona ve en la pantalla. Las acciones,
    las que tocan su ventana; las tareas, solo las suyas; los avisos, ninguno
    (son internos); las personas, ella y las de su empresa.

    Cada método filtra lo que vuelve, no solo lo que pide: si una herramienta
    pide algo de más, igual no se escapa. Lo que se vio pasar queda anotado
    (`_visibles`, `_propias`) para que lo que cuelga de una acción o de una
    tarea (piezas, títulos de tareas madre) salga solo si su dueña salió."""

    def __init__(self, fuente, usuario, ventana: tuple[date, date]):
        self.fuente = fuente
        self.usuario = usuario
        self.v = ventana
        self._visibles: set[str] = set()
        self._propias: set[str] = set()

    def _toca(self, b) -> bool:
        return externos.toca(b.desde, b.hasta, self.v)

    def _anotar(self, barras) -> list:
        out = [b for b in barras if self._toca(b)]
        self._visibles.update(b.id for b in out)
        return out

    async def barras(self, mundos, *, rango=None, secciones=None, ids=None) -> list:
        acotado = _interseccion(rango, self.v)
        if acotado is None:
            return []
        return self._anotar(await self.fuente.barras(mundos, rango=acotado, secciones=secciones, ids=ids))

    async def piezas_de(self, barra_ids) -> list:
        ids = [i for i in (barra_ids or []) if i in self._visibles]
        return [p for p in await self.fuente.piezas_de(ids) if p.barra_id in self._visibles]

    async def tareas_de(self, barra_ids) -> list:
        ids = [i for i in (barra_ids or []) if i in self._visibles]
        out = [
            t for t in await self.fuente.tareas_de(ids)
            if t.barra_id in self._visibles and t.asignado_a_id == self.usuario.id
        ]
        self._propias.update(t.id for t in out)
        return out

    async def avisos_de(self, barra_ids) -> list:
        return []

    async def piezas_con_accion(self, mundos, desde: date, hasta: date) -> list[tuple]:
        return [(p, b) for p, b in await self.fuente.piezas_con_accion(mundos, desde, hasta) if self._toca(b)]

    async def tareas_con_accion(self, mundos, **kw) -> list[tuple]:
        out = [
            (t, b) for t, b in await self.fuente.tareas_con_accion(mundos, **kw)
            if self._toca(b) and t.asignado_a_id == self.usuario.id
        ]
        self._propias.update(t.id for t, _ in out)
        return out

    async def titulos_de_tareas(self, ids) -> dict[str, str]:
        # El título de una tarea madre que no es suya no sale.
        return await self.fuente.titulos_de_tareas([i for i in (ids or []) if i in self._propias])

    async def avisos_con_accion(self, mundos, arranque_desde: date, arranque_hasta: date) -> list[tuple]:
        return []

    async def personas_activas(self) -> list:
        return [
            u for u in await self.fuente.personas_activas()
            if u.id == self.usuario.id
            or (externos.es_externo(u) and externos.misma_empresa(u.empresa, self.usuario.empresa))
        ]


# Lo que no se le contesta a una cuenta externa: la carga de todo el equipo y
# los avisos (internos).
_NO_PARA_EXTERNOS = {
    "calendario_carga": "Es una cuenta externa (agencia): no ve la carga del equipo. Contale solo de sus tareas.",
    "calendario_avisos": "Es una cuenta externa (agencia): los avisos del calendario son internos y no los ve.",
}


# ---------------------------------------------------------------------------
# Las herramientas
# ---------------------------------------------------------------------------

def _rango_json(rango: tuple[date, date] | None) -> dict | None:
    return {"desde": rango[0].isoformat(), "hasta": rango[1].isoformat()} if rango else None


def _contexto(mundos: list[str], hoy: date, rango) -> dict:
    out = {"hoy": hoy.isoformat(), "mundos": [MUNDOS[m] for m in mundos]}
    if rango:
        out["periodo"] = _rango_json(rango)
    return out


def _resumen_piezas(piezas) -> dict:
    out: dict[str, int] = {}
    for p in piezas:
        out[p.estado] = out.get(p.estado, 0) + 1
    return {"total": len(piezas), **{e: out[e] for e in ESTADOS_PIEZA if out.get(e)}}


def _vencida(t, hoy: date) -> bool:
    return t.estado != "hecha" and t.vence is not None and t.vence < hoy


def _resumen_tareas(tareas, hoy: date) -> dict:
    return {
        "total": len(tareas),
        "hechas": sum(1 for t in tareas if t.estado == "hecha"),
        "en_proceso": sum(1 for t in tareas if t.estado == "en-proceso"),
        "pendientes": sum(1 for t in tareas if t.estado == "pendiente"),
        "vencidas": sum(1 for t in tareas if _vencida(t, hoy)),
        "sin_asignar": sum(1 for t in tareas if t.estado != "hecha" and t.asignado_a_id is None),
    }


def _sale(p, b) -> date:
    return p.desde or b.desde


async def acciones(usuario, args: dict, fuente, hoy: date) -> str:
    mundos = mundos_a_mirar(usuario, args.get("mundo"))
    texto = (args.get("texto") or "").strip()
    rango = resolver_rango(args, hoy, por_defecto=None if texto else "proximos_30_dias")
    seccion = args.get("seccion")
    secciones = [seccion] if seccion in SECCIONES else list(SECCIONES_POR_DEFECTO)

    barras = [b for b in await fuente.barras(mundos, rango=rango, secciones=secciones) if b.mundo in mundos]
    if texto:
        barras = [b for b in barras if _coincide_accion(texto, b)]
    total = len(barras)
    barras = barras[:MAX_ITEMS]
    ids = {b.id for b in barras}
    piezas: dict[str, list] = {}
    for p in await fuente.piezas_de(list(ids)):
        if p.barra_id in ids:
            piezas.setdefault(p.barra_id, []).append(p)
    tareas: dict[str, list] = {}
    for t in await fuente.tareas_de(list(ids)):
        if t.barra_id in ids:
            tareas.setdefault(t.barra_id, []).append(t)

    lista = []
    for b in barras:
        item = {**ref_accion(b), "seccion": b.seccion, "desde": _iso(b.desde), "hasta": _iso(b.hasta),
                "cuando": cuando(b.desde, b.hasta, hoy, es_envio=b.seccion == "envio")}
        if b.seccion == "envio":
            item.update({"formato": b.formato, "estado": b.estado or "pendiente", "hora": b.hora})
        if piezas.get(b.id):
            item["piezas"] = _resumen_piezas(piezas[b.id])
        if tareas.get(b.id):
            r = _resumen_tareas(tareas[b.id], hoy)
            item["tareas"] = {k: v for k, v in r.items() if v or k == "total"}
        lista.append({k: v for k, v in item.items() if v is not None})
    datos = {**_contexto(mundos, hoy, rango), "total": total, "acciones": lista}
    if texto:
        datos["busqueda"] = texto
    if total > len(lista):
        datos["recortado"] = {"acciones": {"mostrados": len(lista), "total": total}}
    return a_json(datos, ("acciones",))


def _cercania(b, hoy: date, texto: str) -> tuple:
    """Para elegir entre varias acciones con el mismo nombre (el Ciberlunes de
    este año y el del año pasado): primero el nombre exacto, después la que
    está en curso, después la próxima, después la más reciente."""
    exacto = 0 if normalizar(b.nombre) == normalizar(texto) else 1
    if b.desde <= hoy <= b.hasta:
        return exacto, 0, 0
    if hoy < b.desde:
        return exacto, 1, (b.desde - hoy).days
    return exacto, 2, (hoy - b.hasta).days


async def accion(usuario, args: dict, fuente, hoy: date) -> str:
    mundos = mundos_a_mirar(usuario, args.get("mundo"))
    accion_id = (args.get("accion_id") or "").strip()
    texto = (args.get("texto") or "").strip()
    if accion_id:
        encontradas = [b for b in await fuente.barras(mundos, ids=[accion_id]) if b.mundo in mundos]
        if not encontradas:
            raise ConsultaInvalida(
                "No encontré esa acción entre las que esta persona puede ver: puede que la hayan "
                "borrado o que sea de un mundo al que no entra."
            )
        elegida, otras = encontradas[0], []
    elif texto:
        candidatas = [
            b for b in await fuente.barras(mundos, secciones=list(SECCIONES_POR_DEFECTO))
            if b.mundo in mundos and _coincide_accion(texto, b)
        ]
        if not candidatas:
            raise ConsultaInvalida(
                f"No encontré ninguna acción que se llame '{texto}' en "
                f"{', '.join(MUNDOS[m] for m in mundos)}."
            )
        candidatas.sort(key=lambda b: _cercania(b, hoy, texto))
        elegida, otras = candidatas[0], candidatas[1:]
    else:
        raise ConsultaInvalida("Falta decir qué acción: el id (accion_id) o el nombre (texto).")

    piezas = [p for p in await fuente.piezas_de([elegida.id]) if p.barra_id == elegida.id]
    tareas = [t for t in await fuente.tareas_de([elegida.id]) if t.barra_id == elegida.id]
    avisos = [a for a in await fuente.avisos_de([elegida.id]) if a.barra_id == elegida.id]
    personas = personas_por_mundo(await fuente.personas_activas(), [elegida.mundo])
    yo = getattr(usuario, "id", None)
    es_envio = elegida.seccion == "envio"

    datos_accion = {
        **ref_accion(elegida), "seccion": elegida.seccion,
        "desde": _iso(elegida.desde), "hasta": _iso(elegida.hasta),
        "cuando": cuando(elegida.desde, elegida.hasta, hoy, es_envio=es_envio),
    }
    if es_envio:
        datos_accion.update({"formato": elegida.formato, "estado": elegida.estado or "pendiente", "hora": elegida.hora})

    lista_piezas = []
    for p in piezas:
        sale = _sale(p, elegida)
        item = {
            "area": AREAS.get(p.area, p.area), "formato": corto(p.formato, 80), "estado": p.estado,
            "sale": _iso(sale), "hasta": _iso(p.hasta), "hora": p.hora,
            "en_sharepoint": True if p.en_sharepoint else None,
            # Sale hoy o ya salió y todavía no está aprobada: llega tarde.
            "atrasada": True if p.estado in SIN_APROBAR and sale <= hoy else None,
        }
        lista_piezas.append({k: v for k, v in item.items() if v is not None})

    titulos = {t.id: t.titulo for t in tareas}
    padres = {t.id: t.parent_id for t in tareas}

    def nivel(t) -> int:
        n, padre = 1, t.parent_id
        while padre and n <= 3:
            n, padre = n + 1, padres.get(padre)
        return n

    lista_tareas = []
    for t in tareas:
        item = {
            "titulo": corto(t.titulo, 160), "estado": t.estado,
            "responsable": nombre_de(t.asignado_a_id, elegida.mundo, personas, yo),
            "vence": _iso(t.vence), "vencida": True if _vencida(t, hoy) else None,
            "subtarea_de": corto(titulos.get(t.parent_id), 80) if t.parent_id else None,
            "nivel": nivel(t) if t.parent_id else None,
            "detalle": corto(t.descripcion, 240),
        }
        lista_tareas.append({k: v for k, v in item.items() if v is not None})

    lista_avisos = []
    for a in avisos:
        sale = elegida.desde - timedelta(days=a.dias_antes)
        para = []
        for uid in a.destinatarios or []:
            try:
                n = nombre_de(int(uid), elegida.mundo, personas, yo)
            except (TypeError, ValueError):
                continue
            if n not in para:
                para.append(n)
        lista_avisos.append({"dias_antes": a.dias_antes, "sale_el": _iso(sale), "ya_salio": sale <= hoy,
                             "para": para[:15]})

    datos = {
        "hoy": hoy.isoformat(),
        "accion": {k: v for k, v in datos_accion.items() if v is not None},
        "resumen_piezas": _resumen_piezas(piezas) if elegida.seccion == "comercial" else None,
        "resumen_tareas": _resumen_tareas(tareas, hoy) if tareas else None,
    }
    datos = {k: v for k, v in datos.items() if v is not None}
    con_tope(datos, "piezas", lista_piezas)
    con_tope(datos, "tareas", lista_tareas)
    con_tope(datos, "avisos", lista_avisos, 20)
    if otras:
        con_tope(datos, "otras_coincidencias",
                 [{**ref_accion(b), "desde": _iso(b.desde), "hasta": _iso(b.hasta)} for b in otras], 8)
    return a_json(datos, ("tareas", "piezas", "avisos", "otras_coincidencias"))


def _estados(args: dict, clave: str, validos: tuple[str, ...], por_defecto: tuple[str, ...]) -> tuple[str, ...]:
    pedidos = args.get(clave)
    if isinstance(pedidos, str):
        pedidos = [pedidos]
    if not pedidos:
        return por_defecto
    elegidos = tuple(e for e in validos if e in set(pedidos))
    if not elegidos:
        raise ConsultaInvalida(f"Los estados posibles son: {', '.join(validos)}.")
    return elegidos


async def piezas(usuario, args: dict, fuente, hoy: date) -> str:
    """Piezas (y envíos sueltos) por la fecha en que salen."""
    mundos = mundos_a_mirar(usuario, args.get("mundo"))
    rango = resolver_rango(args, hoy, por_defecto="proximos_30_dias")
    estados = _estados(args, "estados", ESTADOS_PIEZA, ESTADOS_PIEZA)
    texto = (args.get("texto") or "").strip()
    atrasadas = bool(args.get("incluir_atrasadas"))
    # Las atrasadas son de antes del período: se busca hasta 90 días antes.
    desde = rango[0] - timedelta(days=90) if atrasadas else rango[0]

    items = []
    for p, b in await fuente.piezas_con_accion(mundos, desde, rango[1]):
        if b.mundo not in mundos or p.estado not in estados:
            continue
        sale = _sale(p, b)
        en_rango = rango[0] <= sale <= rango[1]
        # Atrasada: salía antes del período, sigue sin aprobar y su acción no terminó.
        atrasada = not en_rango and p.estado in SIN_APROBAR and sale < rango[0] and b.hasta >= hoy
        if not (en_rango or (atrasadas and atrasada)):
            continue
        if texto and not (_coincide_accion(texto, b) or coincide(texto, p.formato, AREAS.get(p.area))):
            continue
        items.append((sale, {
            "accion": ref_accion(b), "area": AREAS.get(p.area, p.area), "formato": corto(p.formato, 80),
            "estado": p.estado, "sale": _iso(sale), "hora": p.hora,
            "atrasada": True if (atrasada or (p.estado in SIN_APROBAR and sale <= hoy)) else None,
            "en_sharepoint": True if p.en_sharepoint else None,
        }))
    # Los envíos sueltos también tienen estado y salen un día: en el
    # cronograma de envíos se ven al lado de las piezas.
    for b in await fuente.barras(mundos, rango=(desde, rango[1]), secciones=["envio"]):
        estado = b.estado or "pendiente"
        if b.mundo not in mundos or estado not in estados:
            continue
        en_rango = rango[0] <= b.desde <= rango[1]
        atrasada = not en_rango and estado in SIN_APROBAR and b.desde < rango[0] and b.desde >= hoy - timedelta(days=90)
        if not (en_rango or (atrasadas and atrasada)):
            continue
        if texto and not _coincide_accion(texto, b):
            continue
        items.append((b.desde, {
            "accion": ref_accion(b), "envio_suelto": True, "area": AREAS.get(b.banda, b.banda),
            "formato": corto(b.formato, 80), "estado": estado, "sale": _iso(b.desde), "hora": b.hora,
            "atrasada": True if estado in SIN_APROBAR and b.desde <= hoy else None,
        }))
    items.sort(key=lambda x: (x[0], x[1]["accion"]["nombre"] or ""))
    lista = [{k: v for k, v in i.items() if v is not None} for _, i in items]
    datos = {**_contexto(mundos, hoy, rango), "estados_pedidos": list(estados), "total": len(lista)}
    con_tope(datos, "piezas", lista)
    return a_json(datos, ("piezas",))


def _ids_de_responsable(responsable: str, usuario, personas: dict[str, dict[int, str]]):
    """None = todos; "sin" = sin asignar; si no, el conjunto de ids."""
    r = normalizar(responsable)
    if r in ("", "todos", "todas", "todo el equipo"):
        return None
    if r in ("yo", "mi", "mias", "mis tareas", "vos"):
        return {usuario.id}
    if r in ("sin_asignar", "sin asignar", "nadie"):
        return "sin"
    ids = {uid for nombres in personas.values() for uid, n in nombres.items() if r in normalizar(n)}
    if not ids:
        raise ConsultaInvalida(
            f"No encontré a nadie que se llame '{responsable}' entre quienes ven este calendario."
        )
    return ids


def entra_por_vencimiento(t, rango, hoy: date, incluir_vencidas: bool, incluir_sin_fecha: bool) -> bool:
    """Si una tarea entra en el pedido por su fecha. Pura: es la misma regla
    que la consulta a la base, repetida para no depender de ella."""
    if t.vence is None:
        return incluir_sin_fecha
    if rango is None:
        return True
    if rango[0] <= t.vence <= rango[1]:
        return True
    return incluir_vencidas and _vencida(t, hoy)


async def tareas(usuario, args: dict, fuente, hoy: date) -> str:
    mundos = mundos_a_mirar(usuario, args.get("mundo"))
    estados = _estados(args, "estados", ESTADOS_TAREA, ABIERTAS)
    rango = resolver_rango(args, hoy)
    incluir_vencidas = bool(args.get("incluir_vencidas", True))
    incluir_sin_fecha = bool(args.get("incluir_sin_fecha", rango is None))
    texto = (args.get("texto") or "").strip()
    personas = personas_por_mundo(await fuente.personas_activas(), mundos)
    responsables = _ids_de_responsable(str(args.get("responsable") or "todos"), usuario, personas)

    filas = await fuente.tareas_con_accion(
        mundos, estados=estados, rango=rango, incluir_vencidas=incluir_vencidas,
        incluir_sin_fecha=incluir_sin_fecha, hoy=hoy,
    )
    elegidas = []
    for t, b in filas:
        if b.mundo not in mundos or t.estado not in estados:
            continue
        if not entra_por_vencimiento(t, rango, hoy, incluir_vencidas, incluir_sin_fecha):
            continue
        if responsables == "sin" and t.asignado_a_id is not None:
            continue
        if isinstance(responsables, set):
            # Solo con nombre en ESE mundo: quien no lo ve no aparece por nombre.
            if t.asignado_a_id not in responsables or t.asignado_a_id not in personas.get(b.mundo, {}):
                continue
        if texto and not (_coincide_accion(texto, b) or coincide(texto, t.titulo)):
            continue
        elegidas.append((t, b))

    padres = await fuente.titulos_de_tareas({t.parent_id for t, _ in elegidas[:MAX_ITEMS] if t.parent_id})
    yo = usuario.id
    lista = []
    for t, b in elegidas[:MAX_ITEMS]:
        item = {
            "titulo": corto(t.titulo, 160), "estado": t.estado,
            "responsable": nombre_de(t.asignado_a_id, b.mundo, personas, yo),
            "vence": _iso(t.vence), "vencida": True if _vencida(t, hoy) else None,
            "accion": ref_accion(b),
            "subtarea_de": corto(padres.get(t.parent_id), 80) if t.parent_id else None,
            "detalle": corto(t.descripcion, 160),
        }
        lista.append({k: v for k, v in item.items() if v is not None})
    datos = {
        **_contexto(mundos, hoy, rango),
        "estados_pedidos": list(estados),
        "total": len(elegidas),
        "vencidas": sum(1 for t, _ in elegidas if _vencida(t, hoy)),
        "tareas": lista,
    }
    if len(elegidas) > len(lista):
        datos["recortado"] = {"tareas": {"mostrados": len(lista), "total": len(elegidas)}}
    return a_json(datos, ("tareas",))


async def carga(usuario, args: dict, fuente, hoy: date) -> str:
    """Cuántas tareas abiertas tiene cada persona en un período."""
    mundos = mundos_a_mirar(usuario, args.get("mundo"))
    rango = resolver_rango(args, hoy, por_defecto="esta_semana")
    personas = personas_por_mundo(await fuente.personas_activas(), mundos)
    filas = await fuente.tareas_con_accion(
        mundos, estados=ABIERTAS, rango=None, incluir_vencidas=True, incluir_sin_fecha=True, hoy=hoy,
    )
    por: dict[Any, dict] = {}
    for t, b in filas:
        if b.mundo not in mundos or t.estado not in ABIERTAS:
            continue
        uid = t.asignado_a_id
        if uid is None:
            clave = "sin"
        elif uid in personas.get(b.mundo, {}):
            clave = uid
        else:
            clave = "nadie"
        if clave == "sin":
            persona = SIN_ASIGNAR
        elif clave == "nadie":
            persona = NADIE
        else:
            persona = nombre_de(uid, b.mundo, personas, usuario.id)
        r = por.setdefault(clave, {
            "persona": persona,
            "vencen_en_el_periodo": 0, "vencidas": 0, "sin_fecha": 0, "en_proceso": 0,
            "abiertas": 0, "del_periodo": [],
        })
        r["abiertas"] += 1
        if t.estado == "en-proceso":
            r["en_proceso"] += 1
        if t.vence is None:
            r["sin_fecha"] += 1
        elif rango[0] <= t.vence <= rango[1]:
            r["vencen_en_el_periodo"] += 1
            if len(r["del_periodo"]) < 5:
                r["del_periodo"].append({"titulo": corto(t.titulo, 80), "vence": _iso(t.vence),
                                         "accion": corto(b.nombre, 60), "link": link_de_accion(b.id)})
        if _vencida(t, hoy):
            r["vencidas"] += 1
    lista = sorted(
        por.values(),
        key=lambda r: (-(r["vencen_en_el_periodo"] + r["vencidas"]), -r["abiertas"], r["persona"]),
    )
    for r in lista:
        if not r["del_periodo"]:
            del r["del_periodo"]
    con_carga = {k for k, r in por.items() if r["vencen_en_el_periodo"] or r["vencidas"]}
    sin_nada = sorted({
        n for m in mundos for uid, n in personas.get(m, {}).items() if uid not in con_carga
    })
    datos = {
        **_contexto(mundos, hoy, rango),
        "criterio": "Tareas abiertas (pendientes o en proceso). 'vencen_en_el_periodo' cuenta las que "
                    "vencen en el período; 'vencidas', las que ya vencieron y siguen abiertas.",
    }
    con_tope(datos, "personas", lista, 40)
    con_tope(datos, "sin_tareas_en_el_periodo", sin_nada, 40)
    return a_json(datos, ("personas", "sin_tareas_en_el_periodo"))


async def avisos(usuario, args: dict, fuente, hoy: date) -> str:
    """Los avisos configurados que salen en un período (a la campanita)."""
    mundos = mundos_a_mirar(usuario, args.get("mundo"))
    rango = resolver_rango(args, hoy, por_defecto="proximos_7_dias")
    solo_mios = normalizar(args.get("para") or "todos") in ("yo", "mi", "mios", "vos")
    personas = personas_por_mundo(await fuente.personas_activas(), mundos)
    # Un aviso sale `dias_antes` (1 a 365) antes de que arranque su acción.
    filas = await fuente.avisos_con_accion(mundos, rango[0], rango[1] + timedelta(days=366))
    items = []
    for a, b in filas:
        if b.mundo not in mundos:
            continue
        sale = b.desde - timedelta(days=a.dias_antes)
        if not rango[0] <= sale <= rango[1]:
            continue
        ids = []
        for uid in a.destinatarios or []:
            try:
                ids.append(int(uid))
            except (TypeError, ValueError):
                continue
        if solo_mios and usuario.id not in ids:
            continue
        para = []
        for uid in ids:
            n = nombre_de(uid, b.mundo, personas, usuario.id)
            if n not in para:
                para.append(n)
        items.append((sale, {"accion": ref_accion(b), "arranca": _iso(b.desde), "dias_antes": a.dias_antes,
                             "sale_el": _iso(sale), "ya_salio": sale <= hoy, "para": para[:15]}))
    items.sort(key=lambda x: x[0])
    datos = {**_contexto(mundos, hoy, rango), "total": len(items)}
    con_tope(datos, "avisos", [i for _, i in items])
    return a_json(datos, ("avisos",))


HERRAMIENTAS = {
    "calendario_acciones": acciones,
    "calendario_accion": accion,
    "calendario_piezas": piezas,
    "calendario_tareas": tareas,
    "calendario_carga": carga,
    "calendario_avisos": avisos,
}


async def ejecutar(nombre: str, args: dict, usuario, db, *, hoy: date | None = None, fuente=None) -> str:
    """Corre una herramienta del calendario y devuelve el JSON para el modelo.
    Un pedido inválido vuelve como {"error": ...}: el modelo se lo explica a
    la persona en vez de inventar."""
    funcion = HERRAMIENTAS.get(nombre)
    if funcion is None:
        return _dump({"error": f"Herramienta desconocida: {nombre}"})
    hoy = hoy or hoy_en_uruguay()
    fuente = fuente or FuenteCalendario(db)
    if externos.es_externo(usuario):
        if nombre in _NO_PARA_EXTERNOS:
            return _dump({"error": _NO_PARA_EXTERNOS[nombre]})
        fuente = FuenteDeExterno(fuente, usuario, externos.ventana(hoy))
    try:
        return await funcion(usuario, args or {}, fuente, hoy)
    except ConsultaInvalida as exc:
        return _dump({"error": str(exc)})
