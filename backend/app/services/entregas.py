"""Entregas por fases: la lógica, separada de las rutas.

Pedido de Ivan (15/11/2026): una tarea "tiene fase 1, fase 2, fase 3…; se
entrega, se aprueba o vuelve con correcciones, la agencia devuelve con las
correcciones aplicadas, puede volver otra vez, hasta que se aprueba". Más lo
que aprobó encima: marcar la corrección sobre la pieza, "aprobado con
cambios", el pedido según el tipo de pieza, la aprobación en cadena y medir el
retrabajo. Las tablas están en app/models/entregas.py; las rutas, en
app/api/routes/entregas.py.

Lo de arriba de este archivo es puro (sin base) a propósito: las reglas del
flujo —a quién le toca, cuándo una versión queda aprobada, qué pasa con la
tarea— se prueban en tests/test_entregas_por_fases.py sin levantar nada.

El flujo, en corto:

1. Quien lidera marca que la tarea lleva entregas: tipo de pieza, brief,
   fases y la cadena de aprobadores. La primera fase queda en curso.
2. El responsable de la tarea entrega: una versión (ronda 1) con imágenes.
3. La revisa el primer aprobador de la cadena. Si aprueba (o "aprueba con
   cambios"), pasa al siguiente; cuando aprueba el último, la versión queda
   aprobada, la fase también y arranca la siguiente. Si cualquiera pide
   cambios, la versión vuelve: el responsable entrega la ronda 2, tildando
   qué marcas corrigió, y la cadena arranca de nuevo desde el primero (lo
   que cambió lo tienen que ver todos).
4. Aprobada la última fase, la tarea queda hecha sola.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

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

MAX_FASES = 8
MAX_APROBADORES = 6
MAX_IMAGENES = 4
# La grande llega comprimida del navegador (1600 px, JPEG 0,75: 50-250 KB).
# Una de 2 MB ya es algo que no pasó por el navegador. La miniatura (320 px)
# pesa 6-20 KB.
MAX_BYTES_IMAGEN = 2 * 1024 * 1024
MAX_BYTES_MINIATURA = 256 * 1024
MAX_MARCAS = 40
# Cuándo se borran las imágenes (la grande y la miniatura), contado desde que
# termina la acción. Las versiones, decisiones y marcas quedan siempre: solo
# se van los bytes. La base es de 500 MB para toda la plataforma.
DIAS_DE_RETENCION = 30
# La versión final (la aprobada de la última fase: la pieza que salió) se
# guarda más, por si hay que reimprimir o reclamar algo.
DIAS_DE_RETENCION_FINAL = 120

ORIGEN = "calendario_entrega"
DECISIONES = ("aprobada", "aprobada-con-cambios", "cambios")
APRUEBAN = ("aprobada", "aprobada-con-cambios")
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


# ---------------------------------------------------------------------------
# La cadena de aprobación (pura)
# ---------------------------------------------------------------------------

Decisiones = list[tuple[int | None, str]]


def _aprobaron(decisiones: Decisiones) -> set[int | None]:
    return {a for a, d in decisiones if d in APRUEBAN}


def resultado_de_version(aprobadores: list[int], decisiones: Decisiones) -> str:
    """'cambios' si alguien los pidió; 'aprobada' si aprobaron todos los de la
    cadena; si no, sigue en 'revision'.

    Sin cadena (le sacaron todos los aprobadores a mitad de camino) decide el
    respaldo, y con una aprobación alcanza: si no, la versión quedaría
    trabada para siempre."""
    if any(d == "cambios" for _, d in decisiones):
        return "cambios"
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
    'aprobada' (todas las fases). Son las columnas del tablero."""
    if not hay_fase_actual:
        return "aprobada"
    if estado_ultima_version == "revision":
        return "revision"
    if estado_ultima_version == "cambios":
        return "cambios"
    return "produccion"


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
#   Archivado          aprobada, y archivada a mano o finalizada hace
#                      ARCHIVAR_TARJETAS_DIAS o más (la archiva sola)
#
# Así no hay dos verdades que se puedan separar: si alguien aprueba desde el
# detalle (sin arrastrar), la tarjeta ya está en Finalizado.

COLUMNAS = ("ingresado", "en-proceso", "esperando", "finalizado", "archivado")
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
    hoy: date, dias_para_archivar: int,
) -> str:
    """En qué columna del tablero va una tarjeta. `iniciada`: si quien entrega
    ya la arrancó o ya entregó algo alguna vez."""
    if momento == "revision":
        return "esperando"
    if momento == "cambios":
        return "en-proceso"
    if momento == "aprobada":
        if archivada_at is not None or se_archiva_sola(finalizada_at, desarchivada_at, hoy, dias_para_archivar):
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


_MOVIMIENTOS = {
    ("ingresado", "en-proceso"): "arrancar",
    ("en-proceso", "ingresado"): "volver",
    ("ingresado", "esperando"): "entregar",
    ("en-proceso", "esperando"): "entregar",
    ("esperando", "en-proceso"): "pedir-cambios",
    ("esperando", "finalizado"): "aprobar",
    ("finalizado", "archivado"): "archivar",
    ("archivado", "finalizado"): "desarchivar",
}


def movimiento(desde: str, a: str, quien: QuienMueve, *, hay_versiones: bool) -> str:
    """Qué significa arrastrar una tarjeta de `desde` a `a`, si esta persona
    lo puede hacer; si no, MovimientoInvalido con el porqué. Es la regla del
    servidor: la pantalla solo la refleja.

    - Quien entrega (la agencia) arranca (Ingresado → En proceso) y entrega
      (→ Esperando feedback, siempre con los materiales: el arrastre abre
      "Entregar"). No aprueba, no finaliza ni archiva.
    - El equipo pide cambios (Esperando → En proceso) o aprueba (Esperando →
      Finalizado) si le toca en la cadena, y archiva o saca del archivo.
    """
    if desde not in COLUMNAS or a not in COLUMNAS:
        raise MovimientoInvalido("Esa columna no existe")
    if desde == a:
        return "nada"
    if quien.es_externo and a == "finalizado":
        raise MovimientoInvalido("La agencia no puede finalizar una tarjeta: la aprueba el equipo", 403)
    accion = _MOVIMIENTOS.get((desde, a))
    if accion is None:
        if a == "finalizado":
            raise MovimientoInvalido("Para finalizarla, primero tiene que haber una entrega esperando feedback")
        if a == "archivado":
            raise MovimientoInvalido("Solo se archiva una tarjeta finalizada")
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


def destinos_posibles(desde: str, quien: QuienMueve, *, hay_versiones: bool) -> list[str]:
    """A qué columnas puede llevar esta persona la tarjeta: lo que ofrece
    "Mover a…" y dónde se ilumina al arrastrar. Incluye Esperando feedback
    para quien entrega: ahí se abre "Entregar"."""
    out = []
    for a in COLUMNAS:
        if a == desde:
            continue
        try:
            movimiento(desde, a, quien, hay_versiones=hay_versiones)
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
    aprobada, mundo, en qué ronda se aprobó). "Aprobado con cambios" cuenta
    como aprobada en esa ronda: es justamente lo que evita una ronda más por
    un error de tilde.

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
    por_responsable = sorted(agrupar(1), key=lambda g: (-g["fases"], g["clave"] or 0))
    por_mundo = sorted(agrupar(2), key=lambda g: (-g["fases"], g["clave"]))
    return {**_bloque([f[3] for f in lista]), "porTipo": por_tipo, "porResponsable": por_responsable, "porMundo": por_mundo}


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


def mensaje_de_aprobacion(
    quien: str, ronda: int, fase: str, tarea: str, *, con_cambios: bool, ajustes: list[str],
    siguiente_fase: str | None, sigue_revisando: str | None, terminada: bool,
) -> str:
    """Al responsable. "Aprobado con cambios" lleva los ajustes; si con esto
    se aprobó la fase, dice qué sigue. Uno solo por decisión."""
    texto = f"{quien} aprobó{' con cambios' if con_cambios else ''} la ronda {ronda} de {fase} de «{tarea}»."
    if ajustes:
        texto += " Ajustes: " + "; ".join(f"{i}) {t}" for i, t in enumerate(ajustes, 1)) + "."
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
    db.add(Notificacion(user_id=user_id, tipo=ORIGEN, mensaje=mensaje, origen_tipo=ORIGEN, origen_ref=ref))
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

    entrega.momento = momento_de(actual is not None, ultima.estado if ultima else None)
    entrega.fase_actual_id = actual.id if actual else None
    entrega.ronda = ultima.ronda if ultima else 0
    entrega.aprobador_de_turno_id = turno
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
    )


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
            {"id": f.id, "nombre": f.nombre, "estado": f.estado, "rondas": rondas.get(f.id, 0)}
            for f in fases
        ],
    }


def es_tarjeta_propia(usuario, tarea, entrega) -> bool:
    """Si una tarjeta es "de" esta persona: se ve siempre en su tablero,
    aunque la campaña quede fuera de su alcance del calendario (0070), porque
    la tiene que trabajar con anticipación. Pura.

    - Una cuenta externa: la tiene asignada o es de su agencia.
    - Alguien del equipo: la hace, la pidió o está entre quienes la aprueban."""
    from app.core import externos

    if externos.es_externo(usuario):
        return externos.es_tarea_propia(usuario, tarea)
    if usuario.id in (tarea.asignado_a_id, tarea.creado_por_id, getattr(entrega, "creado_por_id", None)):
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
    empresa = externos.limpiar_empresa(tarea.agencia) if tarea.para == "agencia" else None
    if empresa:
        for u in (await db.execute(
            select(User).where(
                User.es_externo.is_(True), User.is_active.is_(True),
                externos.empresa_en_sql(User.empresa) == empresa.lower(),
            ).order_by(User.id)
        )).scalars():
            if u.id not in ids and puede_abrir(u, mundo) and externos.puede_tener(u, "calendario.view"):
                ids.append(u.id)
    return ids


async def crear_entregas_por_defecto(db: AsyncSession, tarea: CalendarioTarea, creador_id: int) -> CalendarioEntrega:
    """Las entregas con las que nace una tarea para la agencia (ver
    config_por_defecto). Va en la misma transacción que el alta de la tarea,
    después de que la tarea existe (FK)."""
    conf = config_por_defecto(
        creador_id, tarea.descripcion, tarea.tipo, list(tarea.opciones or []), dict(tarea.detalles or {}),
    )
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
# La purga
# ---------------------------------------------------------------------------

def dias_de_retencion(es_final: bool) -> int:
    """Cuánto se guardan las imágenes de una versión después de que termina
    su acción: la final, DIAS_DE_RETENCION_FINAL; cualquier otra (las que
    volvieron con cambios, los bocetos aprobados), DIAS_DE_RETENCION."""
    return DIAS_DE_RETENCION_FINAL if es_final else DIAS_DE_RETENCION


def vencio(fin_de_la_accion: date, es_final: bool, hoy: date) -> bool:
    """Si las imágenes de una versión ya se tienen que borrar."""
    return fin_de_la_accion < hoy - timedelta(days=dias_de_retencion(es_final))


async def purgar_imagenes_viejas(db: AsyncSession, hoy: date | None = None) -> int:
    """Borra los bytes de las imágenes (la grande y la miniatura) que ya
    vencieron (ver `vencio`). Las versiones, decisiones y marcas quedan: la
    historia de rondas y el retrabajo se siguen viendo, sin las fotos.
    Devuelve cuántas imágenes se vaciaron.

    "Final" es la versión aprobada de la ÚLTIMA fase de su tarea: la pieza que
    salió. Un boceto aprobado no es final."""
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
            and_(not_(es_final), CalendarioBarra.hasta < hoy - timedelta(days=DIAS_DE_RETENCION)),
            and_(es_final, CalendarioBarra.hasta < hoy - timedelta(days=DIAS_DE_RETENCION_FINAL)),
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
    lo ve moverse sin recargar. Devuelve cuántas archivó."""
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
    for mundo in sorted(mundos):
        await _nueva_revision(db, mundo)
    await db.commit()
    return n


async def run_purga_entregas_loop() -> None:
    """Loop perpetuo, como la purga de cenefas: una pasada al arrancar y
    después una por día. Hace las dos cosas que vencen con los días: borrar
    las imágenes viejas y pasar a Archivado las tarjetas finalizadas hace
    ARCHIVAR_TARJETAS_DIAS."""
    from app.core.database import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                n = await purgar_imagenes_viejas(db)
            if n:
                logger.info("purga_entregas: %d imagen(es) vencidas liberadas", n)
        except Exception as exc:
            logger.error("purga_entregas: falló la pasada -- %s", exc, exc_info=True)
        try:
            async with AsyncSessionLocal() as db:
                n = await archivar_finalizadas(db)
            if n:
                logger.info("tablero: %d tarjeta(s) finalizada(s) pasaron solas a Archivado", n)
        except Exception as exc:
            logger.error("tablero: falló el archivado diario -- %s", exc, exc_info=True)
        await asyncio.sleep(24 * 3600)
