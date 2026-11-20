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
3. **Cuánto del calendario ve.** Desde la 0070 eso no depende de ser
   externo: cada persona tiene su alcance (app/core/alcance.py), y una cuenta
   externa arranca en "No lo ve". Una acción fuera de su alcance no existe
   para ella: el mismo 404 que una que se borró.
4. **Lo de adentro de lo que ve.** Solo sus tareas (las que tiene asignadas,
   y las que son "para la agencia" de su empresa: ver `es_tarea_propia`),
   sin avisos internos, sin plantillas, sin las fotos de colocación; de las
   personas, los de su empresa y los que aprueban sus entregas, con nombre y
   sin mail; y de las entregas, todo lo suyo menos las notas internas de las
   decisiones. Sus tarjetas del tablero las ve siempre, aunque la campaña
   quede fuera de su alcance (16/11/2026: las trabaja con anticipación).

Lo puro (sin base) está acá para probarlo sin levantar nada; los filtros de
cada ruta están en cada ruta, llamando a esto.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import and_, func, or_

from app.core.config import settings

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


# Las letras con tilde (y la ñ) y su versión sin. Es una tabla a mano, y no
# unicodedata, porque la misma cuenta se hace en la base (`empresa_en_sql`,
# con translate) y las dos tienen que dar exactamente lo mismo. Van también
# las mayúsculas: si la base no sabe pasar «Ñ» a minúscula (una base con el
# idioma C), la tabla la pasa igual.
_CON_TILDE = "áàäâãåéèëêíìïîóòöôõúùüûñçýÁÀÄÂÃÅÉÈËÊÍÌÏÎÓÒÖÔÕÚÙÜÛÑÇÝ"
_SIN_TILDE = "aaaaaaeeeeiiiiooooouuuuncy" * 2
_SIN_TILDES = str.maketrans(_CON_TILDE, _SIN_TILDE)


def clave_de_empresa(texto: str | None) -> str | None:
    """Cómo se compara el nombre de una empresa: sin espacios de más, sin
    mayúsculas, sin tildes y con la ñ como n. "Diseñadores", "Disenadores" y
    "  DISEÑADORES " dan lo mismo (19/11/2026: la empresa se escribía a mano
    y una letra de diferencia dejaba a la agencia sin ver sus tarjetas).
    Vacío = sin empresa."""
    limpio = limpiar_empresa(texto)
    return limpio.lower().translate(_SIN_TILDES) if limpio else None


def misma_empresa(a: str | None, b: str | None) -> bool:
    """"Diseñadores", "disenadores" y "Diseñadores  " son la misma (ver
    `clave_de_empresa`). Sin empresa no hay con quién compartirla."""
    a, b = clave_de_empresa(a), clave_de_empresa(b)
    return bool(a) and a == b


def empresa_como_ya_esta(texto: str | None, existentes) -> str | None:
    """El nombre con el que se guarda una empresa: si es una de `existentes`
    (sin mirar tildes, la ñ, mayúsculas ni espacios), como ya está escrita
    ahí; si no, como vino, sin espacios de más. Así «Disenadores» o
    «diseñadores » terminan siendo «Diseñadores» (Ivan, 19/11/2026: "¿no
    debería ser una selección?"). Pura: la lista la arma
    app/services/agencias.py."""
    clave = clave_de_empresa(texto)
    if not clave:
        return None
    for nombre in existentes:
        if clave_de_empresa(nombre) == clave:
            return limpiar_empresa(nombre)
    return limpiar_empresa(texto)


def sin_repetir(nombres) -> list[str]:
    """Los nombres de empresa, cada uno una sola vez (el primero que aparece
    manda cómo se escribe) y sin espacios de más. Pura."""
    vistas: set[str] = set()
    out: list[str] = []
    for nombre in nombres:
        clave = clave_de_empresa(nombre)
        if clave and clave not in vistas:
            vistas.add(clave)
            out.append(limpiar_empresa(nombre))
    return out


def es_tarea_propia(usuario, tarea) -> bool:
    """Si una tarea es de esta cuenta externa: la tiene asignada ella, o es
    "para la agencia" y la agencia es su empresa (16/11/2026: la tarjeta es de
    la agencia, la puede tomar cualquiera de sus cuentas). Pura."""
    if tarea.asignado_a_id is not None and tarea.asignado_a_id == usuario.id:
        return True
    return getattr(tarea, "para", None) == "agencia" and misma_empresa(getattr(tarea, "agencia", None), usuario.empresa)


def empresa_en_sql(columna):
    """La empresa como la compara `misma_empresa`, para un WHERE: lo mismo
    que `clave_de_empresa` (sin espacios de más, en minúscula, sin tildes y
    con la ñ como n), así que se compara contra eso. El panel ya la guarda
    limpia y como ya existía; esto cubre lo que quedó guardado de antes
    (19/11/2026: una cuenta con «Disenadores» tiene que ver las tarjetas de
    «Diseñadores» sin tocar los datos)."""
    juntos = func.btrim(func.regexp_replace(columna, r"\s+", " ", "g"))
    return func.translate(func.lower(juntos), _CON_TILDE, _SIN_TILDE)


def condicion_tarea_propia(modelo, usuario):
    """La misma regla que `es_tarea_propia`, para el WHERE de una consulta
    sobre las tareas. La empresa se compara como en `misma_empresa`: sin
    tildes, mayúsculas ni espacios de más (una tarjeta guardada para
    «Disenadores» es de «Diseñadores»)."""
    clave = clave_de_empresa(getattr(usuario, "empresa", None))
    asignada = modelo.asignado_a_id == usuario.id
    if not clave:
        return asignada
    return or_(
        asignada,
        and_(modelo.para == "agencia", empresa_en_sql(modelo.agencia) == clave),
    )


# ---------------------------------------------------------------------------
# La revisión de lo que ve
# ---------------------------------------------------------------------------
# El calendario y el tablero preguntan cada 15 s "¿cambió algo desde la
# revisión N?". El número de revisión es uno para todos: si se le diera a
# quien ve una parte (un externo, o cualquiera con el alcance limitado: ver
# app/core/alcance.py), vería subir el contador con cada cambio que hace
# cualquiera, en cualquier mundo y en cualquier fecha, y podría deducir que
# pasó algo fuera de lo que ve. Por eso a esa persona se le da otro número: la
# huella de lo que ve. Si lo que ve no cambió, la huella es la misma y la respuesta es "sin
# cambios", aunque el resto del calendario se haya movido entero.

def huella(datos) -> int:
    """Un número que cambia si y solo si cambia lo que se le manda (en la
    práctica). Entra en un número de JavaScript sin perder precisión (52 bits)."""
    texto = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return int(hashlib.sha256(texto.encode("utf-8")).hexdigest()[:13], 16)
