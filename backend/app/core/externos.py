"""Las cuentas externas: la agencia (o un diseñador de afuera) adentro de Core
Tienda, con la vista limitada.

Pedido de Ivan (15/11/2026): "que la agencia en un futuro tenga acceso a la
plataforma… limitar también las vistas… que solamente puedan ver el
calendario actual, no lo que viene dentro de 2 o 3 meses, porque el
calendario sería algo público".

Una cuenta externa es un usuario más, marcado con `users.es_externo` y el
nombre de su empresa (`users.empresa`). Entra igual que todos: hoy con mail y
contraseña, y el día que se entre con Microsoft (Azure) va a ser lo mismo, con
el flag. Lo que cambia, todo del lado del servidor:

1. **Permisos.** Como mucho los de PERMISOS_DE_EXTERNOS (ver el calendario).
   Nadie se los puede ampliar: el panel de usuarios lo rechaza, la base tiene
   una regla que lo impide (migración 0069) y `require_permission` igual se
   lo niega si algún día apareciera uno de más.
2. **Qué rutas existen para él.** Solo las de RUTAS_DE_EXTERNOS: su sesión, el
   calendario (filtrado) y sus avisos. Lo demás (cenefas, precios, medios,
   finanzas, Redexpres, el panel...) contesta 403 aunque el permiso alcanzara:
   no alcanza con esconder los botones.
3. **La ventana.** Del calendario ve solo las acciones cuyo rango toca
   [hoy - EXTERNOS_DIAS_ANTES, fin del mes actual + EXTERNOS_DIAS_DESPUES],
   en hora de Uruguay. Una acción fuera de la ventana para él no existe: da el
   mismo 404 que una que se borró, así no se puede ni deducir que está.
4. **Lo de adentro de la ventana.** Solo sus tareas (las que tiene
   asignadas, que son las que entrega), sin avisos internos, sin plantillas,
   sin las fotos de colocación; de las personas, los de su empresa y los que
   aprueban sus entregas, con nombre y sin mail; y de las entregas, todo lo
   suyo menos las notas internas de las decisiones.

Lo puro (sin base) está acá para probarlo sin levantar nada; los filtros de
cada ruta están en cada ruta, llamando a esto.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

URUGUAY = ZoneInfo("America/Montevideo")

# Lo único que puede tener una cuenta externa. Si se agrega algo, va también
# en la regla de la base (`ck_users_externo_solo_calendario`, migración 0069).
# Don Tino queda afuera a propósito: su conocimiento es el de la plataforma
# interna y cada pregunta cuesta; sus herramientas del calendario igual
# respetan la ventana (ver calendario_consultas.py), por si se habilita.
PERMISOS_DE_EXTERNOS = frozenset({"calendario.view"})

# Las rutas de la API (sin el /api/v1) a las que llega una cuenta externa. Su
# sesión, el calendario (que se filtra adentro de cada ruta) y la campanita.
RUTAS_DE_EXTERNOS = ("/auth/", "/calendario/", "/notificaciones")

# Cómo se nombra a alguien del equipo cuyo nombre un externo no ve.
ALGUIEN_DEL_EQUIPO = "Alguien del equipo"

SIN_ACCESO = "Una cuenta externa no tiene acceso a esto"


def es_externo(usuario) -> bool:
    return bool(getattr(usuario, "es_externo", False))


def permisos_no_permitidos(permisos) -> list[str]:
    """Los permisos de la lista que una cuenta externa no puede tener."""
    return [p for p in (permisos or []) if p not in PERMISOS_DE_EXTERNOS]


def puede_tener(usuario, permiso: str) -> bool:
    """Si el usuario tiene el permiso, con el freno de las cuentas externas:
    a un externo no le sirve un permiso que no le corresponde aunque esté en
    su lista, ni el de superadmin."""
    if es_externo(usuario):
        return permiso in PERMISOS_DE_EXTERNOS and permiso in (getattr(usuario, "permissions", None) or [])
    if getattr(usuario, "is_superuser", False):
        return True
    return permiso in (getattr(usuario, "permissions", None) or [])


def ruta_permitida(path: str, prefijo_api: str | None = None) -> bool:
    """Si una cuenta externa puede llegar a esa ruta de la API."""
    prefijo = settings.API_V1_PREFIX if prefijo_api is None else prefijo_api
    if prefijo and path.startswith(prefijo):
        path = path[len(prefijo):]
    return any(path == r.rstrip("/") or path.startswith(r) for r in RUTAS_DE_EXTERNOS)


def limpiar_empresa(texto: str | None) -> str | None:
    """El nombre de la empresa sin espacios de más. Vacío = sin empresa."""
    limpio = " ".join((texto or "").split())
    return limpio[:120] or None


def misma_empresa(a: str | None, b: str | None) -> bool:
    """"Agencia Pampa" y "agencia  pampa" son la misma. Sin empresa no hay
    con quién compartirla."""
    a, b = limpiar_empresa(a), limpiar_empresa(b)
    return bool(a) and bool(b) and a.casefold() == b.casefold()


# ---------------------------------------------------------------------------
# La ventana
# ---------------------------------------------------------------------------

def hoy_en_uruguay(ahora: datetime | None = None) -> date:
    """El día de hoy en Montevideo. A las 22 de un 31 en Uruguay ya es 1 en
    Greenwich: la ventana no puede cambiar de mes por eso."""
    return (ahora or datetime.now(URUGUAY)).astimezone(URUGUAY).date()


def fin_de_mes(d: date) -> date:
    primero_del_siguiente = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return primero_del_siguiente - timedelta(days=1)


def ventana(hoy: date, dias_antes: int | None = None, dias_despues: int | None = None) -> tuple[date, date]:
    """[hoy - días antes, fin del mes de hoy + días después]. Pura."""
    antes = settings.EXTERNOS_DIAS_ANTES if dias_antes is None else dias_antes
    despues = settings.EXTERNOS_DIAS_DESPUES if dias_despues is None else dias_despues
    return hoy - timedelta(days=max(0, antes)), fin_de_mes(hoy) + timedelta(days=max(0, despues))


def ventana_de_hoy(ahora: datetime | None = None) -> tuple[date, date]:
    return ventana(hoy_en_uruguay(ahora))


def toca(desde: date, hasta: date, v: tuple[date, date]) -> bool:
    """Si una acción que va de `desde` a `hasta` toca la ventana (aunque sea
    un día). Una con las fechas al revés se toma como de un solo día."""
    if hasta < desde:
        hasta = desde
    return desde <= v[1] and hasta >= v[0]


def condicion_de_ventana(modelo, v: tuple[date, date]):
    """La misma regla que `toca`, para el WHERE de una consulta sobre una
    tabla con `desde` y `hasta` (las barras del calendario)."""
    return (modelo.desde <= v[1]) & (modelo.hasta >= v[0])


def meses_de_la_ventana(v: tuple[date, date]) -> list[str]:
    """Las claves 'YYYY-MM' de los meses que toca la ventana."""
    claves = []
    y, m = v[0].year, v[0].month
    while (y, m) <= (v[1].year, v[1].month):
        claves.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return claves


# ---------------------------------------------------------------------------
# La revisión de lo que ve
# ---------------------------------------------------------------------------
# El calendario y el tablero preguntan cada 15 s "¿cambió algo desde la
# revisión N?". El número de revisión es uno para todos: si se le diera a un
# externo, vería subir el contador con cada cambio que hace cualquiera, en
# cualquier mundo y en cualquier fecha, y podría deducir que pasó algo fuera de
# su ventana. Por eso a un externo se le da otro número: la huella de lo que él
# ve. Si lo que ve no cambió, la huella es la misma y la respuesta es "sin
# cambios", aunque el resto del calendario se haya movido entero.

def huella(datos) -> int:
    """Un número que cambia si y solo si cambia lo que se le manda (en la
    práctica). Entra en un número de JavaScript sin perder precisión (52 bits)."""
    texto = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return int(hashlib.sha256(texto.encode("utf-8")).hexdigest()[:13], 16)
