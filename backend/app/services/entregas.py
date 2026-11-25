"""Entregas por fases: la lógica, separada de las rutas.

Pedido de Ivan (15/11/2026): una tarea "tiene fase 1, fase 2, fase 3…; se
entrega, se aprueba o vuelve con correcciones, la agencia devuelve con las
correcciones aplicadas, puede volver otra vez, hasta que se aprueba". Más lo
que aprobó encima: marcar la corrección sobre la pieza, el pedido según el
tipo de pieza, la aprobación en cadena y medir el retrabajo. Las tablas están
en app/models/entregas.py; las rutas, en app/api/routes/entregas.py.

Hubo un "aprobado con cambios" (aprobar y dejar anotados ajustes chicos sin
otra ronda) y se sacó el 19/11/2026 (Ivan: "me resulta raro ese botón. No
creo que sume nada"). Quedan dos decisiones: aprobar o pedir cambios. Las
decisiones viejas guardadas así se siguen leyendo como aprobadas (ver
APRUEBAN).

Lo de arriba de este archivo es puro (sin base) a propósito: las reglas del
flujo —a quién le toca, cuándo una versión queda aprobada, qué pasa con la
tarea— se prueban en tests/test_entregas_por_fases.py sin levantar nada.

El flujo, en corto:

1. Quien lidera marca que la tarea lleva entregas: tipo de pieza, brief,
   fases y la cadena de aprobadores. La primera fase queda en curso.
2. El responsable de la tarea entrega: una versión (ronda 1) con imágenes.
3. La revisa el primer aprobador de la cadena. Si aprueba, pasa al
   siguiente; cuando aprueba el último, la versión queda
   aprobada, la fase también y arranca la siguiente. Si cualquiera pide
   cambios, la versión vuelve: el responsable entrega la ronda 2, tildando
   qué marcas corrigió, y la cadena arranca de nuevo desde el primero (lo
   que cambió lo tienen que ver todos).
4. Aprobada la última fase, la tarea queda hecha sola.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, NamedTuple

from sqlalchemy import and_, func, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.calendario import CalendarioBarra, CalendarioTarea
from app.models.entregas import (
    CalendarioDecision, CalendarioEntrega, CalendarioFase, CalendarioVersion, CalendarioVersionImagen,
)
from app.models.notificacion import Notificacion

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# El catálogo
# ---------------------------------------------------------------------------

TIPOS_DE_PIEZA: dict[str, str] = {
    "cenefa": "Cenefa",
    "mailing": "Email marketing (EMM)",
    "banner": "Banner web",
    "redes": "Redes",
    "otro": "Otro",
}

# El formulario del pedido a la agencia, según el tipo de pieza: campo -> qué
# es. Una tupla es una lista cerrada de opciones. "detalle" es el texto libre,
# que está en todos (y que se va a poder dictar por voz). Es el mismo que arma
# el formulario del front (frontend/lib/calendario/entregas.ts): si cambia,
# cambia en los dos.
CAMPOS_DEL_BRIEF: dict[str, dict[str, object]] = {
    "cenefa": {
        "medidas": "texto", "cantidad": "numero", "precio": "texto",
        "vigenciaDesde": "fecha", "vigenciaHasta": "fecha", "legales": "largo", "detalle": "largo",
    },
    "mailing": {
        "asunto": "texto", "segmento": "texto", "fechaEnvio": "fecha", "llamado": "texto", "detalle": "largo",
    },
    "banner": {"medidas": "texto", "link": "url", "desde": "fecha", "hasta": "fecha", "detalle": "largo"},
    "redes": {"formato": ("Post", "Story", "Reel", "Carrusel"), "copy": "largo", "fecha": "fecha", "detalle": "largo"},
    "otro": {"detalle": "largo"},
}

# Las fases con las que arranca cada tipo. Se pueden cambiar al crear la tarea.
FASES_POR_DEFECTO: dict[str, list[str]] = {
    "cenefa": ["Boceto", "Arte final"],
    "mailing": ["Boceto", "Arte final"],
    "banner": ["Boceto", "Arte final", "Adaptaciones"],
    "redes": ["Boceto", "Arte final", "Adaptaciones"],
    "otro": ["Boceto", "Arte final"],
}

# No es un tope de trabajo: devolver una entrega aprobada abre otra fase, sin
# límite (Ivan, 17/11/2026: "la idea sería que eso sea infinito"). Es solo el
# freno de un pedido mal armado al configurar las fases a mano.
MAX_FASES = 100
MAX_APROBADORES = 6
MAX_IMAGENES = 4
# La grande llega comprimida del navegador (1600 px, JPEG 0,75: 50-250 KB).
# Una de 2 MB ya es algo que no pasó por el navegador. La miniatura (320 px)
# pesa 6-20 KB.
MAX_BYTES_IMAGEN = 2 * 1024 * 1024
MAX_BYTES_MINIATURA = 256 * 1024
# Cómo achica el navegador las imágenes de la ronda (frontend/lib/calendario/
# entregas.ts: LADO_MAYOR, LADO_MINIATURA y CALIDAD, que es 0,75). Desde el
# 19/11/2026 el servidor achica igual lo que saca de un ZIP para la ronda (las
# páginas de un PDF, ver app/services/materiales.py): si cambia allá, cambia acá.
LADO_MAYOR = 1600
LADO_MINIATURA = 320
CALIDAD_JPEG = 75
MAX_MARCAS = 40
# Las imágenes de las entregas NO se borran nunca (Ivan, 19/11/2026): son el
# histórico de piezas, el mismo que hoy vive en carpetas por año en SharePoint
# (2023, 2024…), y más adelante van a ir a parar ahí. Mientras estén en la
# base, el único freno es el general de espacio (app/services/espacio.py,
# BASE_TOPE_MB): si se llena, se deja de guardar y se avisa, pero no se
# borra nada. Hasta el 19/11 había una purga (a los 30 días de terminada la
# acción, 120 la versión final): se sacó. La columna `purgada_at` queda por
# las imágenes que esa purga alcanzó a vaciar antes.

ORIGEN = "calendario_entrega"
# Lo que se puede decidir sobre una versión. «Aprobado con cambios» se sacó
# el 19/11/2026 (Ivan: "Sacá la funcionalidad 'aprobado con cambios'").
#
# 'avanzar' es del 25/11/2026 (Ivan: "lo que me pasaron está ok, pero no
# significa que haya terminado la tarea... yo acá le mando que la pieza está
# ok, que pueden avanzar con el resto de los pedidos"): la agencia manda
# primero una pieza para ver si va bien encaminada y después el resto. Es un
# OK a esa ronda que NO aprueba la fase: la ronda vuelve a la agencia, que
# entrega lo que falta en la siguiente, y la fase y la tarea siguen abiertas.
# La versión queda en estado 'avanzar' («OK para avanzar»).
DECISIONES = ("aprobada", "cambios", "avanzar")
AVANZAR = "avanzar"
# La decisión vieja: no se acepta más, pero en la base hay decisiones de esta
# semana guardadas así y se tienen que seguir leyendo como aprobadas (la
# cadena, el retrabajo y la pantalla no se pueden romper por ellas).
DECISION_VIEJA = "aprobada-con-cambios"
APRUEBAN = ("aprobada", DECISION_VIEJA)
MOMENTOS = ("produccion", "revision", "cambios", "aprobada")

_LARGO_TEXTO = 300
_LARGO_LARGO = 5000
_ANIO_MINIMO, _ANIO_MAXIMO = 2000, 2100


def nuevo_id(prefijo: str) -> str:
    return f"{prefijo}-{secrets.token_hex(8)}"


# ---------------------------------------------------------------------------
# Validaciones (puras)
# ---------------------------------------------------------------------------

def link_valido(v: str | None) -> str | None:
    """El link al original: solo web. Un "javascript:..." en una tarea que ve
    todo el equipo se ejecutaría al tocarlo (lo mismo que se cerró en las
    listas de precios en la auditoría del 15/11/2026)."""
    v = (v or "").strip()
    if not v:
        return None
    if not v.lower().startswith(("http://", "https://")):
        raise ValueError("El link tiene que empezar con http:// o https://")
    if len(v) > 1000:
        raise ValueError("El link es demasiado largo")
    if any(ord(c) < 32 for c in v):
        raise ValueError("El link tiene caracteres que no van")
    return v


# Las piezas del pedido que no venían en una ronda (0087, 21/11/2026): las
# calcula la pantalla por las medidas (frontend/lib/calendario/piezas.ts) y
# viajan con la entrega, con lo que escribió quien entrega en «¿Por qué no va
# todo?». Un pedido de banners tiene hasta 40 piezas (20 opciones, web y
# mobile): 40 nombres alcanzan.
MAX_FALTAN = 40
LARGO_PIEZA = 120
LARGO_POR_QUE = 500


def faltan_validas(texto: str | None) -> list[str] | None:
    """La lista de piezas que faltan, como llega en el formulario (JSON): los
    nombres limpios, sin repetidos, en su orden. None si no falta nada.
    ValueError con el mensaje para la persona. Pura."""
    try:
        lista = json.loads(texto or "[]")
    except ValueError:
        lista = None
    if not isinstance(lista, list) or not all(isinstance(x, str) for x in lista):
        raise ValueError("La lista de piezas que faltan no tiene la forma esperada")
    if len(lista) > MAX_FALTAN:
        raise ValueError(f"Son demasiadas piezas que faltan (hasta {MAX_FALTAN})")
    limpias: list[str] = []
    for nombre in lista:
        nombre = " ".join(nombre.split())
        if len(nombre) > LARGO_PIEZA:
            raise ValueError(f"«{nombre[:30]}…» es demasiado largo para el nombre de una pieza")
        if nombre and nombre not in limpias:
            limpias.append(nombre)
    return limpias or None


def por_que_faltan_valido(texto: str | None, faltan: list[str] | None) -> str | None:
    """Lo que escribió quien entrega en «¿Por qué no va todo?», en una línea
    (se lee arriba al revisar, en una línea discreta). Solo si falta algo:
    sin piezas que falten, no hay por qué. ValueError si se pasa. Pura."""
    limpio = " ".join((texto or "").split())
    if len(limpio) > LARGO_POR_QUE:
        raise ValueError(f"«¿Por qué no va todo?» es demasiado largo (hasta {LARGO_POR_QUE} letras)")
    if not faltan:
        return None
    return limpio or None


def _fecha(v: object, nombre: str) -> str:
    try:
        d = date.fromisoformat(str(v))
    except ValueError:
        raise ValueError(f"La fecha de «{nombre}» no es válida")
    if not (_ANIO_MINIMO <= d.year <= _ANIO_MAXIMO):
        raise ValueError(f"La fecha de «{nombre}» no parece real: revisá el año")
    return d.isoformat()


def limpiar_brief(tipo: str, brief: object) -> dict:
    """El pedido a la agencia, con solo los campos de su tipo y cada uno con
    la forma que tiene que tener. Lo vacío no se guarda. Un campo de OTRO tipo
    (quedó de cuando se eligió otro tipo en el formulario) se ignora."""
    if tipo not in CAMPOS_DEL_BRIEF:
        raise ValueError("Ese tipo de pieza no existe")
    if brief is None:
        return {}
    if not isinstance(brief, dict):
        raise ValueError("El pedido a la agencia no tiene la forma esperada")
    campos = CAMPOS_DEL_BRIEF[tipo]
    limpio: dict = {}
    for clave, valor in brief.items():
        if clave not in campos or valor is None:
            continue
        if isinstance(valor, str):
            valor = valor.strip()
            if not valor:
                continue
        clase = campos[clave]
        if isinstance(clase, tuple):
            if valor not in clase:
                raise ValueError(f"«{valor}» no es una opción de {clave}")
        elif clase == "numero":
            try:
                valor = int(valor)
            except (TypeError, ValueError):
                raise ValueError(f"«{clave}» tiene que ser un número")
            if not (0 <= valor <= 1_000_000):
                raise ValueError(f"«{clave}» está fuera de rango")
        elif clase == "fecha":
            valor = _fecha(valor, clave)
        elif clase == "url":
            valor = link_valido(str(valor))
        else:
            valor = str(valor)
            tope = _LARGO_TEXTO if clase == "texto" else _LARGO_LARGO
            if len(valor) > tope:
                raise ValueError(f"«{clave}» es demasiado largo (máximo {tope} caracteres)")
        limpio[clave] = valor
    for desde, hasta in (("vigenciaDesde", "vigenciaHasta"), ("desde", "hasta")):
        if desde in limpio and hasta in limpio and limpio[hasta] < limpio[desde]:
            raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
    return limpio


def nombres_de_fases(nombres: Iterable[str]) -> list[str]:
    limpios = [(n or "").strip() for n in nombres]
    if not limpios:
        raise ValueError("Tiene que haber al menos una fase")
    if len(limpios) > MAX_FASES:
        raise ValueError(f"Son demasiadas fases (máximo {MAX_FASES})")
    for n in limpios:
        if not n:
            raise ValueError("Cada fase necesita un nombre")
        if len(n) > 80:
            raise ValueError("El nombre de una fase es demasiado largo")
    return limpios


def aprobadores_validos(ids: Iterable[int]) -> list[int]:
    lista = list(ids)
    if not lista:
        raise ValueError("Elegí al menos una persona que apruebe")
    if len(lista) > MAX_APROBADORES:
        raise ValueError(f"Son demasiados aprobadores (máximo {MAX_APROBADORES})")
    if len(set(lista)) != len(lista):
        raise ValueError("Una persona no puede estar dos veces en la cadena de aprobación")
    return lista


@dataclass
class FaseExistente:
    id: str
    estado: str
    tiene_versiones: bool

    @property
    def trabajada(self) -> bool:
        return self.estado == "aprobada" or self.tiene_versiones


def plan_de_fases(existentes: list[FaseExistente], pedidas: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    """Valida un cambio de fases y devuelve la lista final (id o None si es
    nueva, nombre), en orden.

    Lo que ya se trabajó (aprobada, o con alguna versión entregada) no se
    puede sacar ni cambiar de orden, y va antes que lo nuevo: si no, la
    historia de rondas quedaría colgando de una fase que no existe, o la
    agencia tendría que entregar una fase "anterior" a una ya aprobada. Lo que
    no se tocó todavía se renombra, se mueve o se saca libremente."""
    nombres = nombres_de_fases(n for _, n in pedidas)
    por_id = {f.id: f for f in existentes}
    ids = [i for i, _ in pedidas if i is not None]
    if len(set(ids)) != len(ids):
        raise ValueError("Una fase está dos veces")
    for i in ids:
        if i not in por_id:
            raise ValueError("Una de las fases ya no existe: recargá la tarea")
    trabajadas = [f.id for f in existentes if f.trabajada]
    for i in trabajadas:
        if i not in ids:
            raise ValueError("No se puede sacar una fase que ya tiene versiones entregadas")
    if [i for i, _ in pedidas[:len(trabajadas)]] != trabajadas:
        raise ValueError("Las fases que ya tienen versiones van primero y en el mismo orden")
    return [(i, n) for (i, _), n in zip(pedidas, nombres)]


def tipo_de_imagen(datos: bytes) -> str | None:
    """El tipo real, por los primeros bytes: el nombre del archivo y lo que
    dice el navegador se pueden falsear."""
    if datos[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(datos) >= 12 and datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def _peso(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f}".replace(".", ",").replace(",0", "") + " MB"
    return f"{max(1, round(n / 1024))} KB"


def validar_imagen(datos: bytes, *, maximo: int = MAX_BYTES_IMAGEN, que: str = "La imagen") -> str:
    """El tipo de la imagen, o ValueError con el mensaje para la persona."""
    if not datos:
        raise ValueError(f"{que} llegó vacía")
    if len(datos) > maximo:
        raise ValueError(f"{que} pesa {_peso(len(datos))}: el máximo es {_peso(maximo)}")
    tipo = tipo_de_imagen(datos)
    if tipo is None:
        raise ValueError(f"{que} no es una imagen JPG, PNG ni WebP")
    return tipo


def validar_decision(decision: str) -> str:
    """La decisión sobre una versión: 'aprobada', 'cambios' o 'avanzar'; si no, ValueError
    con el mensaje para la persona. Una pantalla vieja (o una pestaña abierta
    desde antes) que todavía mande «aprobado con cambios» recibe el porqué y
    qué elegir en su lugar, no un 422 mudo (19/11/2026)."""
    d = (decision or "").strip()
    if d == DECISION_VIEJA:
        raise ValueError(
            "«Aprobado con cambios» ya no existe: si hay algo para corregir, elegí «Pedir cambios»; "
            "si está bien así, «Aprobar». Recargá la página."
        )
    if d not in DECISIONES:
        raise ValueError("Esa decisión no existe: elegí «Avanzar», «Aprobar y terminar» o «Pedir cambios»")
    return d


# ---------------------------------------------------------------------------
# La cadena de aprobación (pura)
# ---------------------------------------------------------------------------

Decisiones = list[tuple[int | None, str]]


def _aprobaron(decisiones: Decisiones) -> set[int | None]:
    return {a for a, d in decisiones if d in APRUEBAN}


def resultado_de_version(aprobadores: list[int], decisiones: Decisiones) -> str:
    """'cambios' si alguien los pidió; 'avanzar' si alguien le dio el OK para
    avanzar (25/11/2026: la ronda vuelve a la agencia y la cadena no sigue,
    porque no hay nada que aprobar todavía); 'aprobada' si aprobaron todos los
    de la cadena; si no, sigue en 'revision'.

    Sin cadena (le sacaron todos los aprobadores a mitad de camino) decide el
    respaldo, y con una aprobación alcanza: si no, la versión quedaría
    trabada para siempre."""
    if any(d == "cambios" for _, d in decisiones):
        return "cambios"
    if any(d == AVANZAR for _, d in decisiones):
        return AVANZAR
    ya = _aprobaron(decisiones)
    if aprobadores:
        return "aprobada" if all(a in ya for a in aprobadores) else "revision"
    return "aprobada" if ya else "revision"


def a_quien_le_toca(aprobadores: list[int], decisiones: Decisiones) -> int | None:
    """El primero de la cadena que todavía no aprobó esta versión. None si ya
    se decidió (o si no hay cadena: entonces decide el respaldo)."""
    if resultado_de_version(aprobadores, decisiones) != "revision":
        return None
    ya = _aprobaron(decisiones)
    return next((a for a in aprobadores if a not in ya), None)


class NoPuedeDecidir(Exception):
    """El mensaje es para la persona. `codigo`: 409 si la versión ya se
    decidió (otro llegó primero), 403 si no le toca."""

    def __init__(self, mensaje: str, codigo: int = 403):
        super().__init__(mensaje)
        self.codigo = codigo


def lugar_para_decidir(
    usuario_id: int, es_gestor: bool, aprobadores: list[int], decisiones: Decisiones,
    subida_por_id: int | None,
) -> tuple[int | None, int, bool]:
    """En nombre de quién decide `usuario_id` sobre una versión en revisión:
    (aprobador de turno, su lugar en la cadena, si decide como respaldo).

    Decide el aprobador al que le toca. Quien tiene `calendario.tareas` puede
    decidir por él (está de licencia, se trabó la cadena) y queda anotado que
    fue como respaldo. Nadie decide sobre una versión que subió."""
    if resultado_de_version(aprobadores, decisiones) != "revision":
        raise NoPuedeDecidir("Esta versión ya se decidió: recargá para ver cómo quedó", 409)
    if subida_por_id is not None and usuario_id == subida_por_id:
        raise NoPuedeDecidir("No podés aprobar ni pedir cambios sobre una versión que subiste vos")
    turno = a_quien_le_toca(aprobadores, decisiones)
    orden = aprobadores.index(turno) if turno in aprobadores else len(aprobadores)
    if turno is not None and turno == usuario_id:
        return turno, orden, False
    if es_gestor:
        return turno, orden, True
    if usuario_id in aprobadores:
        raise NoPuedeDecidir("Todavía no te toca: primero la tiene que aprobar quien está antes en la cadena")
    raise NoPuedeDecidir("No estás en la cadena de aprobación de esta tarea")


# ---------------------------------------------------------------------------
# Fases, momento y tarea (puras)
# ---------------------------------------------------------------------------

def estados_de_fases(estados: list[str]) -> list[str]:
    """Las aprobadas quedan aprobadas; la primera que no lo está queda en
    curso, y las demás, pendientes. Se trabaja una fase por vez."""
    out: list[str] = []
    hay_actual = False
    for e in estados:
        if e == "aprobada":
            out.append("aprobada")
        elif not hay_actual:
            out.append("en-curso")
            hay_actual = True
        else:
            out.append("pendiente")
    return out


def momento_de(hay_fase_actual: bool, estado_ultima_version: str | None) -> str:
    """En qué está la tarea: 'produccion' (le toca a la agencia), 'revision'
    (le toca a un aprobador), 'cambios' (volvió: le toca a la agencia) o
    'aprobada' (todas las fases). Son las columnas del tablero.

    Una ronda con el OK para avanzar (25/11/2026) deja la tarea en
    'produccion': le toca a la agencia entregar lo que falta. Se distingue de
    la primera entrega porque la fase ya tiene rondas (ver `con_ok`)."""
    if not hay_fase_actual:
        return "aprobada"
    if estado_ultima_version == "revision":
        return "revision"
    if estado_ultima_version == "cambios":
        return "cambios"
    return "produccion"


def con_ok(momento: str, ronda: int) -> bool:
    """Si a la agencia le dieron el OK para avanzar con lo que falta: le toca
    entregar y la fase en curso ya tiene rondas. Solo pasa después de un
    'avanzar': con cambios el momento es 'cambios', y una fase nueva arranca
    sin rondas. Pura."""
    return momento == "produccion" and (ronda or 0) > 0


def nombre_de_fase_nueva(nombres: list[str]) -> str:
    """El nombre de la fase que abre una devolución: "Entrega N", donde N es
    la cantidad de fases que va a haber. La que nace con la pieza se llama
    "Entrega", así que la primera devolución abre "Entrega 2". Si ese nombre
    ya está (alguien la nombró así a mano), sigue contando. Pura."""
    usados = {(n or "").strip().casefold() for n in nombres}
    n = len(nombres) + 1
    while f"entrega {n}" in usados:
        n += 1
    return f"Entrega {n}"


def puede_devolver(usuario_id: int, es_gestor: bool, aprobadores: list[int], momento: str) -> bool:
    """Quién devuelve una pieza ya aprobada: quien está en la cadena de
    aprobación, o quien lidera (`calendario.tareas`). Solo cuando todas sus
    fases están aprobadas: antes, los cambios se piden al revisar la entrega.
    Pura (el freno de las cuentas externas va en la ruta)."""
    return momento == "aprobada" and (es_gestor or usuario_id in (aprobadores or []))


def estado_de_tarea(momento: str, hay_versiones: bool, actual: str) -> str:
    """La tarea cambia sola: hecha cuando se aprueba la última fase; en
    proceso mientras hay rondas. Antes de la primera entrega queda como
    estaba (pendiente, o en proceso si alguien ya la había movido)."""
    if momento == "aprobada":
        return "hecha"
    if hay_versiones:
        return "en-proceso"
    return actual if actual in ("pendiente", "en-proceso") else "pendiente"


# ---------------------------------------------------------------------------
# El tablero de tarjetas (puro)
# ---------------------------------------------------------------------------
# Pedido de Ivan (16/11/2026): "una vista estilo Trello, que es a lo que están
# acostumbrados: Ingresado, En proceso, Esperando feedback, Finalizado,
# Archivado. Podemos ir arrastrando las tarjetas de un lado a otro".
#
# La columna NO se guarda: sale del momento de la entrega (que ya se
# recalcula con cada cambio) y de las fechas que el momento no dice:
#
#   Ingresado          produccion, y nadie la arrancó ni entregó nada
#   En proceso         produccion arrancada, o cambios ("Volvió con cambios")
#   Esperando feedback revision: hay una versión esperando al equipo
#   Finalizado         aprobada
#   Archivado          archivada a mano (con cualquier momento: también una
#                      pieza que se canceló sin terminar), o aprobada y
#                      finalizada hace ARCHIVAR_TARJETAS_DIAS o más (la
#                      archiva sola)
#
# Así no hay dos verdades que se puedan separar: si alguien aprueba desde el
# detalle (sin arrastrar), la tarjeta ya está en Finalizado.
#
# Una pieza cancelada (revisión del 16/11/2026): antes solo se archivaba una
# finalizada, y una que se dejaba de hacer quedaba para siempre en Ingresado o
# En proceso, en rojo por vencida, para la agencia y para el equipo. Ahora el
# equipo la archiva desde Ingresado o En proceso, y cerrar la tarea a mano
# («hecha», desde la ficha) también la archiva. Archivada sin terminar es
# "cancelada": la tarea queda cerrada y nadie entrega ni decide hasta que el
# equipo la saque del archivo (vuelve a su columna y la tarea se reabre).

COLUMNAS = ("ingresado", "en-proceso", "esperando", "finalizado", "archivado")
# Las que se guardan en `columna_manual` (0075). Finalizado a mano es darla por
# aprobada y Archivado tiene su fecha: ninguna de las dos va ahí.
COLUMNAS_A_MANO = ("ingresado", "en-proceso", "esperando")
NOMBRES_DE_COLUMNA = {
    "ingresado": "Ingresado",
    "en-proceso": "En proceso",
    "esperando": "Esperando feedback",
    "finalizado": "Finalizado",
    "archivado": "Archivado",
}


def _dia_en_uruguay(momento: datetime) -> date:
    from app.core.alcance import URUGUAY
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(URUGUAY).date()


def se_archiva_sola(
    finalizada_at: datetime | None, desarchivada_at: datetime | None, hoy: date, dias: int,
) -> bool:
    """Si una tarjeta finalizada ya cumplió sus días en Finalizado. Se cuenta
    desde que se finalizó o, si alguien la sacó del archivo a mano, desde
    ese momento (si no, se volvería a archivar en el acto). Finalizada el
    1/11 con 10 días: el 11/11 ya está archivada. En días de Uruguay."""
    referencias = [f for f in (finalizada_at, desarchivada_at) if f is not None]
    if not referencias:
        return False
    return _dia_en_uruguay(max(referencias)) + timedelta(days=max(0, dias)) <= hoy


def dia_de_archivo(
    finalizada_at: datetime | None, archivada_at: datetime | None, desarchivada_at: datetime | None, dias: int,
) -> date | None:
    """El día en que una tarjeta aprobada pasó (o pasa) a Archivado: el que
    quedó anotado, o el que le toca sola. None si no hay con qué contar."""
    if archivada_at is not None:
        return _dia_en_uruguay(archivada_at)
    referencias = [f for f in (finalizada_at, desarchivada_at) if f is not None]
    if not referencias:
        return None
    return _dia_en_uruguay(max(referencias)) + timedelta(days=max(0, dias))


def oculta(
    finalizada_at: datetime | None, archivada_at: datetime | None, desarchivada_at: datetime | None,
    hoy: date, dias_para_archivar: int, dias_para_ocultar: int,
) -> bool:
    """Si una tarjeta aprobada ya se archivó "de verdad": lleva
    OCULTAR_ARCHIVADAS_DIAS o más en Archivado. No se carga en el tablero
    (queda en la base y la encuentra el buscador)."""
    dia = dia_de_archivo(finalizada_at, archivada_at, desarchivada_at, dias_para_archivar)
    return dia is not None and dia + timedelta(days=max(0, dias_para_ocultar)) <= hoy


def columna_de(
    momento: str, *, iniciada: bool, finalizada_at: datetime | None = None,
    archivada_at: datetime | None = None, desarchivada_at: datetime | None = None,
    hoy: date, dias_para_archivar: int, manual: str | None = None,
) -> str:
    """En qué columna del tablero va una tarjeta. `iniciada`: si quien entrega
    ya la arrancó o ya entregó algo alguna vez. `manual`: la columna a la que
    la llevó alguien del equipo a mano (0075), que manda sobre el momento."""
    if archivada_at is not None:
        # Archivada a mano manda sobre el momento: también la que se canceló
        # sin terminar (16/11/2026).
        return "archivado"
    if manual in COLUMNAS_A_MANO:
        return manual
    if momento == "revision":
        return "esperando"
    if momento == "cambios":
        return "en-proceso"
    if momento == "aprobada":
        if se_archiva_sola(finalizada_at, desarchivada_at, hoy, dias_para_archivar):
            return "archivado"
        return "finalizado"
    return "en-proceso" if iniciada else "ingresado"


class MovimientoInvalido(Exception):
    """El mensaje es para la persona. `codigo`: 403 si no le toca a ella, 422
    si ese movimiento no existe, 409 si para hacerlo falta otra cosa antes
    (entregar los materiales)."""

    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


@dataclass
class QuienMueve:
    """Lo que puede hacer, con esta tarjeta, quien la arrastra."""
    es_externo: bool
    # Es quien entrega: la agencia de la tarjeta, o la persona asignada.
    entrega: bool
    # Puede aprobar o pedir cambios sobre la versión que espera: le toca en
    # la cadena, o tiene `calendario.tareas` y decide como respaldo.
    decide: bool
    # Lleva la tarjeta del lado del equipo: gestiona las tareas, la creó o
    # está entre quienes la aprueban.
    del_equipo_de_la_tarjeta: bool
    # Es del equipo de Tienda (no una agencia): mueve la tarjeta a cualquier
    # columna, como en Trello (Ivan, 18/11/2026). Lo que tiene un sentido
    # (arrancar, aprobar si le toca, archivar) se sigue haciendo así; lo
    # demás es "a mano" (ver movimiento).
    libre: bool = False


_MOVIMIENTOS = {
    ("ingresado", "en-proceso"): "arrancar",
    ("en-proceso", "ingresado"): "volver",
    ("ingresado", "esperando"): "entregar",
    ("en-proceso", "esperando"): "entregar",
    ("esperando", "en-proceso"): "pedir-cambios",
    ("esperando", "finalizado"): "aprobar",
    ("finalizado", "archivado"): "archivar",
    # Una pieza que se canceló, sin terminar (16/11/2026). Desde Esperando
    # feedback no: hay una entrega que primero se decide.
    ("ingresado", "archivado"): "archivar",
    ("en-proceso", "archivado"): "archivar",
    ("archivado", "finalizado"): "desarchivar",
}


def movimiento(
    desde: str, a: str, quien: QuienMueve, *, hay_versiones: bool, vuelve_a: str = "finalizado",
) -> str:
    """Qué significa arrastrar una tarjeta de `desde` a `a`, si esta persona
    lo puede hacer; si no, MovimientoInvalido con el porqué.

    Desde el 18/11/2026 el equipo de Tienda la mueve a cualquier columna
    ("libre, como Trello"): si con las reglas de siempre no se puede, para
    alguien del equipo es "a-mano" (la ruta la deja en esa columna sin
    entregar ni decidir nada). Dos excepciones: quien la entrega y la lleva a
    Esperando feedback sigue entregando los materiales (409: se abre
    "Entregar"), y una columna que no existe no existe para nadie."""
    try:
        return _movimiento_con_reglas(desde, a, quien, hay_versiones=hay_versiones, vuelve_a=vuelve_a)
    except MovimientoInvalido as exc:
        if not quien.libre or quien.es_externo or desde not in COLUMNAS or a not in COLUMNAS:
            raise
        if exc.codigo == 409 and quien.entrega:
            raise
        return "a-mano"


def _movimiento_con_reglas(
    desde: str, a: str, quien: QuienMueve, *, hay_versiones: bool, vuelve_a: str = "finalizado",
) -> str:
    """Las reglas de siempre (las de una agencia, y las del equipo cuando
    hacen algo con sentido: arrancar, aprobar, pedir cambios, archivar). Es la
    regla del servidor: la pantalla solo la refleja.

    - Quien entrega (la agencia) arranca (Ingresado → En proceso) y entrega
      (→ Esperando feedback, siempre con los materiales: el arrastre abre
      "Entregar"). No aprueba, no finaliza ni archiva.
    - El equipo pide cambios (Esperando → En proceso) o aprueba (Esperando →
      Finalizado) si le toca en la cadena, y archiva o saca del archivo. Archiva
      también una que se canceló, desde Ingresado o En proceso.

    `vuelve_a`: si la tarjeta está en Archivado, la columna a la que vuelve al
    sacarla del archivo (ver columna_al_desarchivar): Finalizado si estaba
    aprobada; si se archivó sin terminar, la suya (Ingresado, En proceso...).
    """
    if desde not in COLUMNAS or a not in COLUMNAS:
        raise MovimientoInvalido("Esa columna no existe")
    if desde == a:
        return "nada"
    if quien.es_externo and a == "finalizado":
        raise MovimientoInvalido("La agencia no puede finalizar una tarjeta: la aprueba el equipo", 403)
    if desde == "archivado" and vuelve_a != "finalizado":
        # Archivada sin terminar: sale del archivo a donde estaba, no a otra.
        if a != vuelve_a:
            raise MovimientoInvalido(
                f"Esta tarjeta se archivó sin terminar: sale del archivo a {NOMBRES_DE_COLUMNA.get(vuelve_a, vuelve_a)}"
            )
        accion = "desarchivar"
    else:
        accion = _MOVIMIENTOS.get((desde, a))
    if accion is None:
        if a == "finalizado":
            raise MovimientoInvalido("Para finalizarla, primero tiene que haber una entrega esperando feedback")
        if a == "archivado":
            raise MovimientoInvalido("Está esperando feedback: hay que aprobarla o pedir cambios antes de archivarla")
        if desde in ("finalizado", "archivado"):
            raise MovimientoInvalido("Esta tarjeta ya está aprobada: no vuelve atrás")
        if desde == "esperando":
            raise MovimientoInvalido("Está esperando feedback: hay que aprobarla o pedir cambios")
        raise MovimientoInvalido(f"No se puede pasar de {NOMBRES_DE_COLUMNA[desde]} a {NOMBRES_DE_COLUMNA[a]}")

    if accion in ("arrancar", "volver"):
        if quien.es_externo and not quien.entrega:
            raise MovimientoInvalido("La arranca quien la entrega", 403)
        if not (quien.entrega or quien.del_equipo_de_la_tarjeta):
            raise MovimientoInvalido("La arranca quien la entrega", 403)
        if accion == "volver" and hay_versiones:
            raise MovimientoInvalido("Ya se entregó algo: no vuelve a Ingresado")
        return accion
    if accion == "entregar":
        if not quien.entrega:
            raise MovimientoInvalido("La manda a Esperando feedback quien la entrega, con los materiales", 403)
        # Arrastrar no alcanza: hacen falta los materiales. La pantalla abre
        # "Entregar" y la tarjeta pasa recién cuando se mandan.
        raise MovimientoInvalido("Para mandarla a Esperando feedback, entregá los materiales", 409)
    if accion in ("pedir-cambios", "aprobar"):
        if quien.es_externo:
            raise MovimientoInvalido("La agencia no aprueba ni pide cambios: lo hace el equipo", 403)
        if not quien.decide:
            raise MovimientoInvalido("No te toca decidir esta entrega: la decide quien está en la cadena de aprobación", 403)
        return accion
    # archivar / desarchivar
    if quien.es_externo or not quien.del_equipo_de_la_tarjeta:
        raise MovimientoInvalido("La archiva el equipo que lleva la tarjeta", 403)
    return accion


def destinos_posibles(
    desde: str, quien: QuienMueve, *, hay_versiones: bool, vuelve_a: str = "finalizado",
) -> list[str]:
    """A qué columnas puede llevar esta persona la tarjeta: lo que ofrece
    "Mover a…" y dónde se ilumina al arrastrar. Incluye Esperando feedback
    para quien entrega: ahí se abre "Entregar"."""
    out = []
    for a in COLUMNAS:
        if a == desde:
            continue
        try:
            movimiento(desde, a, quien, hay_versiones=hay_versiones, vuelve_a=vuelve_a)
            out.append(a)
        except MovimientoInvalido as exc:
            if exc.codigo == 409:
                out.append(a)
    return out


def config_por_defecto(
    creador_id: int, descripcion: str | None, tipo: str | None = None, opciones: list[str] | None = None,
    detalles: dict | None = None,
) -> dict:
    """Las entregas con las que nace una tarjeta, sin llenar el formulario
    largo: una fase "Entrega", la aprueba quien la creó, el tipo de pieza que
    corresponde a su tipo de tarea ("otro" si no tiene) y, como pedido, lo
    tildado con sus medidas más la descripción escrita. Lo demás se cambia
    después en "Más opciones"."""
    from app.services.tipos_de_tarea import descripcion_del_pedido, tipo_de

    t = tipo_de(tipo)
    partes = [descripcion_del_pedido(tipo, opciones, detalles), (descripcion or "").strip()]
    texto = "\n".join(p for p in partes if p)[:_LARGO_LARGO]
    pieza = t["pieza"] if t and t["pieza"] in TIPOS_DE_PIEZA else "otro"
    return {
        "tipo_pieza": pieza, "brief": {"detalle": texto} if texto else {},
        "fases": ["Entrega"], "aprobadores": [creador_id],
    }


# ---------------------------------------------------------------------------
# Retrabajo (pura)
# ---------------------------------------------------------------------------

def _bloque(rondas: list[int]) -> dict:
    n = len(rondas)
    if n == 0:
        return {"fases": 0, "rondasPromedio": None, "aLaPrimera": None}
    return {
        "fases": n,
        "rondasPromedio": round(sum(rondas) / n, 2),
        "aLaPrimera": round(100 * sum(1 for r in rondas if r == 1) / n),
    }


def metricas_de_retrabajo(filas: Iterable[tuple[str, int | None, str, int]]) -> dict:
    """Cuánto retrabajo hubo, sobre las fases aprobadas.

    Cada fila es una fase aprobada: (tipo de pieza, quién entregó la versión
    aprobada, mundo, en qué ronda se aprobó). Una versión que se aprobó con la
    decisión vieja («aprobado con cambios», hasta el 19/11/2026) es una
    versión aprobada como cualquiera: cuenta en su ronda.

    Devuelve el total y el desglose por tipo de pieza, por responsable y por
    mundo, cada uno con cuántas fases, las rondas promedio hasta aprobar y el
    % que se aprobó a la primera."""
    lista = list(filas)

    def agrupar(i: int) -> list[dict]:
        grupos: dict = {}
        for fila in lista:
            grupos.setdefault(fila[i], []).append(fila[3])
        return [{"clave": k, **_bloque(v)} for k, v in grupos.items()]

    por_tipo = sorted(agrupar(0), key=lambda g: list(TIPOS_DE_PIEZA).index(g["clave"]) if g["clave"] in TIPOS_DE_PIEZA else 99)
    # El responsable es un id de usuario o, en una agencia de afuera, su nombre
    # (un texto: ver _metricas en las rutas). Para ordenar no se comparan
    # números con textos: primero las personas, después las agencias.
    por_responsable = sorted(
        agrupar(1),
        key=lambda g: (-g["fases"], 1, g["clave"]) if isinstance(g["clave"], str) else (-g["fases"], 0, g["clave"] or 0),
    )
    por_mundo = sorted(agrupar(2), key=lambda g: (-g["fases"], g["clave"]))
    return {**_bloque([f[3] for f in lista]), "porTipo": por_tipo, "porResponsable": por_responsable, "porMundo": por_mundo}


# ---------------------------------------------------------------------------
# El análisis por agencia: cuánto tarda y cuántas se pasan de fecha (puro)
# ---------------------------------------------------------------------------
#
# Pedido de Ivan (20/11/2026): el retrabajo pasa a llamarse «Análisis de
# entregas» ("el retrabajo sí sirve, pero sería más un análisis") y suma
# "cuánto tarda cada agencia y cuántas piezas se pasan de fecha". Las rondas
# (metricas_de_retrabajo) siguen igual; esto va al lado.

EQUIPO_PROPIO = "equipo"
NOMBRE_DEL_EQUIPO_PROPIO = "El equipo (sin agencia)"


class PiezaDelAnalisis(NamedTuple):
    """Una pieza (una tarjeta del tablero), con lo que mira el análisis."""
    tarea_id: str
    # Quién la hace (calendario_tareas.para y .agencia): 'agencia', 'fuera' o 'tienda'.
    para: str | None
    agencia: str | None
    # Cuándo se le pidió: cuándo se creó la tarjeta (calendario_entregas.created_at).
    pedida_at: datetime
    # La primera versión que se subió, de cualquier fase y ronda.
    primera_entrega_at: datetime | None
    # Cuándo quedó aprobada entera (finalizada_at: todas sus fases).
    aprobada_at: datetime | None
    # Para cuándo se la pidió (calendario_tareas.vence), en días de Uruguay.
    vence: date | None
    # Si HOY le toca a quien la hace: sin entregar o con cambios pedidos,
    # y abierta (ni archivada ni cerrada a mano).
    le_toca_a_quien_la_hace: bool


def quien_la_hace(para: str | None, agencia: str | None) -> tuple[str, str]:
    """El grupo de una pieza en el análisis, (clave, nombre): su agencia, sea
    de la plataforma o de afuera, o el equipo si la hace la gente de la casa.
    La agencia se compara sin tildes, mayúsculas ni espacios de más
    («Disenadores» es Diseñadores) y uno de los tres tableros se escribe como
    en app/core/tableros.py. Pura."""
    from app.core import externos
    from app.core.tableros import tablero_de
    limpia = externos.limpiar_empresa(agencia) if para in ("agencia", "fuera") else None
    if not limpia:
        return EQUIPO_PROPIO, NOMBRE_DEL_EQUIPO_PROPIO
    return f"agencia:{externos.clave_de_empresa(limpia)}", tablero_de(limpia) or limpia


def _dias_entre(desde: datetime, hasta: datetime) -> float:
    return max(0.0, (hasta - desde).total_seconds() / 86400)


def _promedio_de_dias(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 1) if valores else None


def _bloque_de_tiempos(piezas: list[PiezaDelAnalisis], desde: datetime, hoy: date) -> dict:
    from app.core.alcance import hoy_en_uruguay
    entregadas = [p for p in piezas if p.primera_entrega_at is not None and p.primera_entrega_at >= desde]
    aprobadas = [p for p in piezas if p.aprobada_at is not None and p.aprobada_at >= desde]
    con_fecha = [p for p in entregadas if p.vence is not None]
    tarde = {p.tarea_id for p in con_fecha if hoy_en_uruguay(p.primera_entrega_at) > p.vence}
    vencidas = {p.tarea_id for p in piezas if p.le_toca_a_quien_la_hace and p.vence is not None and p.vence < hoy}
    return {
        "entregadas": len(entregadas),
        "diasHastaEntregar": _promedio_de_dias([_dias_entre(p.pedida_at, p.primera_entrega_at) for p in entregadas]),
        "aprobadas": len(aprobadas),
        "diasHastaAprobar": _promedio_de_dias([_dias_entre(p.pedida_at, p.aprobada_at) for p in aprobadas]),
        "aTiempo": round(100 * (len(con_fecha) - len(tarde)) / len(con_fecha)) if con_fecha else None,
        "entregaronTarde": len(tarde),
        "vencidas": len(vencidas),
        "sePasaron": len(tarde | vencidas),
    }


def analisis_por_agencia(piezas: Iterable[PiezaDelAnalisis], desde: datetime, hoy: date) -> dict:
    """Cuánto tarda cada agencia y cuántas piezas se pasan de fecha, en el
    período que empieza en `desde` (los días que se eligen en la pantalla).

    - **Entregadas**: las piezas cuya PRIMERA entrega cayó en el período.
    - **Cuánto tarda en entregar**: el promedio, en días, desde que se le
      pidió la pieza (se creó la tarjeta) hasta esa primera entrega.
    - **Cuánto tarda en aprobarse**: el promedio desde que se pidió hasta que
      quedó aprobada entera, de las que se aprobaron en el período. Ese
      tiempo también incluye lo que tardan en revisar quienes aprueban.
    - **Se pasaron de fecha**: las que entregaron por primera vez después
      de su vencimiento (de las entregadas en el período) más las que HOY
      están vencidas y le toca a quien la hace (sin entregar o con cambios
      pedidos). Cuenta cada pieza una vez. Lo que se pasó esperando la
      revisión del equipo no se le cuenta a la agencia.
    - **A tiempo**: el % de las entregadas con vencimiento cuya primera
      entrega llegó a tiempo (ese mismo día o antes).

    Devuelve el total y una fila por agencia: primero los tres tableros, en
    su orden, después las demás agencias por nombre y al final el equipo."""
    from app.core.tableros import TABLEROS
    lista = list(piezas)
    grupos: dict[str, list[PiezaDelAnalisis]] = {}
    nombres: dict[str, str] = {}
    for p in lista:
        clave, nombre = quien_la_hace(p.para, p.agencia)
        grupos.setdefault(clave, []).append(p)
        nombres.setdefault(clave, nombre)

    def orden(clave: str) -> tuple:
        nombre = nombres[clave]
        if clave == EQUIPO_PROPIO:
            return (2, 0, "")
        if nombre in TABLEROS:
            return (0, TABLEROS.index(nombre), "")
        return (1, 0, nombre.lower())

    por_agencia = []
    for clave in sorted(grupos, key=orden):
        bloque = _bloque_de_tiempos(grupos[clave], desde, hoy)
        if bloque["entregadas"] or bloque["aprobadas"] or bloque["vencidas"]:
            por_agencia.append({"clave": clave, "nombre": nombres[clave], **bloque})
    return {"total": _bloque_de_tiempos(lista, desde, hoy), "porAgencia": por_agencia}


# ---------------------------------------------------------------------------
# Los avisos (puros: el texto y la referencia)
# ---------------------------------------------------------------------------

def referencia(barra_id: str, tarea_id: str, version_id: str, evento: str) -> str:
    """Empieza por la acción y la tarea, como las de las tareas: la campanita
    lleva a la tarea con su segundo pedazo. Una por versión y por evento, así
    un reintento no manda el mismo aviso dos veces."""
    return f"{barra_id}:{tarea_id}:{version_id}:{evento}"[:255]


def _corto(texto: str, tope: int = 700) -> str:
    return texto if len(texto) <= tope else texto[: tope - 1].rstrip() + "…"


def mensaje_para_revisar(
    entrego: str, ronda: int, fase: str, tarea: str, accion: str, *, aprobo_antes: str | None = None,
) -> str:
    if aprobo_antes:
        return (f"{aprobo_antes} aprobó la ronda {ronda} de {fase} en «{tarea}» ({accion}). "
                "Ahora te toca revisarla a vos.")
    return f"{entrego} entregó la ronda {ronda} de {fase} en «{tarea}» ({accion}). Te toca revisarla."


def mensaje_de_cambios(quien: str, ronda: int, fase: str, tarea: str, marcas: int) -> str:
    cuantas = "1 marca" if marcas == 1 else f"{marcas} marcas"
    detalle = f" ({cuantas})" if marcas else ""
    return (f"{quien} pidió cambios en la ronda {ronda} de {fase} de «{tarea}»{detalle}. "
            f"Te toca entregar la ronda {ronda + 1}.")


def mensaje_de_avanzar(quien: str, ronda: int, tarea: str, comentario: str | None = None) -> str:
    """A quien la hace, cuando le dieron el OK para avanzar (25/11/2026)."""
    texto = f"{quien} dio el OK a la ronda {ronda} de «{tarea}»: avanzá con lo que falta."
    if comentario:
        texto += f" Dice: «{comentario}»"
    return _corto(texto)


def mensaje_de_aprobacion(
    quien: str, ronda: int, fase: str, tarea: str, *,
    siguiente_fase: str | None, sigue_revisando: str | None, terminada: bool,
) -> str:
    """Al responsable, cuando se aprobó la fase (o cuando la aprobó el último
    y sigue otra persona): dice qué sigue. Uno solo por decisión. Hasta el
    19/11/2026 llevaba también los "ajustes" del aprobado con cambios."""
    texto = f"{quien} aprobó la ronda {ronda} de {fase} de «{tarea}»."
    if sigue_revisando:
        texto += f" Ahora la revisa {sigue_revisando}."
    elif siguiente_fase:
        texto += f" Te toca entregar {siguiente_fase}."
    elif terminada:
        texto += " Era la última fase: la tarea quedó hecha."
    return _corto(texto)


def mensaje_de_tarea_aprobada(tarea: str, accion: str) -> str:
    return f"Se aprobó la última fase de «{tarea}» ({accion}): la tarea quedó hecha."


def mensaje_de_tarjeta_nueva(quien: str, tarea: str, opciones: list[str] | None, vence: date | None) -> str:
    """A quien la hace, cuando le nace una tarjeta: "Iván te pidió: Ciberlunes
    - Banners (Header, Slider, Checkout). Es para el 25/11." (16/11/2026)."""
    detalle = f" ({', '.join(opciones)})" if opciones else ""
    cuando = f" Es para el {vence.strftime('%d/%m')}." if vence else ""
    return _corto(f"{quien or 'El equipo'} te pidió: {tarea}{detalle}.{cuando}")


def mensaje_de_tarjetas_nuevas(quien: str, tareas: list[tuple[str, list[str] | None, date | None]]) -> str:
    """Varias tarjetas juntas (las de una plantilla): UN aviso por persona,
    no uno por tarjeta."""
    if len(tareas) == 1:
        return mensaje_de_tarjeta_nueva(quien, *tareas[0])
    titulos = [t for t, _, _ in tareas]
    lista = (f"{', '.join(titulos[:3])} y {len(titulos) - 3} más" if len(titulos) > 3
             else f"{', '.join(titulos[:-1])} y {titulos[-1]}")
    vences = [v for _, _, v in tareas if v]
    cuando = f" La primera es para el {min(vences).strftime('%d/%m')}." if vences else ""
    return _corto(f"{quien or 'El equipo'} te pidió {len(tareas)} tarjetas: {lista}.{cuando}")


def mensaje_de_devolucion(quien: str, tarea: str, accion: str, fase: str, motivo: str) -> str:
    """A quien entrega, cuando le devuelven una pieza que ya estaba aprobada."""
    motivo = " ".join((motivo or "").split())
    if motivo and motivo[-1] not in ".!?…":
        motivo += "."
    return _corto(f"{quien} devolvió «{tarea}» ({accion}) para corregir: {motivo} Te toca entregar {fase}.")


def mensaje_de_comentario(quien: str, tarea: str, texto: str) -> str:
    """A los que siguen la tarjeta, cuando alguien comenta (17/11/2026)."""
    texto = " ".join((texto or "").split())
    corto = texto if len(texto) <= 160 else texto[:159].rstrip() + "…"
    return _corto(f"{quien or 'Alguien'} comentó en «{tarea}»: {corto}")


def mensaje_de_tarjeta_finalizada(tarea: str, accion: str) -> str:
    """A quien creó la tarjeta, cuando se aprueba la última entrega."""
    return f"«{tarea}» ({accion}) quedó finalizada: se aprobó la entrega."


# ---------------------------------------------------------------------------
# Con la base
# ---------------------------------------------------------------------------

async def avisar(db: AsyncSession, user_id: int | None, mensaje: str, ref: str) -> bool:
    """Un aviso a la campanita, si no salió ya el mismo (misma persona y misma
    referencia). Usa el índice de la 0061."""
    if user_id is None:
        return False
    ya = (await db.execute(
        select(Notificacion.id).where(
            Notificacion.user_id == user_id,
            Notificacion.origen_tipo == ORIGEN,
            Notificacion.origen_ref == ref,
        ).limit(1)
    )).scalar_one_or_none()
    if ya is not None:
        return False
    # Solo campanita, nunca mail (Ivan, 19/11/2026: el tope es de 3.000 mails
    # por mes y el tablero se lo comería). Ver avisos_por_mail.SOLO_CAMPANITA.
    db.add(Notificacion(
        user_id=user_id, tipo=ORIGEN, mensaje=mensaje, origen_tipo=ORIGEN, origen_ref=ref, mail_pendiente=False,
    ))
    return True


async def decisiones_de(db: AsyncSession, version_id: str) -> Decisiones:
    return [
        (a, d) for a, d in (await db.execute(
            select(CalendarioDecision.aprobador_id, CalendarioDecision.decision)
            .where(CalendarioDecision.version_id == version_id)
            .order_by(CalendarioDecision.id)
        )).all()
    ]


async def recalcular(db: AsyncSession, entrega: CalendarioEntrega, tarea: CalendarioTarea) -> None:
    """Pone al día las fases, el resumen y el estado de la tarea después de
    cualquier cambio. Va en la misma transacción que el cambio."""
    fases = (await db.execute(
        select(CalendarioFase).where(CalendarioFase.tarea_id == tarea.id).order_by(CalendarioFase.orden)
    )).scalars().all()
    for fase, estado in zip(fases, estados_de_fases([f.estado for f in fases])):
        if fase.estado != estado:
            fase.estado = estado
    actual = next((f for f in fases if f.estado == "en-curso"), None)
    ultima = None
    if actual is not None:
        ultima = (await db.execute(
            select(CalendarioVersion).where(CalendarioVersion.fase_id == actual.id)
            .order_by(CalendarioVersion.ronda.desc()).limit(1)
        )).scalar_one_or_none()
    turno = None
    if ultima is not None and ultima.estado == "revision":
        turno = a_quien_le_toca(list(entrega.aprobadores or []), await decisiones_de(db, ultima.id))
    hay_versiones = (await db.execute(
        select(func.count()).select_from(CalendarioVersion).where(CalendarioVersion.tarea_id == tarea.id)
    )).scalar_one() > 0

    antes = (entrega.momento, entrega.fase_actual_id, entrega.ronda or 0)
    entrega.momento = momento_de(actual is not None, ultima.estado if ultima else None)
    entrega.fase_actual_id = actual.id if actual else None
    entrega.ronda = ultima.ronda if ultima else 0
    entrega.aprobador_de_turno_id = turno
    # Pasó algo de verdad (una entrega, una decisión, otra fase): la columna
    # vuelve a salir de las entregas, aunque alguien la hubiera movido a mano
    # (0075). Cambiar quién aprueba o el pedido no la mueve.
    if (entrega.momento, entrega.fase_actual_id, entrega.ronda) != antes:
        entrega.columna_manual = None
    nuevo = estado_de_tarea(entrega.momento, hay_versiones, tarea.estado)
    if nuevo != tarea.estado:
        tarea.estado = nuevo

    # Las fechas del tablero (0070). Entregar algo es haberla arrancado. Se
    # finaliza cuando se aprueba todo; si vuelve a haber algo para entregar
    # (le agregaron una fase), deja de estar finalizada y archivada.
    ahora = datetime.now(timezone.utc)
    if hay_versiones and entrega.iniciada_at is None:
        entrega.iniciada_at = ahora
    if entrega.momento == "aprobada":
        if entrega.finalizada_at is None:
            entrega.finalizada_at = ahora
    elif entrega.finalizada_at is not None or entrega.archivada_at is not None:
        entrega.finalizada_at = None
        entrega.archivada_at = None
        entrega.archivada_por_id = None
        entrega.desarchivada_at = None


def columna_de_entrega(entrega: CalendarioEntrega, hoy: date | None = None) -> str:
    """La columna del tablero de una entrega guardada (ver columna_de)."""
    from app.core.alcance import hoy_en_uruguay
    from app.core.config import settings
    return columna_de(
        entrega.momento,
        iniciada=entrega.iniciada_at is not None or (entrega.ronda or 0) > 0,
        finalizada_at=entrega.finalizada_at, archivada_at=entrega.archivada_at,
        desarchivada_at=entrega.desarchivada_at,
        hoy=hoy or hoy_en_uruguay(), dias_para_archivar=settings.ARCHIVAR_TARJETAS_DIAS,
        manual=getattr(entrega, "columna_manual", None),
    )


def columna_al_desarchivar(entrega) -> str:
    """A qué columna vuelve una tarjeta si se la saca del archivo: una
    aprobada, a Finalizado (sus días vuelven a contar desde ese momento); una
    que se archivó sin terminar (cancelada), a la que le toca por su momento:
    Ingresado, En proceso o Esperando feedback. Pura."""
    manual = getattr(entrega, "columna_manual", None)
    if manual in COLUMNAS_A_MANO:
        # La habían llevado a mano a una columna (0075): vuelve a esa.
        return manual
    if entrega.momento == "aprobada":
        return "finalizado"
    return columna_de(
        entrega.momento, iniciada=entrega.iniciada_at is not None or (entrega.ronda or 0) > 0,
        hoy=date.today(), dias_para_archivar=0,
    )


def archivada_sin_terminar(entrega) -> bool:
    """Si la tarjeta se archivó (canceló) sin que se aprobara: no se entrega
    ni se decide hasta que el equipo la saque del archivo. Pura."""
    return entrega.archivada_at is not None and entrega.momento != "aprobada"


def resumen_json(entrega: CalendarioEntrega, fases: list[CalendarioFase], rondas: dict[str, int]) -> dict:
    """Lo que viaja con la tarea en /calendario/datos y en "Mis tareas": en qué
    fase va, a quién le toca y en qué columna del tablero está. Sin imágenes
    ni historia (eso se pide al abrir)."""
    return {
        "tipoPieza": entrega.tipo_pieza,
        "momento": entrega.momento,
        "columna": columna_de_entrega(entrega),
        "ronda": entrega.ronda,
        "faseActual": entrega.fase_actual_id,
        "aprobadorDeTurno": entrega.aprobador_de_turno_id,
        "aprobadores": list(entrega.aprobadores or []),
        "fases": [
            {"id": f.id, "nombre": f.nombre, "estado": f.estado, "rondas": rondas.get(f.id, 0),
             # Lo que hay que cambiar, si la fase la abrió una devolución (0072).
             "motivo": f.motivo}
            for f in fases
        ],
    }


def es_tarjeta_propia(usuario, tarea, entrega) -> bool:
    """Si una tarjeta es "de" esta persona: se ve siempre en su tablero,
    aunque la campaña quede fuera de su alcance del calendario (0070), porque
    la tiene que trabajar con anticipación. Pura.

    - Una cuenta externa: la tiene asignada o es de su agencia.
    - Alguien del equipo: la hace, la pidió, la lleva por Tienda (su
      responsable, 0090) o está entre quienes la aprueban."""
    from app.core import externos

    if externos.es_externo(usuario):
        return externos.es_tarea_propia(usuario, tarea)
    if usuario.id in (
        tarea.asignado_a_id, tarea.creado_por_id, getattr(tarea, "responsable_id", None),
        getattr(entrega, "creado_por_id", None),
    ):
        return True
    return usuario.id in list(getattr(entrega, "aprobadores", None) or [])


def condicion_tarjeta_propia(usuario):
    """La misma regla que `es_tarjeta_propia`, para el WHERE de una consulta
    que junta tareas con sus entregas."""
    from app.core import externos

    if externos.es_externo(usuario):
        return externos.condicion_tarea_propia(CalendarioTarea, usuario)
    return or_(
        CalendarioTarea.asignado_a_id == usuario.id,
        CalendarioTarea.creado_por_id == usuario.id,
        CalendarioTarea.responsable_id == usuario.id,
        CalendarioEntrega.creado_por_id == usuario.id,
        CalendarioEntrega.aprobadores.contains([usuario.id]),
    )


async def tarjetas_propias(db: AsyncSession, usuario, tarea_ids) -> set[str]:
    """De esas tareas, las que son tarjetas propias de esta persona."""
    ids = [i for i in set(tarea_ids or []) if i]
    if not ids:
        return set()
    filas = (await db.execute(
        select(CalendarioTarea, CalendarioEntrega)
        .join(CalendarioEntrega, CalendarioEntrega.tarea_id == CalendarioTarea.id)
        .where(CalendarioTarea.id.in_(ids))
    )).all()
    return {t.id for t, e in filas if es_tarjeta_propia(usuario, t, e)}


async def destinatarios_de_la_tarjeta(db: AsyncSession, tarea: CalendarioTarea, mundo: str) -> list[int]:
    """A quiénes les llega lo que es "para quien entrega": la persona
    asignada y, si la tarea es para una agencia, todas las cuentas activas de
    esa agencia que entran al mundo (la tarjeta es de la agencia: la puede
    estar mirando cualquiera de ellas). Sin repetidos."""
    from app.core import externos
    from app.core.mundos import puede_abrir
    from app.models.user import User

    ids: list[int] = []
    if tarea.asignado_a_id is not None:
        ids.append(tarea.asignado_a_id)
    # La agencia se compara sin tildes ni mayúsculas (19/11/2026): a una
    # cuenta guardada con «Disenadores» le llega lo de Diseñadores.
    clave = externos.clave_de_empresa(tarea.agencia) if tarea.para == "agencia" else None
    if clave:
        for u in (await db.execute(
            select(User).where(
                User.es_externo.is_(True), User.is_active.is_(True),
                externos.empresa_en_sql(User.empresa) == clave,
            ).order_by(User.id)
        )).scalars():
            if u.id not in ids and puede_abrir(u, mundo) and externos.puede_tener(u, "calendario.view"):
                ids.append(u.id)
    return ids


async def gestores_del_mundo(db: AsyncSession, mundo: str, menos: int | None = None) -> list[int]:
    """Quiénes pueden decidir como respaldo en ese mundo: las cuentas activas
    del equipo con `calendario.tareas` (o superadmin) que entran al mundo. Es a
    quienes hay que avisarles cuando una entrega no tiene a nadie más que la
    pueda aprobar. `menos`: a quién no (quien acaba de entregar)."""
    from app.core import externos
    from app.core.mundos import puede_abrir
    from app.models.user import User

    ids: list[int] = []
    for u in (await db.execute(
        select(User).where(User.is_active.is_(True), User.es_externo.is_(False)).order_by(User.id)
    )).scalars():
        if u.id != menos and puede_abrir(u, mundo) and externos.puede_tener(u, "calendario.tareas"):
            ids.append(u.id)
    return ids


async def crear_entregas_por_defecto(
    db: AsyncSession, tarea: CalendarioTarea, creador_id: int, aprobadores: list[int] | None = None,
) -> CalendarioEntrega:
    """Las entregas con las que nace una tarea para la agencia (ver
    config_por_defecto). Va en la misma transacción que el alta de la tarea,
    después de que la tarea existe (FK).

    `aprobadores`: para cuando quien la crea no puede ser quien la aprueba
    (la va a hacer esa misma persona). Vacía = decide quien tiene
    `calendario.tareas`, como respaldo."""
    conf = config_por_defecto(
        creador_id, tarea.descripcion, tarea.tipo, list(tarea.opciones or []), dict(tarea.detalles or {}),
    )
    if aprobadores is not None:
        conf["aprobadores"] = list(aprobadores)
    entrega = CalendarioEntrega(
        tarea_id=tarea.id, tipo_pieza=conf["tipo_pieza"], brief=conf["brief"], aprobadores=conf["aprobadores"],
        momento="produccion", ronda=0, creado_por_id=creador_id,
    )
    db.add(entrega)
    for orden, nombre in enumerate(conf["fases"]):
        db.add(CalendarioFase(
            id=nuevo_id("fa"), tarea_id=tarea.id, orden=orden, nombre=nombre,
            estado="en-curso" if orden == 0 else "pendiente",
        ))
    await db.flush()
    entrega.fase_actual_id = (await db.execute(
        select(CalendarioFase.id).where(CalendarioFase.tarea_id == tarea.id).order_by(CalendarioFase.orden).limit(1)
    )).scalar_one()
    return entrega


async def resumenes_de_entregas(db: AsyncSession, tareas, entregas: list | None = None) -> dict[str, dict]:
    """El resumen de cada tarea que lleva entregas, de entre `tareas` (una
    lista de ids o una subconsulta). Dos consultas, y una sola si no hay
    ninguna (lo común en la mayoría de los mundos). Si quien llama ya tiene
    las entregas (el tablero), las pasa y se ahorra una.

    Cada ida y vuelta a la base cuesta, con la base lejos, más que la consulta
    misma: por eso las rondas de cada fase vienen en la misma consulta que las
    fases (16/11/2026, medido en el tablero con 3.100 tarjetas)."""
    if entregas is None:
        entregas = (await db.execute(
            select(CalendarioEntrega).where(CalendarioEntrega.tarea_id.in_(tareas))
        )).scalars().all()
    if not entregas:
        return {}
    ids = [e.tarea_id for e in entregas]
    ultima_ronda = (
        select(func.max(CalendarioVersion.ronda)).where(CalendarioVersion.fase_id == CalendarioFase.id)
        .correlate(CalendarioFase).scalar_subquery()
    )
    fases: dict[str, list[CalendarioFase]] = {}
    rondas: dict[str, int] = {}
    for f, n in (await db.execute(
        select(CalendarioFase, ultima_ronda).where(CalendarioFase.tarea_id.in_(ids)).order_by(CalendarioFase.orden)
    )).all():
        fases.setdefault(f.tarea_id, []).append(f)
        if n is not None:
            rondas[f.id] = n
    return {e.tarea_id: resumen_json(e, fases.get(e.tarea_id, []), rondas) for e in entregas}


# ---------------------------------------------------------------------------
# La pasada diaria
# ---------------------------------------------------------------------------

async def purgar_imagenes_viejas(
    db: AsyncSession, hoy: date | None = None, *, dias: int = 30, dias_final: int = 120,
) -> int:
    """NO SE USA desde el 19/11/2026: las imágenes no se borran (ver arriba).
    Queda solo por si algún día hay que liberar espacio A MANO, con los días
    que se pasen; nadie la llama sola. Vacía los bytes (la grande y la
    miniatura) de las versiones cuya acción terminó hace más de `dias`
    (`dias_final` para la versión aprobada de la última fase); las versiones,
    decisiones y marcas quedan."""
    hoy = hoy or date.today()
    otra_fase = aliased(CalendarioFase)
    ultima_fase = (
        select(func.max(otra_fase.orden)).where(otra_fase.tarea_id == CalendarioVersion.tarea_id)
        .correlate(CalendarioVersion).scalar_subquery()
    )
    es_final = and_(CalendarioVersion.estado == "aprobada", CalendarioFase.orden == ultima_fase)
    vencidas = (
        select(CalendarioVersion.id)
        .join(CalendarioFase, CalendarioFase.id == CalendarioVersion.fase_id)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioVersion.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .where(or_(
            and_(not_(es_final), CalendarioBarra.hasta < hoy - timedelta(days=dias)),
            and_(es_final, CalendarioBarra.hasta < hoy - timedelta(days=dias_final)),
        ))
    )
    r = await db.execute(
        update(CalendarioVersionImagen)
        .where(
            CalendarioVersionImagen.version_id.in_(vencidas),
            or_(CalendarioVersionImagen.datos.isnot(None), CalendarioVersionImagen.miniatura.isnot(None)),
        )
        .values(datos=None, miniatura=None, purgada_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return r.rowcount or 0


async def archivar_finalizadas(db: AsyncSession, hoy: date | None = None) -> int:
    """Deja guardado en Archivado lo que ya se archivó solo (ver
    se_archiva_sola): las finalizadas hace ARCHIVAR_TARJETAS_DIAS o más que
    nadie archivó a mano. El tablero ya las muestra en Archivado al leer;
    esto lo deja anotado (con `archivada_por_id` en null: se archivó sola) y
    sube la revisión de cada mundo tocado, así quien tiene el tablero abierto
    lo ve moverse sin recargar. También archiva las que quedaron sin terminar
    con la tarea cerrada a mano (ver abajo). Devuelve cuántas archivó."""
    from app.api.routes.calendario import _nueva_revision
    from app.core.alcance import hoy_en_uruguay
    from app.core.config import settings

    hoy = hoy or hoy_en_uruguay()
    dias = max(0, settings.ARCHIVAR_TARJETAS_DIAS)
    candidatas = (await db.execute(
        select(CalendarioEntrega, CalendarioBarra.mundo)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioEntrega.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .where(
            CalendarioEntrega.momento == "aprobada",
            CalendarioEntrega.archivada_at.is_(None),
            CalendarioEntrega.finalizada_at.isnot(None),
            # Aprobada, pero alguien la volvió a una columna a mano (0075):
            # no está en Finalizado, no se archiva sola.
            CalendarioEntrega.columna_manual.is_(None),
        )
        .with_for_update(of=CalendarioEntrega)
    )).all()
    ahora = datetime.now(timezone.utc)
    mundos: set[str] = set()
    n = 0
    for entrega, mundo in candidatas:
        if se_archiva_sola(entrega.finalizada_at, entrega.desarchivada_at, hoy, dias):
            entrega.archivada_at = ahora
            entrega.archivada_por_id = None
            mundos.add(mundo)
            n += 1
    # Las que se cerraron a mano («hecha» desde la ficha) sin terminar antes
    # de que cerrarlas las archivara (16/11/2026): quedaban para siempre en
    # Ingresado o En proceso. Desde ahora cerrar la tarea ya la archiva; esto
    # acomoda las de antes y cualquier camino que cierre la tarea sin pasar
    # por ahí. Una tarea con entregas solo queda «hecha» sola al aprobarse.
    for entrega, mundo in (await db.execute(
        select(CalendarioEntrega, CalendarioBarra.mundo)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioEntrega.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .where(
            CalendarioEntrega.momento != "aprobada",
            CalendarioEntrega.archivada_at.is_(None),
            CalendarioTarea.estado == "hecha",
        )
        .with_for_update(of=CalendarioEntrega)
    )).all():
        entrega.archivada_at = ahora
        entrega.archivada_por_id = None
        mundos.add(mundo)
        n += 1
    for mundo in sorted(mundos):
        await _nueva_revision(db, mundo)
    await db.commit()
    return n


async def run_pasada_diaria_entregas() -> None:
    """Loop perpetuo: una pasada al arrancar y después una por día. Pasa a
    Archivado las tarjetas finalizadas hace ARCHIVAR_TARJETAS_DIAS. Hasta el
    19/11/2026 también borraba las imágenes viejas: ya no (ver arriba).

    PENDIENTE (Ivan, 16/11/2026; no se hace hasta que se conecte Outlook):
    acá va también el mail a toda la empresa 1 o 2 días antes de que arranque
    una acción grande, con su entrega final (por ejemplo, el mailing de Black
    Friday ya aprobado). La pasada diaria es el lugar: ya sabe qué acciones
    arrancan y qué tarjetas quedaron finalizadas."""
    from app.core.database import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                n = await archivar_finalizadas(db)
            if n:
                logger.info("tablero: %d tarjeta(s) finalizada(s) pasaron solas a Archivado", n)
        except Exception as exc:
            logger.error("tablero: falló el archivado diario -- %s", exc, exc_info=True)
        await asyncio.sleep(24 * 3600)
