"""entregas.py — entregas por fases con rondas de corrección (0067) y el
tablero de tarjetas estilo Trello (0070).

  PUT    /calendario/tareas/{id}/entregas     — que la tarea lleve entregas: tipo, brief, fases, aprobadores
  DELETE /calendario/tareas/{id}/entregas     — que deje de llevarlas (solo si no se entregó nada)
  GET    /calendario/tareas/{id}/entregas     — todo: fases, rondas, imágenes (los ids), marcas, decisiones
  POST   /calendario/tareas/{id}/control-previo — antes de entregar: ¿se ve hecho lo pedido? (la IA; los cambios
                                                  o, en la primera ronda, el pedido inicial) y lo que
                                                  encontró en la pieza, como lo vería quien aprueba
  POST   /calendario/tareas/{id}/versiones    — entregar una ronda (multipart: imágenes y/o un link, y un ZIP)
  POST   /calendario/tareas/{id}/mover        — arrastrar la tarjeta a otra columna del tablero
  POST   /calendario/versiones/{id}/decision  — aprobar o pedir cambios
  GET    /calendario/versiones/{id}/zip       — el ZIP original de la ronda, tal cual lo mandó la agencia
  GET    /calendario/entregas/imagenes/{id}   — una imagen (?tam=mini|grande)
  GET    /calendario/entregas?mundo=&rev=     — el tablero del mundo (5 columnas)
  GET    /calendario/entregas/metricas        — el análisis de entregas (rondas, tiempos y fechas por agencia)
  GET    /calendario/entregas/archivadas      — más de Archivado ("Ver más")
  GET    /calendario/entregas/buscar?q=       — el buscador, también en lo archivado de verdad
  GET    /calendario/mis-entregas             — lo que espera MI decisión y lo que me devolvieron

Pedido de Ivan (15/11/2026), como tarjetas de Trello con la agencia; y el
16/11/2026, el tablero en sí: Ingresado, En proceso, Esperando feedback,
Finalizado y Archivado, arrastrando las tarjetas. La lógica pura está en
app/services/entregas.py; acá están los permisos, que se cuidan todos del lado
del servidor:

- Ve todo esto quien tiene el calendario del mundo de la acción, dentro de
  su alcance (0070, app/core/alcance.py)... y sus tarjetas siempre, aunque la
  campaña quede fuera (ver es_tarjeta_propia). Una cuenta externa (la
  agencia) ve SOLO sus tarjetas (ver app/core/externos.py y `_tarea_y_barra`):
  de lo demás, un 404 igual al de algo que no existe.
- Configura (tipo, brief, fases, aprobadores) quien tiene `calendario.tareas`.
- Entrega quien la hace (`puede_entregar`): la persona asignada, o cualquier
  cuenta de la agencia de la tarjeta.
- Decide el aprobador al que le toca; quien tiene `calendario.tareas` puede
  decidir por él como respaldo. Nadie decide sobre lo que subió. Una cuenta
  externa no aprueba: no se la puede poner en la cadena ni decide.
- Las decisiones son dos: aprobar o pedir cambios. «Aprobado con cambios» (y
  con él las marcas de tipo "ajuste" y la ruta para tildarlas sueltas) se
  sacó el 19/11/2026 (Ivan: "me resulta raro ese botón. No creo que sume
  nada"). Las decisiones y marcas viejas quedan en la base y se siguen
  leyendo (ver reglas.APRUEBAN).
- La decisión puede llevar una nota interna (0069): la ve el equipo, nunca la
  agencia (ni en la tarea ni en el aviso). Las marcas y el comentario sí, que
  son para ella.
- Arrastrar en el tablero pasa por las mismas reglas (`mover`, y
  reglas.movimiento): la pantalla no alcanza.

Las imágenes NO viajan en /calendario/datos (que se pregunta cada 15 s): ahí va
solo el resumen de cada tarea (en qué fase, a quién le toca). Las imágenes se
piden al abrir la tarea, de a una.

Cada versión entregada se la revisa la IA en segundo plano, después de
contestar la subida (app/services/revision_ia.py). Lo que encontró se pide
aparte (app/api/routes/revision_ia.py) y lo ven solo los aprobadores y quien
gestiona: ver `puede_ver_revision`. Desde el 19/11/2026 la IA mira también lo
que venga en un ZIP (campo `zip` del multipart) y detrás del link
(app/services/materiales.py).

El ZIP, desde el 19/11/2026, se guarda tal cual como el original de la ronda
(calendario_version_zips): se baja de a partes, con las mismas reglas que las
imágenes de la versión (`_exigir_ver_archivos`). Y lo que el navegador no
pudo mostrar de adentro (las páginas de un PDF) el servidor lo pasa a
imágenes de la ronda al entregar: ver `entregar`.
"""
import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import LargeBinary, String, and_, delete, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.calendario import (
    _ID, _exigir_gestion_de_tareas, _nueva_revision, _puede_gestionar_tareas, _puede_ver_el_mundo,
    _rev_para, _ve_una_parte, ids_de_aprobadores_de, nombre_sin_mail, nombres_para_externo, vence_al_reabrir,
)
from app.core.config import settings
from app.core import alcance, externos
from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import require_permission
from app.core.mundos import MUNDOS, exigir_mundo, mundos_de
from app.core.rate_limit import limiter
from app.models.calendario import CalendarioBarra, CalendarioRevision, CalendarioRevisionMundo, CalendarioTarea
from app.models.entregas import (
    CalendarioComentario, CalendarioDecision, CalendarioEntrega, CalendarioFase, CalendarioMarca, CalendarioVersion,
    CalendarioVersionImagen, CalendarioVersionZip,
)
from app.models.revision_ia import CalendarioRevisionIA
from app.models.user import User
from app.services import entregas as reglas
from app.services import materiales, revision_ia, tipos_de_tarea
from app.services.espacio import MB, entra, exigir_lugar, hay_lugar
from app.services.entregas import (
    MAX_BYTES_IMAGEN, MAX_BYTES_MINIATURA, MAX_IMAGENES, MAX_MARCAS, NoPuedeDecidir, FaseExistente,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendario", tags=["calendario-entregas"])

_NO_LLEVA = "Esta tarea no lleva entregas"


# ---------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------

_NO_EXISTE_LA_TAREA = "Esta tarea ya no existe: la borró otra persona."


def _puede_ver(usuario: User, mundo: str, tarea: CalendarioTarea) -> bool:
    """Quién ve las entregas de una tarea: quien tiene el calendario del mundo
    (el permiso y el mundo; su tablero lo ve aunque su alcance sea "No lo
    ve"). Una cuenta externa, además, solo las de SUS tareas. Lo de las
    fechas (el alcance) lo mira `_tarea_y_barra`."""
    if not _puede_ver_el_mundo(usuario, mundo):
        return False
    return not externos.es_externo(usuario) or externos.es_tarea_propia(usuario, tarea)


def puede_entregar(usuario: User, tarea: CalendarioTarea) -> bool:
    """Quién entrega (sube los materiales): la persona asignada (alguien de
    Tienda, o quien carga lo de una agencia de afuera) o, si la tarjeta es de
    una agencia de la plataforma, cualquiera de sus cuentas: la tarjeta es de
    la agencia (16/11/2026)."""
    if tarea.asignado_a_id is not None and tarea.asignado_a_id == usuario.id:
        return True
    return externos.es_externo(usuario) and tarea.para == "agencia" and externos.es_tarea_propia(usuario, tarea)


def puede_ver_revision(
    usuario: User, entrega: CalendarioEntrega, tarea: CalendarioTarea, version: CalendarioVersion | None,
) -> bool:
    """Si `usuario` ve lo que encontró la IA en `version`: los aprobadores de
    la cadena y quien gestiona las tareas, nunca quien entrega (ver
    revision_ia.puede_ver). Además tiene que poder ver la tarea (`_puede_ver`):
    eso lo controla quien llama.

    En una pieza de una agencia de AFUERA, quien la carga es alguien del
    equipo y suele ser quien la aprueba (ver `_autor`): no es quien la hace,
    así que la ve como cualquier aprobador. Antes era la única que decidía y
    la única que no veía lo que encontró la IA (revisión del 16/11/2026)."""
    afuera = getattr(tarea, "para", None) == "fuera"
    if not afuera and puede_entregar(usuario, tarea):
        return False
    return revision_ia.puede_ver(
        usuario.id, es_gestor=_puede_gestionar_tareas(usuario), aprobadores=list(entrega.aprobadores or []),
        responsable_id=None if afuera else tarea.asignado_a_id,
        subida_por_id=_autor(tarea, version.subida_por_id) if version else None,
        activa=settings.IA_REVISION_ACTIVA,
    )


async def _tarea_y_barra(
    db: AsyncSession, tarea_id: str, usuario: User, *, bloquear: bool = False,
) -> tuple[CalendarioTarea, CalendarioBarra]:
    """La tarea y su acción, si la persona las puede ver:

    - Una cuenta externa, solo sus tareas. Una ajena, para ella, no existe:
      el mismo 404, así no se puede ni deducir qué ids hay.
    - Una acción fuera de su alcance del calendario (0070) tampoco existe...
      salvo que la tarea sea una tarjeta suya (ver es_tarjeta_propia): esas
      se ven siempre, porque se trabajan con anticipación."""
    consulta = select(CalendarioTarea).where(CalendarioTarea.id == tarea_id)
    if bloquear:
        consulta = consulta.with_for_update()
    tarea = (await db.execute(consulta)).scalar_one_or_none()
    if tarea is None:
        raise HTTPException(status_code=404, detail=_NO_EXISTE_LA_TAREA)
    if externos.es_externo(usuario) and not externos.es_tarea_propia(usuario, tarea):
        raise HTTPException(status_code=404, detail=_NO_EXISTE_LA_TAREA)
    barra = (await db.execute(select(CalendarioBarra).where(CalendarioBarra.id == tarea.barra_id))).scalar_one_or_none()
    if barra is None:
        raise HTTPException(status_code=404, detail=_NO_EXISTE_LA_TAREA)
    exigir_mundo(usuario, barra.mundo)
    if not alcance.toca(barra.desde, barra.hasta, alcance.ventana_de(usuario)):
        entrega = await db.get(CalendarioEntrega, tarea.id)
        if entrega is None or not reglas.es_tarjeta_propia(usuario, tarea, entrega):
            raise HTTPException(status_code=404, detail=_NO_EXISTE_LA_TAREA)
    return tarea, barra


async def _entrega_bloqueada(db: AsyncSession, tarea_id: str) -> CalendarioEntrega:
    """La entrega, bloqueada hasta el final de la transacción: dos personas
    decidiendo (o entregando) a la vez sobre la misma tarea quedan en fila, y
    la segunda ve lo que hizo la primera.

    Siempre DESPUÉS de bloquear la tarea (`_tarea_y_barra(bloquear=True)`):
    con el mismo orden en todos lados, dos cambios a la vez esperan en vez de
    trabarse uno con otro (deadlock), que Postgres cortaría con un error."""
    entrega = (await db.execute(
        select(CalendarioEntrega).where(CalendarioEntrega.tarea_id == tarea_id).with_for_update()
    )).scalar_one_or_none()
    if entrega is None:
        raise HTTPException(status_code=404, detail=_NO_LLEVA)
    return entrega


async def _nombres(db: AsyncSession, ids) -> dict[int, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {
        u.id: (u.full_name or u.email)
        for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()
    }


def _quien(usuario: User) -> str:
    return usuario.full_name or usuario.email


async def _resumen(db: AsyncSession, tarea_id: str) -> dict | None:
    return (await reglas.resumenes_de_entregas(db, [tarea_id])).get(tarea_id)


def quien_la_hace(tarea: CalendarioTarea, nombres: dict[int, str]) -> dict:
    """Quién hace la tarjeta, para mostrar y para filtrar el tablero:
    {"tipo": 'agencia' | 'fuera' | 'tienda', "nombre": ...}. De una agencia de
    afuera, también quién del equipo carga sus entregas."""
    if tarea.para == "agencia":
        return {"tipo": "agencia", "nombre": tarea.agencia}
    if tarea.para == "fuera":
        return {"tipo": "fuera", "nombre": tarea.agencia, "carga": nombres.get(tarea.asignado_a_id)}
    return {"tipo": "tienda", "nombre": nombres.get(tarea.asignado_a_id)}


# ---------------------------------------------------------------------------
# Configurar
# ---------------------------------------------------------------------------

class FasePedida(BaseModel):
    id: str | None = Field(None, pattern=_ID)
    nombre: str = Field(..., max_length=80)


class EntregaConfig(BaseModel):
    tipoPieza: Literal["cenefa", "mailing", "banner", "redes", "otro"]
    brief: dict | None = None
    aprobadores: list[int] = Field(..., max_length=reglas.MAX_APROBADORES)
    fases: list[FasePedida] = Field(..., max_length=reglas.MAX_FASES)


@router.put("/tareas/{tarea_id}/entregas")
async def configurar_entregas(
    tarea_id: str,
    payload: EntregaConfig,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Que la tarea lleve entregas, o cambiarle el brief, las fases o los
    aprobadores. Lo que ya se trabajó (fases con versiones) no se puede sacar
    ni reordenar: ver `plan_de_fases`."""
    _exigir_gestion_de_tareas(current_user)
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user, bloquear=True)
    try:
        brief = reglas.limpiar_brief(payload.tipoPieza, payload.brief)
        aprobadores = reglas.aprobadores_validos(payload.aprobadores)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # En una pieza de una agencia de AFUERA, quien la carga (la persona
    # asignada) es del equipo y puede aprobarla (ver `_autor`): es el camino
    # por defecto de «Pedir una pieza». Sin esto, «Configurar» y «Más
    # opciones» no dejaban guardar esa tarjeta (revisión del 16/11/2026).
    if tarea.para != "fuera" and tarea.asignado_a_id is not None and tarea.asignado_a_id in aprobadores:
        raise HTTPException(
            status_code=422,
            detail="Quien entrega la pieza no puede estar entre los que la aprueban",
        )
    usuarios = (await db.execute(select(User).where(User.id.in_(aprobadores)))).scalars().all()
    if any(externos.es_externo(u) for u in usuarios):
        # Aprobar es una decisión de la casa: la agencia entrega, no aprueba.
        raise HTTPException(
            status_code=422,
            detail="Una cuenta externa (agencia) no aprueba piezas: elegí a alguien del equipo",
        )
    validos = {u.id for u in usuarios if u.is_active and _puede_ver_el_mundo(u, barra.mundo)}
    if any(a not in validos for a in aprobadores):
        raise HTTPException(
            status_code=422,
            detail=f"Hay aprobadores que no pueden abrir el calendario de {MUNDOS.get(barra.mundo, barra.mundo)}: no verían la pieza",
        )

    entrega = (await db.execute(
        select(CalendarioEntrega).where(CalendarioEntrega.tarea_id == tarea_id).with_for_update()
    )).scalar_one_or_none()
    existentes = (await db.execute(
        select(CalendarioFase).where(CalendarioFase.tarea_id == tarea_id).order_by(CalendarioFase.orden)
    )).scalars().all()
    con_versiones = {
        fid for (fid,) in (await db.execute(
            select(CalendarioVersion.fase_id).where(CalendarioVersion.tarea_id == tarea_id).distinct()
        )).all()
    }
    try:
        plan = reglas.plan_de_fases(
            [FaseExistente(f.id, f.estado, f.id in con_versiones) for f in existentes],
            [(f.id, f.nombre) for f in payload.fases],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    turno_antes = entrega.aprobador_de_turno_id if entrega else None
    if entrega is None:
        entrega = CalendarioEntrega(
            tarea_id=tarea_id, tipo_pieza=payload.tipoPieza, brief=brief, aprobadores=aprobadores,
            momento="produccion", ronda=0, creado_por_id=current_user.id,
        )
        db.add(entrega)
    else:
        entrega.tipo_pieza = payload.tipoPieza
        entrega.brief = brief
        entrega.aprobadores = aprobadores

    por_id = {f.id: f for f in existentes}
    quedan = {i for i, _ in plan if i is not None}
    for f in existentes:
        if f.id not in quedan:
            await db.delete(f)
    for orden, (fid, nombre) in enumerate(plan):
        if fid is None:
            db.add(CalendarioFase(
                id=reglas.nuevo_id("fa"), tarea_id=tarea_id, orden=orden, nombre=nombre, estado="pendiente",
            ))
        else:
            por_id[fid].orden = orden
            por_id[fid].nombre = nombre
    await db.flush()
    await reglas.recalcular(db, entrega, tarea)

    avisados = 0
    # Si con la cadena nueva la versión que espera ya la aprobaron todos los
    # que quedan (se sacó al que faltaba), se aprueba ahora: si no, nadie
    # podría decidirla y la tarea quedaría trabada.
    if entrega.momento == "revision":
        version = await _ultima_version(db, entrega.fase_actual_id)
        if version is not None and reglas.resultado_de_version(
            aprobadores, await reglas.decisiones_de(db, version.id),
        ) == "aprobada":
            fase = await db.get(CalendarioFase, version.fase_id)
            ahora = datetime.now(timezone.utc)
            version.estado, version.decidida_at = "aprobada", ahora
            fase.estado, fase.aprobada_at = "aprobada", ahora
            await db.flush()
            await reglas.recalcular(db, entrega, tarea)
            for uid in await reglas.destinatarios_de_la_tarjeta(db, tarea, barra.mundo):
                if uid != current_user.id and await reglas.avisar(
                    db, uid,
                    f"Se aprobó la ronda {version.ronda} de {fase.nombre} de «{tarea.titulo}»: "
                    "ya la habían aprobado todos los que quedan en la cadena.",
                    reglas.referencia(barra.id, tarea.id, version.id, "aprobada"),
                ):
                    avisados += 1

    # Si con la cadena nueva le toca a otra persona una versión que está
    # esperando, se le avisa (una vez: la referencia lleva la persona).
    if entrega.momento == "revision" and entrega.aprobador_de_turno_id not in (None, turno_antes):
        version = await _ultima_version(db, entrega.fase_actual_id)
        fase = await db.get(CalendarioFase, entrega.fase_actual_id)
        if version is not None and fase is not None:
            nombres = await _nombres(db, [version.subida_por_id])
            if await reglas.avisar(
                db, entrega.aprobador_de_turno_id,
                reglas.mensaje_para_revisar(
                    nombres.get(version.subida_por_id, "La agencia"), version.ronda, fase.nombre,
                    tarea.titulo, barra.nombre,
                ),
                reglas.referencia(barra.id, tarea.id, version.id, f"revisar-{entrega.aprobador_de_turno_id}"),
            ):
                avisados += 1

    resumen = await _resumen(db, tarea_id)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    # A quien ve una parte, sin el contador de todos (ver _rev_para).
    return {"id": tarea_id, "rev": _rev_para(current_user, rev), "entrega": resumen, "avisados": avisados}


@router.delete("/tareas/{tarea_id}/entregas")
async def quitar_entregas(
    tarea_id: str,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Que la tarea vuelva a ser una tarea común. Solo si no se entregó nada:
    si no, se perdería la historia de rondas."""
    _exigir_gestion_de_tareas(current_user)
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user, bloquear=True)
    hay = (await db.execute(
        select(func.count()).select_from(CalendarioVersion).where(CalendarioVersion.tarea_id == tarea_id)
    )).scalar_one()
    if hay:
        raise HTTPException(
            status_code=409,
            detail="Ya hay versiones entregadas: las entregas no se pueden sacar sin perder la historia",
        )
    await db.execute(delete(CalendarioFase).where(CalendarioFase.tarea_id == tarea_id))
    await db.execute(delete(CalendarioEntrega).where(CalendarioEntrega.tarea_id == tarea_id))
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": tarea_id, "rev": _rev_para(current_user, rev), "borrada": True}


async def _ultima_version(db: AsyncSession, fase_id: str | None) -> CalendarioVersion | None:
    if fase_id is None:
        return None
    return (await db.execute(
        select(CalendarioVersion).where(CalendarioVersion.fase_id == fase_id)
        .order_by(CalendarioVersion.ronda.desc()).limit(1)
    )).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Leer
# ---------------------------------------------------------------------------

def _autor(tarea, subida_por_id: int | None) -> int | None:
    """De quién es la versión, para la regla "nadie decide sobre lo que subió".

    En una pieza de una agencia de AFUERA de la plataforma quien la sube es
    alguien del equipo que carga lo que le mandaron por mail o WhatsApp: no
    es su trabajo, y es justo quien tiene que poder aprobarlo o pedir
    cambios. Sin esto, quien pedía un mailing y lo cargaba (el camino por
    defecto del formulario) dejaba la tarjeta trabada en Esperando feedback,
    sin que nadie más se enterara."""
    return None if getattr(tarea, "para", None) == "fuera" else subida_por_id


def _puede_decidir(usuario: User, tarea: CalendarioTarea, entrega: CalendarioEntrega,
                   version: CalendarioVersion | None, decisiones: reglas.Decisiones) -> tuple[bool, bool]:
    """(puede decidir, como respaldo). La misma regla que exige el POST."""
    if version is None or version.estado != "revision":
        return False, False
    try:
        _, _, respaldo = reglas.lugar_para_decidir(
            usuario.id, _puede_gestionar_tareas(usuario), list(entrega.aprobadores or []), decisiones,
            _autor(tarea, version.subida_por_id),
        )
        return True, respaldo
    except NoPuedeDecidir:
        return False, False


@router.get("/tareas/{tarea_id}/entregas")
async def ver_entregas(
    tarea_id: str,
    huella: str | None = None,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Todo lo de las entregas de una tarea. Las imágenes van por id: se piden
    aparte (ver `ver_imagen`).

    A una cuenta externa (solo de sus tareas, ver `_tarea_y_barra`) no le
    viajan las notas internas de las decisiones, y de las personas solo ve con
    nombre (sin mail) a las de su empresa y a quienes aprueban sus entregas."""
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user)
    if not _puede_ver(current_user, barra.mundo, tarea):
        raise HTTPException(status_code=403, detail="No podés ver esta tarea")
    externo = externos.es_externo(current_user)
    entrega = await db.get(CalendarioEntrega, tarea_id)
    if entrega is None:
        raise HTTPException(status_code=404, detail=_NO_LLEVA)
    # La tarjeta abierta pregunta cada tanto si cambió (Ivan, 20/11/2026: "si
    # se completa una tarea o una entrega y tengo abierta la tarjeta, su estado
    # no se actualiza solo"). Si no cambió nada, la respuesta es una línea.
    actual_huella = await _huella_de_la_tarjeta(db, tarea, barra)
    if huella is not None and huella == actual_huella:
        return {"huella": actual_huella, "sinCambios": True}

    fases = (await db.execute(
        select(CalendarioFase).where(CalendarioFase.tarea_id == tarea_id).order_by(CalendarioFase.orden)
    )).scalars().all()
    versiones = (await db.execute(
        select(CalendarioVersion).where(CalendarioVersion.tarea_id == tarea_id)
        .order_by(CalendarioVersion.created_at, CalendarioVersion.ronda)
    )).scalars().all()
    ids_v = [v.id for v in versiones]
    imagenes: dict[str, list[CalendarioVersionImagen]] = {}
    decisiones: dict[str, list[CalendarioDecision]] = {}
    marcas: dict[str, list[CalendarioMarca]] = {}
    zips: dict[str, dict] = {}
    if ids_v:
        for im in (await db.execute(
            select(CalendarioVersionImagen).where(CalendarioVersionImagen.version_id.in_(ids_v))
            .order_by(CalendarioVersionImagen.orden)
        )).scalars():
            imagenes.setdefault(im.version_id, []).append(im)
        # El ZIP original de cada ronda (19/11/2026): nombre, peso y si se
        # guardó, sin traer los bytes (eso es al bajarlo, ver `bajar_zip`).
        for vid, nombre, tamano, fecha, guardado in (await db.execute(
            select(CalendarioVersionZip.version_id, CalendarioVersionZip.nombre, CalendarioVersionZip.tamano,
                   CalendarioVersionZip.created_at, CalendarioVersionZip.datos.isnot(None))
            .where(CalendarioVersionZip.version_id.in_(ids_v))
        )).all():
            zips[vid] = {"nombre": nombre, "tamano": tamano, "guardado": bool(guardado),
                         "fecha": fecha.isoformat() if fecha else None}
        for d in (await db.execute(
            select(CalendarioDecision).where(CalendarioDecision.version_id.in_(ids_v))
            .order_by(CalendarioDecision.id)
        )).scalars():
            decisiones.setdefault(d.version_id, []).append(d)
        for m in (await db.execute(
            select(CalendarioMarca).where(CalendarioMarca.version_id.in_(ids_v))
            .order_by(CalendarioMarca.numero)
        )).scalars():
            marcas.setdefault(m.version_id, []).append(m)
    comentarios = (await db.execute(
        select(CalendarioComentario).where(CalendarioComentario.tarea_id == tarea_id)
        .order_by(CalendarioComentario.created_at, CalendarioComentario.id)
    )).scalars().all()

    personas = [tarea.asignado_a_id, tarea.creado_por_id, *list(entrega.aprobadores or [])]
    personas += [c.autor_id for c in comentarios]
    personas += [v.subida_por_id for v in versiones]
    personas += [f.abierta_por_id for f in fases]
    personas += [d.aprobador_id for ds in decisiones.values() for d in ds]
    personas += [d.decidido_por_id for ds in decisiones.values() for d in ds]
    personas += [m.autor_id for ms in marcas.values() for m in ms]
    if externo:
        nombres = await nombres_para_externo(
            db, current_user, personas, await ids_de_aprobadores_de(db, current_user, barra.mundo),
        )
    else:
        nombres = await _nombres(db, personas)

    def decision_json(d: CalendarioDecision) -> dict:
        out = {
            "aprobador": d.aprobador_id, "decididoPor": d.decidido_por_id, "orden": d.orden,
            "decision": d.decision, "comentario": d.comentario,
            "fecha": d.created_at.isoformat() if d.created_at else None,
        }
        # La nota interna, solo al equipo: a la agencia no le viaja ni la clave.
        if not externo:
            out["notaInterna"] = d.nota_interna
        return out

    def version_json(v: CalendarioVersion) -> dict:
        return {
            "id": v.id, "faseId": v.fase_id, "ronda": v.ronda, "estado": v.estado,
            "subidaPor": v.subida_por_id, "fecha": v.created_at.isoformat() if v.created_at else None,
            "decididaEl": v.decidida_at.isoformat() if v.decidida_at else None,
            "comentario": v.comentario, "link": v.link, "corregidas": list(v.corregidas or []),
            # Las piezas del pedido que no venían en esta ronda y por qué
            # (0087, 21/11/2026): lo ven quien aprueba y la agencia.
            "faltan": list(v.faltan or []), "porQueFaltan": v.por_que_faltan,
            "imagenes": [
                {"id": im.id, "orden": im.orden, "purgada": im.purgada_at is not None}
                for im in imagenes.get(v.id, [])
            ],
            # El ZIP que vino con la ronda, si vino: {nombre, tamano, guardado,
            # fecha}. `guardado` en false: no había lugar (el tope de los ZIP o
            # la base) y no se guardó.
            "zip": zips.get(v.id),
            "decisiones": [decision_json(d) for d in decisiones.get(v.id, [])],
            "marcas": [
                {
                    "id": m.id, "numero": m.numero, "imagenId": m.imagen_id, "x": m.x, "y": m.y,
                    "texto": m.texto, "tipo": m.tipo, "autor": m.autor_id, "corregida": m.corregida,
                    "corregidaEn": m.corregida_en_version_id,
                }
                for m in marcas.get(v.id, [])
            ],
        }

    actual = next((v for v in reversed(versiones) if v.fase_id == entrega.fase_actual_id), None)
    decisiones_actual = [(d.aprobador_id, d.decision) for d in decisiones.get(actual.id, [])] if actual else []
    puede_decidir, como_respaldo = _puede_decidir(current_user, tarea, entrega, actual, decisiones_actual)
    # Archivada sin terminar (cancelada): nadie entrega ni decide hasta que el
    # equipo la saque del archivo (ver `entregar` y `decidir`).
    cancelada = reglas.archivada_sin_terminar(entrega)
    if cancelada:
        puede_decidir, como_respaldo = False, False
    entrega_yo = puede_entregar(current_user, tarea)
    quien = _quien_mueve(current_user, tarea, entrega, puede_decidir)
    columna = reglas.columna_de_entrega(entrega)
    return {
        "huella": actual_huella,
        "tarea": {
            "id": tarea.id, "titulo": tarea.titulo, "descripcion": tarea.descripcion, "estado": tarea.estado,
            "asignadoA": tarea.asignado_a_id, "vence": tarea.vence.isoformat() if tarea.vence else None,
            "creadoPor": tarea.creado_por_id,
            "ancla": tarea.ancla, "anclaDias": tarea.ancla_dias,
            "tipo": tarea.tipo, "opciones": list(tarea.opciones or []), "detalles": dict(tarea.detalles or {}),
            # Lo que se pidió con sus medidas ("Banners: Header (web 1920×416 ·
            # mobile 640×260)"), así quien la hace lo ve sin buscarlo.
            "pedido": tipos_de_tarea.descripcion_del_pedido(tarea.tipo, list(tarea.opciones or []), tarea.detalles),
            # Lo pedido, una pieza por medida ("Header (mobile)" 640×260): con
            # esto la pantalla dice sola, antes de mandar, si falta alguna
            # (21/11/2026, ver tipos_de_tarea.piezas_del_pedido).
            "piezas": tipos_de_tarea.piezas_del_pedido(tarea.tipo, list(tarea.opciones or [])),
            "quienLaHace": quien_la_hace(tarea, nombres),
        },
        "accion": {
            "id": barra.id, "mundo": barra.mundo, "nombre": barra.nombre, "color": barra.color,
            "seccion": barra.seccion, "desde": barra.desde.isoformat(), "hasta": barra.hasta.isoformat(),
        },
        "tipoPieza": entrega.tipo_pieza,
        "brief": entrega.brief or {},
        "aprobadores": list(entrega.aprobadores or []),
        "resumen": await _resumen(db, tarea_id),
        "fases": [
            {
                "id": f.id, "orden": f.orden, "nombre": f.nombre, "estado": f.estado,
                "aprobadaEl": f.aprobada_at.isoformat() if f.aprobada_at else None,
                # Si la abrió una devolución (0072): qué hay que cambiar y quién lo pidió.
                "motivo": f.motivo, "abiertaPor": f.abierta_por_id,
                "versiones": [version_json(v) for v in versiones if v.fase_id == f.id],
            }
            for f in fases
        ],
        "personas": {str(k): v for k, v in nombres.items()},
        "columna": columna,
        "puedo": {
            "entregar": entrega_yo and entrega.momento in ("produccion", "cambios") and not cancelada,
            "decidir": puede_decidir,
            "comoRespaldo": como_respaldo,
            "configurar": _puede_gestionar_tareas(current_user),
            # Devolver una pieza ya aprobada, con un texto: abre otra fase (0072).
            "devolver": not externo and reglas.puede_devolver(
                current_user.id, _puede_gestionar_tareas(current_user), list(entrega.aprobadores or []), entrega.momento,
            ),
            # A qué columnas del tablero la puede llevar (ver reglas.movimiento).
            "mover": reglas.destinos_posibles(
                columna, quien, hay_versiones=bool(versiones), vuelve_a=reglas.columna_al_desarchivar(entrega),
            ),
            # Si le mostramos lo que encontró la IA en la versión en curso (el
            # front la pide aparte, y el servidor lo vuelve a controlar ahí).
            "verRevisionIA": puede_ver_revision(current_user, entrega, tarea, actual),
        },
        "limites": {
            "imagenes": MAX_IMAGENES, "bytesImagen": MAX_BYTES_IMAGEN, "marcas": MAX_MARCAS,
            # El ZIP que se suma a la entrega para que lo revise la IA (19/11/2026).
            "bytesZip": materiales.MAX_BYTES_ZIP,
        },
        # La conversación de la tarjeta, al costado como en Trello (0073).
        "comentarios": [_comentario_json(c, current_user, nombres) for c in comentarios],
    }


def huella_de(*valores) -> str:
    """Un resumen corto de unos valores: cambia si cambia cualquiera. Pura."""
    return hashlib.sha1(repr(valores).encode("utf-8")).hexdigest()[:16]


async def _huella_de_la_tarjeta(db: AsyncSession, tarea, barra) -> str:
    """Lo que, si cambia, cambia lo que se ve en la tarjeta: la tarea (estado,
    nombre, vencimiento, responsable), la acción, la entrega (cada movimiento
    le toca `updated_at`: entregar, decidir, mover, archivar) y cuántas rondas,
    decisiones, marcas y comentarios hay, con la última de cada una. Una sola
    consulta chica: es lo que se pregunta cada pocos segundos mientras la
    tarjeta está abierta, en vez de traerla entera."""
    t = tarea.id
    def cuantos_y_ultimo(modelo, columna):
        return (
            select(func.count()).select_from(modelo).where(modelo.tarea_id == t).scalar_subquery(),
            select(func.max(columna)).where(modelo.tarea_id == t).scalar_subquery(),
        )
    decisiones = (
        select(func.count(CalendarioDecision.id), func.max(CalendarioDecision.id))
        .join(CalendarioVersion, CalendarioVersion.id == CalendarioDecision.version_id)
        .where(CalendarioVersion.tarea_id == t)
    ).subquery()
    fila = (await db.execute(select(
        select(CalendarioEntrega.updated_at).where(CalendarioEntrega.tarea_id == t).scalar_subquery(),
        select(CalendarioEntrega.momento).where(CalendarioEntrega.tarea_id == t).scalar_subquery(),
        *cuantos_y_ultimo(CalendarioVersion, CalendarioVersion.created_at),
        *cuantos_y_ultimo(CalendarioComentario, CalendarioComentario.created_at),
        *cuantos_y_ultimo(CalendarioMarca, CalendarioMarca.created_at),
        *decisiones.c,
    ))).one()
    return huella_de(
        tuple(fila), tarea.estado, tarea.titulo, tarea.vence, tarea.asignado_a_id, tarea.descripcion,
        barra.nombre, barra.desde, barra.hasta, barra.color,
    )


def _comentario_json(c: CalendarioComentario, usuario: User, nombres: dict) -> dict:
    return {
        "id": c.id, "autor": c.autor_id, "autorNombre": nombres.get(c.autor_id) if c.autor_id else None,
        "texto": c.texto, "fecha": c.created_at.isoformat() if c.created_at else None,
        "mio": c.autor_id is not None and c.autor_id == usuario.id,
    }


class ComentarioNuevo(BaseModel):
    id: str = Field(..., pattern=_ID)
    texto: str = Field(..., max_length=2000)

    @field_validator("texto")
    @classmethod
    def _con_texto(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Escribí el comentario")
        return v


@router.post("/tareas/{tarea_id}/comentarios", status_code=201)
@limiter.limit("30/minute")
async def comentar(
    tarea_id: str,
    payload: ComentarioNuevo,
    request: Request,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Un comentario en la tarjeta (17/11/2026: "como tiene Trello en un
    costado, para poder explicar cambios"). Lo escribe cualquiera que ve la
    tarjeta: el equipo y el tablero al que va. Le llega a la campanita de los
    que la siguen: quien la hace (todo el tablero, si es de una agencia),
    quien la pidió, quienes la aprueban y quien lleva la tarea de la que
    cuelga. Nunca a quien comentó."""
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user)
    if not _puede_ver(current_user, barra.mundo, tarea):
        raise HTTPException(status_code=403, detail="No podés ver esta tarea")
    entrega = await db.get(CalendarioEntrega, tarea.id)
    if entrega is None:
        raise HTTPException(status_code=404, detail=_NO_LLEVA)
    ya = await db.get(CalendarioComentario, payload.id)
    if ya is not None:
        if ya.tarea_id != tarea.id:
            raise HTTPException(status_code=409, detail="Ese comentario ya existe en otra tarjeta")
        return {"id": ya.id, "comentario": _comentario_json(ya, current_user, await _nombres(db, [ya.autor_id])), "avisados": 0}
    comentario = CalendarioComentario(id=payload.id, tarea_id=tarea.id, autor_id=current_user.id, texto=payload.texto)
    db.add(comentario)
    await db.flush()
    await db.refresh(comentario)

    siguen = list(await reglas.destinatarios_de_la_tarjeta(db, tarea, barra.mundo))
    siguen += [tarea.creado_por_id, *list(entrega.aprobadores or [])]
    if tarea.parent_id:
        madre = await db.get(CalendarioTarea, tarea.parent_id)
        if madre is not None:
            siguen.append(madre.asignado_a_id)
    mensaje = reglas.mensaje_de_comentario(current_user.full_name, tarea.titulo, payload.texto)
    referencia = reglas.referencia(barra.id, tarea.id, comentario.id, "comentario")
    avisados = 0
    for uid in dict.fromkeys(u for u in siguen if u is not None and u != current_user.id):
        if await reglas.avisar(db, uid, mensaje, referencia):
            avisados += 1
    await db.commit()
    nombres = await _nombres(db, [current_user.id])
    return {"id": comentario.id, "comentario": _comentario_json(comentario, current_user, nombres), "avisados": avisados}


def _exigir_ver_archivos(
    usuario: User, tarea: CalendarioTarea, barra: CalendarioBarra, entrega: CalendarioEntrega | None, *,
    no_existe: str, no_podes: str,
) -> None:
    """Quién ve los archivos de una versión (sus imágenes y su ZIP original):
    lo mismo que la tarea (`_tarea_y_barra`). Una cuenta externa, solo los de
    sus tarjetas; nadie, los de una acción fuera de su alcance que no sea una
    tarjeta suya. Lo demás, el mismo 404 (`no_existe`) que algo que no
    existe; sin el calendario del mundo, 403 (`no_podes`)."""
    propia = entrega is not None and reglas.es_tarjeta_propia(usuario, tarea, entrega)
    if externos.es_externo(usuario) and not propia:
        raise HTTPException(status_code=404, detail=no_existe)
    if not propia and not alcance.toca(barra.desde, barra.hasta, alcance.ventana_de(usuario)):
        raise HTTPException(status_code=404, detail=no_existe)
    exigir_mundo(usuario, barra.mundo)
    if not _puede_ver(usuario, barra.mundo, tarea):
        raise HTTPException(status_code=403, detail=no_podes)


def _de_la_version(columnas: tuple, tabla, *, por, valor):
    """La consulta de un archivo de una versión con su tarea, su acción y su
    entrega (para `_exigir_ver_archivos`), en una sola ida a la base."""
    return (
        select(*columnas, CalendarioTarea, CalendarioBarra, CalendarioEntrega)
        .select_from(tabla)
        .join(CalendarioVersion, CalendarioVersion.id == tabla.version_id)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioVersion.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .join(CalendarioEntrega, CalendarioEntrega.tarea_id == CalendarioTarea.id, isouter=True)
        .where(por == valor)
    )


@router.get("/entregas/imagenes/{imagen_id}")
async def ver_imagen(
    imagen_id: str,
    tam: Literal["mini", "grande"] = "grande",
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Una imagen de una versión. Viaja con la sesión (el front la pide por
    axios y arma una URL local), no con un link público: una pieza sin
    lanzar no puede quedar abierta a quien tenga el link."""
    fila = (await db.execute(_de_la_version(
        (CalendarioVersionImagen.tipo_mime, CalendarioVersionImagen.tipo_mime_miniatura),
        CalendarioVersionImagen, por=CalendarioVersionImagen.id, valor=imagen_id,
    ))).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Esa imagen ya no existe")
    tipo, tipo_mini, tarea, barra, entrega = fila
    _exigir_ver_archivos(current_user, tarea, barra, entrega,
                         no_existe="Esa imagen ya no existe", no_podes="No podés ver esta imagen")
    columna = CalendarioVersionImagen.miniatura if tam == "mini" else CalendarioVersionImagen.datos
    datos = (await db.execute(select(columna).where(CalendarioVersionImagen.id == imagen_id))).scalar_one_or_none()
    if datos is None:
        # Venció: los bytes se borran a los 30 días de terminada la acción
        # (120 la versión final). La versión, sus marcas y decisiones quedan.
        raise HTTPException(
            status_code=410,
            detail="Esta imagen ya se borró: se guardan hasta un tiempo después de terminada la acción.",
        )
    return Response(
        content=datos,
        media_type=tipo_mini if tam == "mini" else tipo,
        headers={
            # Una imagen no cambia nunca (cada versión es nueva): el navegador
            # la guarda y no la vuelve a pedir.
            "Cache-Control": "private, max-age=31536000, immutable",
            # Ya viene comprimida: que el GZip de la app no la vuelva a comprimir.
            "Content-Encoding": "identity",
        },
    )


def _adjunto(nombre: str) -> str:
    """El Content-Disposition para bajar un archivo con su nombre, también
    con tildes y ñ (filename* va en UTF-8; filename, para los viejos)."""
    plano = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in nombre) or "archivo.zip"
    return f"attachment; filename=\"{plano}\"; filename*=UTF-8''{quote(nombre, safe='')}"


# El ZIP se manda de a partes de 1 MB (revisión del 19/11/2026): leerlo entero
# para bajarlo eran unos 80 MB de memoria por un ZIP de 40, retenidos mientras
# viajaba, y nada frenaba varias bajadas a la vez en los 512 MB del servidor.
_PARTE_DEL_ZIP = 1024 * 1024


async def _partes_del_zip(version_id: str, largo: int):
    """Los `largo` bytes del ZIP de una ronda, de a `_PARTE_DEL_ZIP`, cada
    parte con un `substring` en la base: en memoria hay una parte por vez.

    Corre mientras se manda la respuesta, así que lee con su propia sesión y
    la cierra al terminar: la del pedido (get_db) no se usa acá, y los
    permisos ya los miró `bajar_zip` con ella. Después de cada parte termina
    la transacción (solo leyó) y la conexión vuelve al pool: una bajada lenta
    no deja una conexión de la base tomada mientras el navegador recibe."""
    async with AsyncSessionLocal() as db:
        enviados = 0
        while enviados < largo:
            parte = (await db.execute(
                select(func.substring(CalendarioVersionZip.datos, enviados + 1, _PARTE_DEL_ZIP, type_=LargeBinary))
                .where(CalendarioVersionZip.version_id == version_id)
            )).scalar_one_or_none()
            await db.commit()
            if not parte:
                # Se borró mientras bajaba (alguien borró la tarea): se corta
                # acá, y el navegador da la bajada por fallida porque no llegó
                # todo lo que anunció el Content-Length.
                logger.warning("entregas: el ZIP de la versión %s se borró mientras se bajaba (%d de %d bytes)",
                               version_id, enviados, largo)
                return
            enviados += len(parte)
            yield parte


@router.get("/versiones/{version_id}/zip")
@limiter.limit("10/minute")
async def bajar_zip(
    request: Request,
    version_id: str,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """El ZIP original de una ronda, tal cual lo mandó la agencia (19/11/2026,
    Ivan: "cuando lo subís deberías de subir la carpeta comprimida"). Lo bajan
    el equipo y la agencia con las mismas reglas que las imágenes de esa
    versión (`_exigir_ver_archivos`), y viaja con la sesión, como ellas: una
    pieza sin lanzar no queda abierta a quien tenga un link.

    Con un tope por persona y por minuto: un ZIP pesa hasta 40 MB y cada
    bajada sale de la base (el plan gratis tiene un tope de transferencia por
    mes); una pantalla que reintentara sola no tiene que poder gastarlo.

    Se manda de a partes (`_partes_del_zip`), con lo que pesa en el
    Content-Length: el navegador muestra el avance y sabe si llegó entero."""
    # Lo que pesa lo guardado (NULL si no se guardó): es lo que se manda.
    fila = (await db.execute(_de_la_version(
        (CalendarioVersionZip.nombre, func.octet_length(CalendarioVersionZip.datos)),
        CalendarioVersionZip, por=CalendarioVersionZip.version_id, valor=version_id,
    ))).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Esa ronda no tiene un ZIP")
    nombre, largo, tarea, barra, entrega = fila
    _exigir_ver_archivos(current_user, tarea, barra, entrega,
                         no_existe="Esa ronda no tiene un ZIP", no_podes="No podés ver esta ronda")
    if largo is None:
        raise HTTPException(
            status_code=404,
            detail="El ZIP de esta ronda no se guardó porque no había lugar en la base: pedile el link a quien la hace.",
        )
    # La sesión del pedido ya no hace falta: se suelta su conexión antes de
    # mandar (FastAPI la cierra recién cuando termina la bajada).
    await db.close()
    return StreamingResponse(
        _partes_del_zip(version_id, largo),
        media_type="application/zip",
        headers={
            "Content-Disposition": _adjunto(nombre),
            "Content-Length": str(largo),
            # El ZIP de una ronda no cambia nunca (cada ronda es nueva).
            "Cache-Control": "private, max-age=31536000, immutable",
            # Ya viene comprimido: que el GZip de la app no lo vuelva a comprimir.
            "Content-Encoding": "identity",
        },
    )


# ---------------------------------------------------------------------------
# Entregar
# ---------------------------------------------------------------------------

async def _hay_lugar_para_el_zip(db: AsyncSession, peso: int, bytes_imagenes: int) -> bool:
    """Si el ZIP original de una ronda (`peso` bytes) se puede guardar: entra
    en el tope propio de los ZIP (ZIP_TOPE_MB, contando lo que ya ocupan los
    guardados con sus bytes) y además en la base, junto con las imágenes de
    la ronda (`hay_lugar` de siempre). Revisión del 19/11/2026: antes era
    una reserva debajo del tope de la base, que dejaba a los ZIP llegar a
    350 de los 400 MB; ver ZIP_TOPE_MB en app/core/config.py. Si no hay
    lugar, deja un error en el log para quien administra: no se borra nada.

    Se llama adentro de _UN_ZIP_POR_VEZ, justo antes de guardar (ver
    _guardar_el_zip): a los guardados se les suman los que otra entrega ya
    mandó y todavía no confirmó (`_zips_sin_confirmar`)."""
    guardados = (await db.execute(
        select(func.coalesce(func.sum(CalendarioVersionZip.tamano), 0))
        .where(CalendarioVersionZip.datos.isnot(None))
    )).scalar_one() + _zips_sin_confirmar
    if not entra(guardados, peso, settings.ZIP_TOPE_MB):
        logger.error(
            "entregas: los ZIP guardados ocupan %.1f MB y su tope es %d MB (ZIP_TOPE_MB): el de %.1f MB "
            "no se guardó (la entrega sí). Para guardar más ZIP hay que subir el tope; no se borra nada.",
            guardados / MB, settings.ZIP_TOPE_MB, peso / MB,
        )
        return False
    return await hay_lugar(db, bytes_imagenes + peso)


# Guardar el ZIP de una entrega, de a uno en todo el proceso (revisión del
# 19/11/2026): mandarle a la base un ZIP de 40 MB arma copias del pedido en
# memoria (el pico sube unos 120 MB además del ZIP), y dos entregas grandes a
# la vez no entran en los 512 MB del servidor. Adentro solo se mira si hay
# lugar (dos lecturas) y se manda el ZIP: no se espera ningún candado de la
# base, así que no se traba con otra entrega.
_UN_ZIP_POR_VEZ = asyncio.Semaphore(1)

# Los bytes de los ZIP que ya se mandaron a la base y todavía no se
# confirmaron (commit). Otra entrega no los ve en la suma de los guardados
# hasta el commit, así que el control del tope los suma de acá. Sin esto,
# mirar el tope adentro del candado no alcanzaba: la segunda entrega lo
# miraba cuando la primera ya había guardado su ZIP pero no lo había
# confirmado, y entraban las dos (revisión del 19/11/2026). Es por proceso,
# como el candado: el servidor corre en uno solo.
_zips_sin_confirmar = 0


@asynccontextmanager
async def _guardar_el_zip(db: AsyncSession, version_id: str, nombre: str | None, datos: bytes | None,
                          bytes_imagenes: int):
    """El ZIP original de una ronda: se mira si hay lugar y se guarda, juntos
    y de a uno en todo el proceso (_UN_ZIP_POR_VEZ). Antes el control del
    tope iba afuera del candado: dos entregas con un ZIP grande casi a la vez
    lo pasaban las dos antes de que ninguna guardara, y dejaban el tope
    pasado por hasta 40 MB (revisión del 19/11/2026, arreglado el
    21/11/2026).

    Si no hay lugar (el tope propio de los ZIP o la base), queda la fila sin
    los bytes, para que la ficha diga que no se guardó; la entrega sigue
    igual (no es un 507) y nada se borra. Da si se guardó.

    Lo que guarda cuenta en `_zips_sin_confirmar` hasta que termina el
    bloque: adentro va el commit de la entrega."""
    global _zips_sin_confirmar
    if datos is None:
        yield False
        return
    # Lo pendiente de la entrega se manda antes: adentro, solo esto.
    await db.flush()
    async with _UN_ZIP_POR_VEZ:
        guardado = await _hay_lugar_para_el_zip(db, len(datos), bytes_imagenes)
        db.add(CalendarioVersionZip(
            version_id=version_id, nombre=nombre, tamano=len(datos), datos=datos if guardado else None,
        ))
        await db.flush()
        reservado = len(datos) if guardado else 0
        _zips_sin_confirmar += reservado
    try:
        yield guardado
    finally:
        _zips_sin_confirmar -= reservado


async def _leer(archivo: UploadFile, maximo: int, que: str) -> tuple[bytes, str]:
    # Se lee uno más que el máximo: alcanza para saber que se pasó sin leer
    # un archivo gigante entero.
    datos = await archivo.read(maximo + 1)
    try:
        return datos, reglas.validar_imagen(datos, maximo=maximo, que=que)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/tareas/{tarea_id}/control-previo")
@limiter.limit("10/minute")
async def control_previo(
    request: Request,
    tarea_id: str,
    comentario: str = Form("", max_length=5000),
    imagenes: list[UploadFile] | None = File(None),
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Antes de entregar, la IA mira si se hicieron los cambios pedidos (Ivan,
    20/11/2026: "que a la agencia, cuando va a subir los archivos, la IA le
    diga 'che, pará, acá faltan estas cositas de los cambios'") o, en la
    primera ronda de la fase, si la pieza cumple el pedido inicial (Ivan,
    21/11/2026: "La primera entrega debería compararse contra lo pedido
    inicialmente").

    Desde el 24/11/2026 le muestra también lo que encontró en la pieza, lo
    mismo que vería quien aprueba (Ivan: "la IA sigue encontrando cosas del
    lado de Tienda que no encuentra del lado de la agencia"), y mira aunque
    no haya nada pedido.

    Recibe las mismas imágenes que se van a entregar (sin las miniaturas: no
    se guarda nada de ellas) y no crea ninguna versión. Contesta
    {estado, cambios, controlId, inicial, observaciones}: 'sin-pedido' si no
    hay imágenes o si ahora no se podría entregar (eso lo dice la entrega),
    'listo' con cada marca o punto pedido [{numero, texto, veredicto, nota}]
    (vacío si no se pidió nada) y lo que encontró en las imágenes [{id, tipo,
    texto, gravedad, imagen, x, y}], o 'no-disponible' (sin IA, tope, falla,
    demora): la pantalla manda igual. `inicial`: si lo controlado es el
    pedido inicial. Nunca traba la entrega. Solo quien la hace
    (`puede_entregar`). Ver revision_ia.controlar_antes_de_entregar."""
    imagenes = imagenes or []
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user)
    if not puede_entregar(current_user, tarea):
        raise HTTPException(status_code=403, detail="Entrega solo quien hace la tarea")
    sin_pedido = revision_ia.ResultadoDelControl("sin-pedido", []).para_la_agencia()
    entrega = await db.get(CalendarioEntrega, tarea_id)
    if entrega is None or entrega.fase_actual_id is None or reglas.archivada_sin_terminar(entrega):
        return sin_pedido
    ultima = await _ultima_version(db, entrega.fase_actual_id)
    if ultima is not None and ultima.estado == "revision":
        return sin_pedido
    if not imagenes:
        return sin_pedido
    if len(imagenes) > MAX_IMAGENES:
        raise HTTPException(status_code=422, detail=f"Son demasiadas imágenes: hasta {MAX_IMAGENES} por ronda")
    leidas = []
    for i, grande in enumerate(imagenes, 1):
        leidas.append(await _leer(grande, MAX_BYTES_IMAGEN, f"La imagen {i}" if len(imagenes) > 1 else "La imagen"))
    fase = await db.get(CalendarioFase, entrega.fase_actual_id)
    usuario_id = current_user.id
    resultado = await revision_ia.controlar_antes_de_entregar(
        db, tarea=tarea, entrega=entrega, barra=barra, fase=fase, ronda=(ultima.ronda if ultima else 0) + 1,
        usuario_id=usuario_id, imagenes=leidas, comentario=comentario,
    )
    return resultado.para_la_agencia()


@router.post("/tareas/{tarea_id}/versiones", status_code=201)
@limiter.limit("20/minute")
async def entregar(
    request: Request,
    background_tasks: BackgroundTasks,
    tarea_id: str,
    versionId: str = Form(..., pattern=_ID),
    comentario: str = Form("", max_length=5000),
    link: str = Form("", max_length=1000),
    corregidas: str = Form("[]", max_length=20_000),
    imagenes: list[UploadFile] | None = File(None),
    miniaturas: list[UploadFile] | None = File(None),
    archivo_zip: UploadFile | None = File(None, alias="zip"),
    zipYaSubidas: str = Form("[]", max_length=2000),
    faltan: str = Form("[]", max_length=20_000),
    porQueFaltan: str = Form("", max_length=5000),
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Entrega una ronda de la fase en curso: la manda a "Esperando feedback".
    Solo quien la hace (`puede_entregar`). Los materiales son imágenes y/o un
    link al original (WeTransfer, Smash: 16/11/2026, "imágenes como hoy y/o un
    link"). Va todo en un pedido (las imágenes también): o queda la versión
    entera, o no queda nada.

    Desde el 19/11/2026 puede venir además un ZIP (`zip`, hasta 40 MB) con
    las piezas adentro. Se mira acá que sea un ZIP sano y:

    - Se guarda tal cual, como el original de la ronda (calendario_version_
      zips), en la misma transacción. Si no hay lugar (el tope propio de los
      ZIP, ZIP_TOPE_MB, o la base: `_hay_lugar_para_el_zip`), la entrega se
      hace igual sin guardarlo y queda anotado (la fila sin los bytes): la
      ficha lo dice. Nunca se borra nada para hacerle lugar. El control y el
      guardado van juntos y de a uno (`_guardar_el_zip`, 21/11/2026): dos
      entregas a la vez no pasan el tope.
    - Las imágenes de adentro las saca el navegador y las sube como imágenes
      de la ronda. `zipYaSubidas` dice cuáles (su lugar en el índice del
      ZIP), junto con las que la persona sacó de la ronda a propósito: esas
      no vuelven. Si quedan lugares de imagen libres, el servidor los llena
      con lo demás del ZIP, en su orden: imágenes que el navegador no pudo
      abrir y páginas de los PDF (materiales.imagenes_para_la_ronda). Así un
      ZIP solo alcanza para entregar si de él sale al menos una imagen.
    - La IA lo revisa en segundo plano, sin mirar dos veces lo que ya es
      imagen de la ronda.

    Desde el 21/11/2026 pueden venir `faltan` (JSON: los nombres de las
    piezas del pedido que la pantalla vio que no venían, por las medidas) y
    `porQueFaltan` (lo que escribió quien entrega: "Es el KV, para aprobarlo
    antes"). Se guardan con la ronda tal cual, con sus topes
    (reglas.faltan_validas): no traban la entrega."""
    imagenes, miniaturas = imagenes or [], miniaturas or []
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user, bloquear=True)
    entrega = await _entrega_bloqueada(db, tarea_id)
    if not puede_entregar(current_user, tarea):
        raise HTTPException(status_code=403, detail="Entrega solo quien hace la tarea")

    existente = await db.get(CalendarioVersion, versionId)
    if existente is not None:
        if existente.tarea_id != tarea_id:
            raise HTTPException(status_code=409, detail="Esa versión es de otra tarea")
        # Un reintento de la misma subida: ya quedó.
        return {"id": versionId, "rev": None, "ronda": existente.ronda, "yaExistia": True,
                "entrega": await _resumen(db, tarea_id)}
    if entrega.fase_actual_id is None:
        raise HTTPException(status_code=409, detail="Todas las fases ya están aprobadas: no hay nada más para entregar")
    if reglas.archivada_sin_terminar(entrega):
        # Se canceló (16/11/2026): entregarla la reabría sola, sin que el
        # equipo se enterara de por qué volvía.
        raise HTTPException(
            status_code=409,
            detail="Esta tarjeta está archivada: para entregarla, el equipo tiene que sacarla del archivo",
        )
    fase = await db.get(CalendarioFase, entrega.fase_actual_id)
    ultima = await _ultima_version(db, entrega.fase_actual_id)
    if ultima is not None and ultima.estado == "revision":
        raise HTTPException(
            status_code=409,
            detail=f"La ronda {ultima.ronda} de {fase.nombre} todavía está en revisión: esperá a que la decidan",
        )

    try:
        ya_subidas = json.loads(zipYaSubidas or "[]")
        if not isinstance(ya_subidas, list) or not all(type(i) is int and 0 <= i < 100_000 for i in ya_subidas):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="La lista de imágenes sacadas del ZIP no tiene la forma esperada")
    zip_saltar = frozenset(ya_subidas)
    zip_datos, zip_nombre, inventario = None, None, None
    if archivo_zip is not None and archivo_zip.filename:
        # Uno más que el máximo: alcanza para saber que se pasó.
        zip_datos = await archivo_zip.read(materiales.MAX_BYTES_ZIP + 1)
        zip_nombre = archivo_zip.filename.replace("\\", "/").rsplit("/", 1)[-1][:120] or "archivo.zip"
        if not zip_datos:
            zip_datos = None
        else:
            try:
                inventario = materiales.inspeccionar_zip(zip_datos)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            if not any(e.clase != "otro" for e in inventario):
                raise HTTPException(
                    status_code=422,
                    detail="El ZIP no trae nada para revisar: adentro tiene que haber imágenes (JPG, PNG, WebP) o PDF",
                )
    if not imagenes and not (link or "").strip() and zip_datos is None:
        raise HTTPException(status_code=422, detail="Subí al menos una imagen o pegá el link al original")
    if len(imagenes) > MAX_IMAGENES:
        raise HTTPException(status_code=422, detail=f"Son demasiadas imágenes: hasta {MAX_IMAGENES} por ronda")
    if len(miniaturas) != len(imagenes):
        raise HTTPException(status_code=422, detail="Falta la miniatura de alguna imagen: volvé a elegirlas")
    try:
        link_ok = reglas.link_valido(link)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        pedidas = json.loads(corregidas or "[]")
    except json.JSONDecodeError:
        pedidas = None
    if not isinstance(pedidas, list) or not all(isinstance(x, str) for x in pedidas):
        raise HTTPException(status_code=422, detail="La lista de marcas corregidas no tiene la forma esperada")
    try:
        piezas_que_faltan = reglas.faltan_validas(faltan)
        por_que_faltan = reglas.por_que_faltan_valido(porQueFaltan, piezas_que_faltan)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    leidas = []
    for i, (grande, mini) in enumerate(zip(imagenes, miniaturas), 1):
        cual = f"La imagen {i}" if len(imagenes) > 1 else "La imagen"
        datos, tipo = await _leer(grande, MAX_BYTES_IMAGEN, cual)
        datos_mini, tipo_mini = await _leer(mini, MAX_BYTES_MINIATURA, f"La miniatura de {cual.lower()}")
        leidas.append((datos, tipo, datos_mini, tipo_mini))

    # Lo del ZIP que el navegador no pudo mostrar, a los lugares de imagen que
    # quedan (19/11/2026: un ZIP con solo el PDF del folleto se rechazaba, y
    # Ivan no entendía por qué; no tenía que pasar). Pesado (descomprimir,
    # dibujar páginas): en un hilo, de a una cosa.
    del_zip = materiales.SacadoDelZip()
    if zip_datos is not None and len(leidas) < MAX_IMAGENES:
        try:
            del_zip = await asyncio.to_thread(
                materiales.imagenes_para_la_ronda, zip_datos, lugar=MAX_IMAGENES - len(leidas), saltar=zip_saltar,
            )
        except Exception as exc:  # el ZIP ya se miró arriba: esto no debería pasar
            logger.warning("entregas: no se pudo sacar nada del ZIP «%s» — %s: %s", zip_nombre, type(exc).__name__, exc)
        leidas += [(im.datos, "image/jpeg", im.miniatura, "image/jpeg") for im in del_zip.imagenes]
    if not leidas and not link_ok:
        # Solo vino un ZIP, y de adentro no salió nada para ver.
        porque = "; ".join(del_zip.no_se_pudo[:3])
        raise HTTPException(
            status_code=422,
            detail="Del ZIP no salió ninguna imagen para mostrar" + (f" ({porque})" if porque else "")
            + ": subí una imagen o pegá el link al original, así quien aprueba ve la pieza",
        )
    # El freno general: con la base casi llena no se guarda ninguna imagen
    # (507, con el mensaje para la persona, y un error en el log). Solo si hay
    # imágenes: una entrega con un link solo no ocupa lugar, y con la base
    # llena recibía un 507 que decía «La imagen no se guardó» (16/11/2026).
    bytes_imagenes = sum(len(g) + len(m) for g, _, m, _ in leidas)
    if leidas:
        await exigir_lugar(db, bytes_imagenes)
    # El ZIP original se guarda al final, solo si entra en el tope de los ZIP
    # y en la base: ver _guardar_el_zip.

    ronda = (ultima.ronda if ultima else 0) + 1
    # Solo cuentan las marcas de ESTA tarea que estaban sin corregir: lo
    # demás (una que ya tildó otro, un id viejo) se ignora.
    marcas = (await db.execute(
        select(CalendarioMarca).where(
            CalendarioMarca.tarea_id == tarea_id, CalendarioMarca.id.in_(set(pedidas)),
            CalendarioMarca.corregida.is_(False),
        )
    )).scalars().all() if pedidas else []
    ahora = datetime.now(timezone.utc)
    db.add(CalendarioVersion(
        id=versionId, fase_id=fase.id, tarea_id=tarea_id, ronda=ronda, subida_por_id=current_user.id,
        comentario=(comentario or "").strip() or None, link=link_ok,
        corregidas=[m.id for m in marcas], estado="revision",
        faltan=piezas_que_faltan, por_que_faltan=por_que_faltan,
    ))
    # La versión tiene que existir antes que sus imágenes (FK): se manda ya.
    await db.flush()
    ids_de_imagenes: list[str] = []
    for orden, (datos, tipo, datos_mini, tipo_mini) in enumerate(leidas):
        ids_de_imagenes.append(reglas.nuevo_id("im"))
        db.add(CalendarioVersionImagen(
            id=ids_de_imagenes[-1], version_id=versionId, orden=orden, tipo_mime=tipo, datos=datos,
            tipo_mime_miniatura=tipo_mini, miniatura=datos_mini, tamano=len(datos),
        ))
    for m in marcas:
        m.corregida = True
        m.corregida_en_version_id = versionId
        m.corregida_at = ahora
    await db.flush()
    await reglas.recalcular(db, entrega, tarea)
    # Si la IA ya miró exactamente estas imágenes en el control previo (Ivan,
    # 20/11/2026), la revisión de la versión sale de ahí y no se le paga dos
    # veces; desde el 21/11/2026, también en la primera ronda (el control del
    # pedido inicial). Con link o ZIP no: eso lo mira al entregar.
    del_control = bool(leidas) and await revision_ia.reusar_control(
        db, tarea_id=tarea_id, usuario_id=current_user.id, fase_id=fase.id, ronda=ronda,
        huella=revision_ia.huella_de([g for g, _, _, _ in leidas]), con_link=bool(link_ok),
        con_zip=zip_datos is not None, version_id=versionId, ids_de_imagenes=ids_de_imagenes,
    )

    # Al aprobador que le toca; sin cadena, a quien creó la tarea (que la
    # puede decidir como respaldo si tiene calendario.tareas).
    destino = entrega.aprobador_de_turno_id or tarea.creado_por_id
    avisados = 0
    # Si a quien le tocaría es quien acaba de entregar y no puede decidir
    # sobre lo suyo (una pieza de Tienda que se pidió a sí mismo), se les
    # avisa a quienes pueden aprobarla como respaldo: si no, quedaba en
    # Esperando feedback sin que nadie se enterara. En una pieza de una
    # agencia de afuera no hace falta: quien la carga la decide (ver _autor).
    if destino == current_user.id and _autor(tarea, current_user.id) is not None:
        destinos = await reglas.gestores_del_mundo(db, barra.mundo, menos=current_user.id)
    else:
        destinos = [destino] if destino != current_user.id else []
    for uid in destinos:
        if await reglas.avisar(
            db, uid,
            reglas.mensaje_para_revisar(_quien(current_user), ronda, fase.nombre, tarea.titulo, barra.nombre),
            reglas.referencia(barra.id, tarea.id, versionId, f"revisar-{uid}"),
        ):
            avisados += 1
    resumen = await _resumen(db, tarea_id)
    # El ZIP original, al final y antes de la revisión del calendario (su
    # fila es una sola para todos: no se la tiene tomada mientras se espera
    # el turno del ZIP). Lo que guarda cuenta para el tope hasta el commit.
    async with _guardar_el_zip(db, versionId, zip_nombre, zip_datos, bytes_imagenes) as zip_guardado:
        rev = await _nueva_revision(db, barra.mundo)
        await db.commit()
    # La IA la revisa en segundo plano: arranca después de contestar (y ya
    # con la versión guardada, por el commit de arriba), abre su propia
    # sesión y no levanta nunca. Si falla, la entrega queda igual. El ZIP va
    # en memoria y el link lo baja ella (19/11/2026): la entrega no espera la
    # descarga. Lo que ya es imagen de la ronda no lo mira dos veces; y si del
    # ZIP no le queda ninguna imagen ni PDF por mirar (todo pasó a la ronda),
    # no se le pasa, como hacía antes la pantalla: así no queda ocupando
    # memoria mientras espera su turno.
    saltar_ia = zip_saltar | frozenset(del_zip.entradas)
    queda_para_la_ia = inventario is not None and any(
        e.clase != "otro" and e.indice not in saltar_ia for e in inventario
    )
    if revision_ia.activa() and not del_control and (leidas or queda_para_la_ia or link_ok):
        background_tasks.add_task(
            revision_ia.revisar_version, versionId,
            zip_datos=zip_datos if queda_para_la_ia else None, zip_nombre=zip_nombre if queda_para_la_ia else None,
            zip_saltar=saltar_ia, zip_paginas=dict(del_zip.paginas),
        )
    return {
        "id": versionId, "rev": _rev_para(current_user, rev), "ronda": ronda, "entrega": resumen, "avisados": avisados,
        # El ZIP: si se guardó (si no, la pantalla avisa), cuántas imágenes de
        # la ronda salieron de él en el servidor, qué más se le va a mirar y
        # qué no es imagen ni PDF, para que quien entrega lo vea en el acto.
        "zip": None if inventario is None else {
            "nombre": zip_nombre,
            "tamano": len(zip_datos),
            "guardado": zip_guardado,
            "sumadas": len(del_zip.imagenes),
            "archivos": [e.nombre for e in inventario if e.clase != "otro" and e.indice not in saltar_ia],
            "ignorados": [e.nombre for e in inventario if e.clase == "otro"],
        },
    }


# ---------------------------------------------------------------------------
# Decidir
# ---------------------------------------------------------------------------

class MarcaNueva(BaseModel):
    imagenId: str = Field(..., pattern=_ID)
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    texto: str = Field(..., min_length=1, max_length=1000)
    # Si el aprobador la armó desde una observación de la IA ("Hacer marca"):
    # la observación queda como convertida. La marca es una marca más, del
    # aprobador; para la agencia no hay diferencia.
    observacionIA: str | None = Field(None, pattern=_ID)

    @field_validator("texto")
    @classmethod
    def _sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Cada marca necesita un texto: qué hay que cambiar")
        return v


class DecisionNueva(BaseModel):
    # 'aprobada' o 'cambios' (reglas.DECISIONES). Es un texto y no un Literal
    # a propósito: así el 422 de «aprobado con cambios» (que ya no existe,
    # 19/11/2026) lleva un mensaje para la persona y no el genérico de
    # pydantic. Lo controla reglas.validar_decision al decidir.
    decision: str = Field(..., max_length=40)
    # Lo que lee la agencia, con las marcas.
    comentario: str | None = Field(None, max_length=5000)
    marcas: list[MarcaNueva] = Field(default_factory=list, max_length=MAX_MARCAS)
    # Solo para el equipo: la agencia nunca la ve (0069).
    notaInterna: str | None = Field(None, max_length=5000)


@router.post("/versiones/{version_id}/decision")
async def decidir(
    version_id: str,
    payload: DecisionNueva,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    try:
        decision = reglas.validar_decision(payload.decision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    version = await db.get(CalendarioVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Esa versión ya no existe")
    if externos.es_externo(current_user):
        # La agencia entrega; aprobar o pedir cambios es de la casa. No se la
        # puede poner en la cadena (ver configurar_entregas) y acá tampoco
        # decide como respaldo.
        raise HTTPException(status_code=403, detail="Una cuenta externa no aprueba ni pide cambios")
    tarea, barra = await _tarea_y_barra(db, version.tarea_id, current_user, bloquear=True)
    entrega = await _entrega_bloqueada(db, tarea.id)
    # Con la entrega bloqueada, se vuelve a leer: otro pudo haber decidido.
    await db.refresh(version)
    if version.fase_id != entrega.fase_actual_id:
        raise HTTPException(status_code=409, detail="Esa versión ya no es la que está en revisión: recargá")
    if reglas.archivada_sin_terminar(entrega):
        raise HTTPException(
            status_code=409,
            detail="Esta tarjeta está archivada: para decidirla, el equipo tiene que sacarla del archivo",
        )
    resultado, avisados = await _aplicar_decision(
        db, current_user, tarea, barra, entrega, version, decision,
        comentario=payload.comentario, marcas=payload.marcas, nota_interna=payload.notaInterna,
    )
    resumen = await _resumen(db, tarea.id)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {
        "id": version.id, "rev": _rev_para(current_user, rev), "resultado": resultado, "entrega": resumen,
        "avisados": avisados,
    }


class Devolucion(BaseModel):
    """Lo que hay que cambiar de una pieza que ya estaba aprobada."""
    comentario: str = Field(..., max_length=5000)

    @field_validator("comentario")
    @classmethod
    def _con_texto(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Escribí qué hay que cambiar")
        return v


@router.post("/tareas/{tarea_id}/devolver")
async def devolver_aprobada(
    tarea_id: str,
    payload: Devolucion,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Devolver una pieza que ya estaba aprobada, con lo que hay que cambiar.

    Pedido de Ivan (17/11/2026): con la última fase aprobada la tarjeta
    quedaba cerrada y no había dónde escribir para "volver para atrás el
    arte". Ahora quien la aprueba (o quien lidera) la devuelve con un texto:
    se abre una fase nueva al final ("Entrega 2", "Entrega 3"... sin tope),
    que guarda ese texto, y a quien entrega le llega el aviso. La tarjeta
    deja de estar finalizada (y archivada, si ya lo estaba) y la tarea vuelve
    a en proceso: es lo que hace `recalcular` cuando vuelve a haber algo para
    entregar."""
    if externos.es_externo(current_user):
        raise HTTPException(status_code=403, detail="Una cuenta externa no devuelve piezas")
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user, bloquear=True)
    entrega = await _entrega_bloqueada(db, tarea.id)
    if entrega.momento != "aprobada":
        raise HTTPException(
            status_code=409,
            detail="Esta pieza todavía no está aprobada: los cambios se piden al revisar la entrega",
        )
    if not reglas.puede_devolver(
        current_user.id, _puede_gestionar_tareas(current_user), list(entrega.aprobadores or []), entrega.momento,
    ):
        raise HTTPException(
            status_code=403,
            detail="La devuelve quien la aprueba o quien lidera las tareas",
        )
    fases = (await db.execute(
        select(CalendarioFase).where(CalendarioFase.tarea_id == tarea.id).order_by(CalendarioFase.orden)
    )).scalars().all()
    nombre = reglas.nombre_de_fase_nueva([f.nombre for f in fases])
    fase = CalendarioFase(
        id=reglas.nuevo_id("fa"), tarea_id=tarea.id, orden=max((f.orden for f in fases), default=-1) + 1,
        nombre=nombre, estado="pendiente", motivo=payload.comentario, abierta_por_id=current_user.id,
    )
    db.add(fase)
    await db.flush()
    await reglas.recalcular(db, entrega, tarea)

    avisados = 0
    mensaje = reglas.mensaje_de_devolucion(
        current_user.full_name, tarea.titulo, barra.nombre, nombre, payload.comentario,
    )
    for uid in await reglas.destinatarios_de_la_tarjeta(db, tarea, barra.mundo):
        if uid != current_user.id and await reglas.avisar(
            db, uid, mensaje, reglas.referencia(barra.id, tarea.id, fase.id, "devuelta"),
        ):
            avisados += 1
    resumen = await _resumen(db, tarea.id)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": tarea.id, "fase": {"id": fase.id, "nombre": nombre}, "rev": _rev_para(current_user, rev),
            "entrega": resumen, "avisados": avisados}


async def _aplicar_decision(
    db: AsyncSession, current_user: User, tarea: CalendarioTarea, barra: CalendarioBarra,
    entrega: CalendarioEntrega, version: CalendarioVersion, decision: str, *,
    comentario: str | None, marcas: list, nota_interna: str | None,
) -> tuple[str, int]:
    """Aprobar o pedir cambios sobre la versión que espera, con la tarea y la
    entrega ya bloqueadas. Es lo mismo desde el revisor (POST /decision) que
    arrastrando la tarjeta en el tablero (POST /mover): las reglas de la
    cadena son una sola. No hace commit. Devuelve (resultado de la versión, a
    cuántos se avisó). `decision` ya viene validada (reglas.validar_decision):
    'aprobada' o 'cambios'."""
    comentario = (comentario or "").strip() or None
    nota_interna = (nota_interna or "").strip() or None
    if decision == "aprobada" and marcas:
        # Con marcas no hay aprobación: desde el 19/11/2026 una marca es
        # siempre algo que la agencia tiene que corregir en otra ronda.
        raise HTTPException(
            status_code=422,
            detail="Con marcas, elegí «Pedir cambios»: «Aprobar» las perdería",
        )
    if decision != "aprobada" and not marcas and not comentario:
        # La nota interna no cuenta: quien entrega no la ve, y no sabría qué cambiar.
        raise HTTPException(status_code=422, detail="Decí qué hay que cambiar: poné una marca sobre la imagen o un comentario")

    aprobadores = list(entrega.aprobadores or [])
    previas = await reglas.decisiones_de(db, version.id)
    try:
        aprobador, orden, _ = reglas.lugar_para_decidir(
            current_user.id, _puede_gestionar_tareas(current_user), aprobadores, previas,
            _autor(tarea, version.subida_por_id),
        )
    except NoPuedeDecidir as exc:
        raise HTTPException(status_code=exc.codigo, detail=str(exc))

    ids_imagenes = {
        i for (i,) in (await db.execute(
            select(CalendarioVersionImagen.id).where(CalendarioVersionImagen.version_id == version.id)
        )).all()
    }
    if any(m.imagenId not in ids_imagenes for m in marcas):
        raise HTTPException(status_code=422, detail="Una marca está sobre una imagen que no es de esta versión")

    ahora = datetime.now(timezone.utc)
    db.add(CalendarioDecision(
        version_id=version.id, aprobador_id=aprobador, decidido_por_id=current_user.id, orden=orden,
        decision=decision, comentario=comentario, nota_interna=nota_interna,
    ))
    hay = (await db.execute(
        select(func.coalesce(func.max(CalendarioMarca.numero), 0)).where(CalendarioMarca.version_id == version.id)
    )).scalar_one()
    de_la_ia: dict[str, tuple[str, int]] = {}
    for i, m in enumerate(marcas, 1):
        marca_id = reglas.nuevo_id("mk")
        # Solo hay marcas de tipo "cambio" (las tilda la agencia al
        # reentregar). El tipo "ajuste" era el del aprobado con cambios: ya no
        # se crea (19/11/2026); la columna queda por las marcas viejas.
        db.add(CalendarioMarca(
            id=marca_id, version_id=version.id, imagen_id=m.imagenId, tarea_id=tarea.id,
            numero=hay + i, x=m.x, y=m.y, texto=m.texto, tipo="cambio", autor_id=current_user.id,
        ))
        if m.observacionIA:
            de_la_ia[m.observacionIA] = (marca_id, hay + i)
    if de_la_ia:
        # Las observaciones de la IA que se hicieron marca. Si no hay revisión
        # (o no es de esta versión), no pasa nada: la marca ya está.
        revision = await db.get(CalendarioRevisionIA, version.id, with_for_update=True)
        if revision is not None and revision.estado == "lista":
            revision.observaciones = revision_ia.marcar_convertidas(
                list(revision.observaciones or []), de_la_ia, current_user.id, ahora,
            )

    resultado = reglas.resultado_de_version(aprobadores, previas + [(aprobador, decision)])
    fase = await db.get(CalendarioFase, version.fase_id)
    if resultado in ("aprobada", "cambios"):
        version.estado = resultado
        version.decidida_at = ahora
    if resultado == "aprobada":
        fase.estado = "aprobada"
        fase.aprobada_at = ahora
    await db.flush()
    await reglas.recalcular(db, entrega, tarea)

    # Los avisos: uno por persona y por decisión, nunca a uno mismo. Lo que
    # es "para quien la hace" le llega a la persona asignada y, si la tarjeta
    # es de una agencia, a todas sus cuentas (16/11/2026: "volvió con cambios
    # → a la agencia").
    quien = _quien(current_user)
    quienes_la_hacen = await reglas.destinatarios_de_la_tarjeta(db, tarea, barra.mundo)
    avisados = 0

    async def avisar(uid: int | None, mensaje: str, evento: str) -> None:
        nonlocal avisados
        if uid is None or uid == current_user.id:
            return
        if await reglas.avisar(db, uid, mensaje, reglas.referencia(barra.id, tarea.id, version.id, evento)):
            avisados += 1

    if resultado == "revision":
        # Aprobó y sigue la cadena: le toca al siguiente. A quien entrega no
        # se le avisa: no tiene nada que hacer todavía, y sería ruido.
        siguiente = entrega.aprobador_de_turno_id
        await avisar(siguiente, reglas.mensaje_para_revisar(
            "", version.ronda, fase.nombre, tarea.titulo, barra.nombre, aprobo_antes=quien,
        ), f"revisar-{siguiente}")
    elif resultado == "cambios":
        for uid in quienes_la_hacen:
            await avisar(uid, reglas.mensaje_de_cambios(
                quien, version.ronda, fase.nombre, tarea.titulo, len(marcas),
            ), "cambios")
    else:
        terminada = entrega.momento == "aprobada"
        siguiente_fase = None
        if not terminada and entrega.fase_actual_id:
            siguiente_fase = (await db.get(CalendarioFase, entrega.fase_actual_id)).nombre
        for uid in quienes_la_hacen:
            await avisar(uid, reglas.mensaje_de_aprobacion(
                quien, version.ronda, fase.nombre, tarea.titulo,
                siguiente_fase=siguiente_fase, sigue_revisando=None, terminada=terminada,
            ), "aprobada")
        # Finalizada: además, a quien la pidió (16/11/2026).
        if terminada and tarea.creado_por_id not in quienes_la_hacen:
            await avisar(tarea.creado_por_id, reglas.mensaje_de_tarjeta_finalizada(tarea.titulo, barra.nombre), "hecha")
    return resultado, avisados


# ---------------------------------------------------------------------------
# Mover la tarjeta en el tablero
# ---------------------------------------------------------------------------

def _quien_mueve(usuario: User, tarea: CalendarioTarea, entrega: CalendarioEntrega, decide: bool) -> reglas.QuienMueve:
    """Lo que esta persona puede hacer con esta tarjeta (ver reglas.movimiento)."""
    externo = externos.es_externo(usuario)
    del_equipo = not externo and (
        _puede_gestionar_tareas(usuario)
        or usuario.id in (tarea.creado_por_id, entrega.creado_por_id)
        or usuario.id in list(entrega.aprobadores or [])
    )
    return reglas.QuienMueve(
        es_externo=externo, entrega=puede_entregar(usuario, tarea), decide=decide and not externo,
        del_equipo_de_la_tarjeta=del_equipo,
        # El equipo de Tienda la mueve a cualquier columna (18/11/2026).
        libre=not externo,
    )


class Movimiento(BaseModel):
    # La columna donde la pantalla veía la tarjeta: si ya no está ahí (otra
    # persona la movió recién), no se mueve nada y se avisa.
    desde: Literal["ingresado", "en-proceso", "esperando", "finalizado", "archivado"]
    a: Literal["ingresado", "en-proceso", "esperando", "finalizado", "archivado"]
    # "¿Qué hay que cambiar?", al devolverla a En proceso.
    comentario: str | None = Field(None, max_length=5000)


@router.post("/tareas/{tarea_id}/mover")
async def mover(
    tarea_id: str,
    payload: Movimiento,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Arrastrar una tarjeta a otra columna del tablero (o "Mover a…"). Las
    reglas son del servidor (reglas.movimiento): quien entrega arranca;
    Esperando feedback se llega entregando (POST /versiones); el equipo pide
    cambios o aprueba respetando la cadena, y archiva o saca del archivo."""
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user, bloquear=True)
    if not _puede_ver(current_user, barra.mundo, tarea):
        raise HTTPException(status_code=404, detail=_NO_EXISTE_LA_TAREA)
    entrega = await _entrega_bloqueada(db, tarea_id)
    actual = reglas.columna_de_entrega(entrega)
    if payload.desde != actual:
        raise HTTPException(
            status_code=409,
            detail=f"Esta tarjeta ya se movió: ahora está en {reglas.NOMBRES_DE_COLUMNA[actual]}.",
        )
    hay_versiones = (await db.execute(
        select(func.count()).select_from(CalendarioVersion).where(CalendarioVersion.tarea_id == tarea_id)
    )).scalar_one() > 0
    version = await _ultima_version(db, entrega.fase_actual_id) if entrega.momento == "revision" else None
    decide = False
    if version is not None and version.estado == "revision":
        decide, _ = _puede_decidir(current_user, tarea, entrega, version, await reglas.decisiones_de(db, version.id))
    quien = _quien_mueve(current_user, tarea, entrega, decide)
    try:
        accion = reglas.movimiento(
            actual, payload.a, quien, hay_versiones=hay_versiones, vuelve_a=reglas.columna_al_desarchivar(entrega),
        )
    except reglas.MovimientoInvalido as exc:
        raise HTTPException(status_code=exc.codigo, detail=str(exc))

    ahora = datetime.now(timezone.utc)
    avisados = 0
    resultado = None
    if accion == "nada":
        return {"id": tarea_id, "columna": actual, "rev": None, "avisados": 0}
    if accion == "a-mano":
        await _mover_a_mano(db, entrega, tarea, actual, payload.a, ahora, current_user)
    elif accion == "arrancar":
        entrega.columna_manual = None
        entrega.iniciada_at = ahora
        # La ficha muestra el estado de la tarea: si la agencia la arrancó,
        # que no siga diciendo «Pendiente» hasta la primera entrega (16/11/2026).
        if tarea.estado == "pendiente":
            tarea.estado = "en-proceso"
    elif accion == "volver":
        entrega.columna_manual = None
        entrega.iniciada_at = None
        # Volver a Ingresado solo se puede sin nada entregado: vuelve a pendiente.
        if tarea.estado == "en-proceso":
            tarea.estado = "pendiente"
    elif accion in ("aprobar", "pedir-cambios"):
        if version is None:
            raise HTTPException(status_code=409, detail="No hay ninguna entrega esperando feedback: recargá")
        resultado, avisados = await _aplicar_decision(
            db, current_user, tarea, barra, entrega, version,
            "aprobada" if accion == "aprobar" else "cambios",
            comentario=payload.comentario, marcas=[], nota_interna=None,
        )
    elif accion == "archivar":
        entrega.archivada_at = ahora
        entrega.archivada_por_id = current_user.id
        if entrega.momento != "aprobada":
            # Archivarla sin terminar es cancelarla (16/11/2026): la tarea se
            # cierra, como si quien lidera la tildara «hecha» en la ficha, y
            # deja de aparecer pendiente en Mis tareas.
            tarea.estado = "hecha"
    elif accion == "desarchivar":
        entrega.archivada_at = None
        entrega.archivada_por_id = None
        entrega.desarchivada_at = ahora
        if entrega.momento != "aprobada" and tarea.estado == "hecha":
            # Sacarla del archivo sin terminar es reabrirla: la tarea vuelve a
            # pendiente (o en proceso, si ya se entregó algo) y a su fecha
            # contada desde la acción, como al reabrirla desde la ficha.
            tarea.estado = reglas.estado_de_tarea(entrega.momento, hay_versiones, "pendiente")
            tarea.vence = vence_al_reabrir(tarea, barra.desde, barra.hasta)
    await db.flush()
    columna = reglas.columna_de_entrega(entrega)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {
        "id": tarea_id, "columna": columna, "resultado": resultado, "avisados": avisados,
        "rev": _rev_para(current_user, rev), "entrega": await _resumen(db, tarea_id),
        # Qué se hizo: "a-mano" es que el equipo la movió sin entregar ni decidir.
        "accion": accion,
    }


async def _mover_a_mano(
    db: AsyncSession, entrega: CalendarioEntrega, tarea: CalendarioTarea, actual: str, a: str,
    ahora: datetime, usuario: User,
) -> None:
    """Alguien del equipo lleva la tarjeta a una columna a la que las reglas
    no la llevan (18/11/2026, "libre, como Trello"). No se entrega ni se
    decide nada y no se avisa a nadie: solo cambia de columna.

    - Archivado: como archivar (sin terminar, cierra la tarea).
    - Finalizado: se da por aprobada (la tarea queda hecha y se archiva sola
      a los días, como cualquier finalizada).
    - Ingresado, En proceso o Esperando feedback: se guarda la columna
      (`columna_manual`) y la tarea queda pendiente o en proceso. Si estaba
      dada por aprobada, primero vuelve a lo que dicen sus entregas.
    Lo próximo que pase de verdad (una entrega, una decisión) vuelve a mandar.
    """
    if a == "archivado":
        entrega.archivada_at = ahora
        entrega.archivada_por_id = usuario.id
        if entrega.momento != "aprobada":
            tarea.estado = "hecha"
        return
    if actual == "archivado":
        entrega.archivada_at = None
        entrega.archivada_por_id = None
        entrega.desarchivada_at = ahora
    if a == "finalizado":
        entrega.columna_manual = None
        entrega.momento = "aprobada"
        entrega.aprobador_de_turno_id = None
        if entrega.finalizada_at is None or actual != "finalizado":
            entrega.finalizada_at = ahora
        tarea.estado = "hecha"
        return
    if entrega.momento == "aprobada":
        await reglas.recalcular(db, entrega, tarea)
    entrega.columna_manual = a
    tarea.estado = "pendiente" if a == "ingresado" else "en-proceso"


# Hasta el 19/11/2026 acá había PATCH /calendario/marcas/{id}, para tildar
# suelto un "ajuste" del aprobado con cambios. Se fue con él: las marcas que
# quedan ("cambio") se tildan al reentregar (ver `entregar`, `corregidas`).


# ---------------------------------------------------------------------------
# El tablero y "Mis tareas"
# ---------------------------------------------------------------------------
# Lo que más les molesta del Trello de hoy (16/11/2026) es que anda lentísimo
# porque carga miles de tarjetas viejas. Por eso el tablero lee solo lo que
# muestra:
#
# - las 4 columnas activas (Ingresado, En proceso, Esperando feedback,
#   Finalizado) enteras, y de Archivado solo las primeras POR_PAGINA (las más
#   recientes) con "Ver más" (GET /entregas/archivadas);
# - lo archivado hace OCULTAR_ARCHIVADAS_DIAS o más ni se lee: queda en la
#   base y lo encuentra el buscador (GET /entregas/buscar);
# - de cada tarjeta, lo justo: nada de historia ni marcas, y de la imagen solo
#   el id de la miniatura (la pantalla la pide cuando la tarjeta se ve);
# - todo en unas pocas consultas, sin una por tarjeta (ver _tarjetas).
#
# El análisis de entregas va aparte (GET /entregas/metricas): no cambia
# con cada movimiento y no tiene por qué viajar en cada pregunta.

POR_PAGINA = 20
_ACTIVOS = ("produccion", "revision", "cambios")


def _consulta_tarjetas():
    return (
        select(CalendarioEntrega, CalendarioTarea, CalendarioBarra)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioEntrega.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
    )


def _las_que_ve(usuario: User):
    """El WHERE de las tarjetas que una persona puede ver en un mundo: las de
    acciones dentro de su alcance del calendario y, siempre, las suyas (una
    cuenta externa, SOLO las suyas)."""
    propias = reglas.condicion_tarjeta_propia(usuario)
    if externos.es_externo(usuario):
        return propias
    v = alcance.ventana_de(usuario)
    if v is None:
        return true()
    return or_(alcance.condicion(CalendarioBarra, v), propias)


def _sin_ocultar():
    """El WHERE de lo que todavía se muestra: lo activo que no se archivó, y
    de lo archivado (aprobado, o cancelado sin terminar) lo que no lleva
    OCULTAR_ARCHIVADAS_DIAS en Archivado. Es un filtro grueso (con un día de
    margen, para no depender de la hora): el fino, en días de Uruguay, lo hace
    reglas.oculta al clasificar."""
    archivar = timedelta(days=max(0, settings.ARCHIVAR_TARJETAS_DIAS))
    margen = datetime.now(timezone.utc) - timedelta(days=max(0, settings.OCULTAR_ARCHIVADAS_DIAS) + 1)
    se_archiva = func.coalesce(
        CalendarioEntrega.archivada_at,
        func.greatest(CalendarioEntrega.finalizada_at, CalendarioEntrega.desarchivada_at) + archivar,
        func.coalesce(CalendarioEntrega.updated_at, CalendarioEntrega.created_at) + archivar,
    )
    return or_(
        and_(CalendarioEntrega.momento.in_(_ACTIVOS), CalendarioEntrega.archivada_at.is_(None)),
        # Una aprobada que alguien volvió a una columna a mano (0075) está activa.
        and_(CalendarioEntrega.columna_manual.isnot(None), CalendarioEntrega.archivada_at.is_(None)),
        # Lo archivado a mano, con cualquier momento (16/11/2026: también lo
        # cancelado), se archivó ese día: `se_archiva` es su archivada_at.
        and_(
            or_(CalendarioEntrega.momento == "aprobada", CalendarioEntrega.archivada_at.isnot(None)),
            se_archiva > margen,
        ),
    )


def _columna(e: CalendarioEntrega, hoy) -> str:
    return reglas.columna_de_entrega(e, hoy)


def _es_oculta(e: CalendarioEntrega, hoy) -> bool:
    """Si ya lleva OCULTAR_ARCHIVADAS_DIAS en Archivado: no se carga en el
    tablero (la encuentra el buscador). Lo aprobado, y también lo que se
    archivó sin terminar (cancelado)."""
    if e.archivada_at is None and e.columna_manual is not None:
        return False
    return (e.momento == "aprobada" or e.archivada_at is not None) and reglas.oculta(
        e.finalizada_at, e.archivada_at, e.desarchivada_at, hoy,
        settings.ARCHIVAR_TARJETAS_DIAS, settings.OCULTAR_ARCHIVADAS_DIAS,
    )


def _dia_de_archivo(e: CalendarioEntrega):
    return reglas.dia_de_archivo(e.finalizada_at, e.archivada_at, e.desarchivada_at, settings.ARCHIVAR_TARJETAS_DIAS)


async def _tarjetas(db: AsyncSession, filas, usuario: User, hoy=None) -> list[dict]:
    """Una tarjeta por tarea con entregas: lo que muestra el tablero (y "Mis
    tareas" y el buscador). Lo justo para pintarla: la miniatura va por id
    (se pide aparte), y nada de la historia. Todo en un puñado de consultas
    para todas juntas, nunca una por tarjeta.

    Para una cuenta externa, los nombres sin mail (los de afuera de su
    empresa, solo si aprueban)."""
    filas = list(filas)
    if not filas:
        return []
    hoy = hoy or alcance.hoy_en_uruguay()
    ids = [t.id for _, t, _ in filas]
    # Las entregas ya vinieron con las filas: no se vuelven a pedir.
    resumenes = await reglas.resumenes_de_entregas(db, ids, entregas=[e for e, _, _ in filas])
    # La última versión de cada tarjeta, con quién la subió y su miniatura,
    # en UNA consulta (con la base lejos, cada ida y vuelta pesa más que la
    # consulta misma).
    miniatura = (
        select(CalendarioVersionImagen.id)
        .where(CalendarioVersionImagen.version_id == CalendarioVersion.id, CalendarioVersionImagen.orden == 0,
               CalendarioVersionImagen.purgada_at.is_(None))
        .correlate(CalendarioVersion).limit(1).scalar_subquery()
    )
    ultimas: dict[str, tuple] = {
        tid: (vid, estado, subida, mini) for tid, vid, estado, subida, mini in (await db.execute(
            select(CalendarioVersion.tarea_id, CalendarioVersion.id, CalendarioVersion.estado,
                   CalendarioVersion.subida_por_id, miniatura)
            .where(CalendarioVersion.tarea_id.in_(ids))
            .distinct(CalendarioVersion.tarea_id)
            .order_by(CalendarioVersion.tarea_id, CalendarioVersion.created_at.desc())
        )).all()
    }
    miniaturas = {v[0]: v[3] for v in ultimas.values() if v[3]}
    subidas = {v[0]: v[2] for v in ultimas.values()}
    # Para saber quién puede aprobarlas arrastrando: las decisiones de las
    # versiones que esperan feedback, de una sola vez.
    en_revision = [v[0] for v in ultimas.values() if v[1] == "revision"]
    decisiones: dict[str, reglas.Decisiones] = {}
    if en_revision:
        for vid, a, d in (await db.execute(
            select(CalendarioDecision.version_id, CalendarioDecision.aprobador_id, CalendarioDecision.decision)
            .where(CalendarioDecision.version_id.in_(en_revision)).order_by(CalendarioDecision.id)
        )).all():
            decisiones.setdefault(vid, []).append((a, d))

    ids_personas = [t.asignado_a_id for _, t, _ in filas] + [e.aprobador_de_turno_id for e, _, _ in filas]
    if externos.es_externo(usuario):
        # Quiénes aprueban estas tarjetas (todas suyas): los ve con nombre.
        # Salen de las filas que ya están, sin ir otra vez a la base.
        aprobadores = {a for e, _, _ in filas for a in (e.aprobadores or []) if isinstance(a, int)}
        aprobadores |= {e.aprobador_de_turno_id for e, _, _ in filas if e.aprobador_de_turno_id is not None}
        nombres = await nombres_para_externo(db, usuario, ids_personas, aprobadores)
    else:
        nombres = await _nombres(db, ids_personas)
    gestor = _puede_gestionar_tareas(usuario)

    def tarjeta(e: CalendarioEntrega, t: CalendarioTarea, b: CalendarioBarra) -> dict:
        ultima = ultimas.get(t.id)
        decide = False
        # Archivada sin terminar (cancelada): ni se entrega ni se decide.
        cancelada = reglas.archivada_sin_terminar(e)
        if (ultima and ultima[1] == "revision" and e.momento == "revision" and not cancelada
                and not externos.es_externo(usuario)):
            try:
                reglas.lugar_para_decidir(
                    usuario.id, gestor, list(e.aprobadores or []), decisiones.get(ultima[0], []),
                    _autor(t, subidas.get(ultima[0])),
                )
                decide = True
            except NoPuedeDecidir:
                decide = False
        columna = _columna(e, hoy)
        quien = _quien_mueve(usuario, t, e, decide)
        archivo = _dia_de_archivo(e) if (e.momento == "aprobada" or e.archivada_at is not None) else None
        return {
            "tareaId": t.id, "titulo": t.titulo, "estado": t.estado,
            "columna": columna, "volvioConCambios": e.momento == "cambios" and not cancelada,
            # Archivada sin aprobarse: la pantalla la marca "Cancelada" para que
            # no se confunda con una pieza terminada.
            "cancelada": cancelada,
            "vence": t.vence.isoformat() if t.vence else None,
            "ancla": t.ancla, "anclaDias": t.ancla_dias,
            "tipo": t.tipo, "opciones": list(t.opciones or []),
            "asignadoA": t.asignado_a_id, "responsable": nombres.get(t.asignado_a_id),
            "turno": nombres.get(e.aprobador_de_turno_id),
            "hace": quien_la_hace(t, nombres),
            "accion": {
                "id": b.id, "mundo": b.mundo, "nombre": b.nombre, "color": b.color,
                "desde": b.desde.isoformat(), "hasta": b.hasta.isoformat(),
            },
            "entrega": resumenes.get(t.id),
            "miniatura": miniaturas.get(ultima[0]) if ultima else None,
            "puedo": {
                "entregar": quien.entrega and e.momento in ("produccion", "cambios") and not cancelada,
                "decidir": decide,
                "mover": reglas.destinos_posibles(
                    columna, quien, hay_versiones=ultima is not None, vuelve_a=reglas.columna_al_desarchivar(e),
                ),
            },
            "archivadaEl": archivo.isoformat() if archivo and columna == "archivado" else None,
            "actualizada": (e.updated_at or e.created_at).isoformat() if (e.updated_at or e.created_at) else None,
        }

    return [tarjeta(e, t, b) for e, t, b in filas]


async def _filas_del_tablero(db: AsyncSession, usuario: User, mundo: str) -> list:
    """Las filas (entrega, tarea, acción) de lo que se muestra, ya sin lo
    oculto, en el orden del tablero (lo que vence antes, arriba)."""
    hoy = alcance.hoy_en_uruguay()
    filas = (await db.execute(
        _consulta_tarjetas().where(CalendarioBarra.mundo == mundo, _las_que_ve(usuario), _sin_ocultar())
        .order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioBarra.desde, CalendarioTarea.id)
    )).all()
    return [f for f in filas if not _es_oculta(f[0], hoy)]


def _archivadas_primero_las_nuevas(filas, hoy) -> list:
    archivadas = [f for f in filas if _columna(f[0], hoy) == "archivado"]
    return sorted(archivadas, key=lambda f: (_dia_de_archivo(f[0]) or hoy, f[1].id), reverse=True)


async def _datos_del_tablero(db: AsyncSession, usuario: User, mundo: str) -> dict:
    hoy = alcance.hoy_en_uruguay()
    filas = await _filas_del_tablero(db, usuario, mundo)
    archivadas = _archivadas_primero_las_nuevas(filas, hoy)
    activas = [f for f in filas if _columna(f[0], hoy) != "archivado"]
    pagina = archivadas[:POR_PAGINA]
    return {
        "mundo": mundo,
        "hoy": hoy.isoformat(),
        "tarjetas": await _tarjetas(db, activas + pagina, usuario, hoy),
        "archivadas": {"total": len(archivadas), "mostradas": len(pagina)},
        "dias": {"archivar": settings.ARCHIVAR_TARJETAS_DIAS, "ocultar": settings.OCULTAR_ARCHIVADAS_DIAS},
    }


@router.get("/entregas")
async def tablero(
    mundo: str,
    rev: int | None = None,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """El tablero de un mundo: las tarjetas que la persona ve, con su columna
    (Ingresado, En proceso, Esperando feedback, Finalizado, Archivado). Lo ve
    aunque su alcance del calendario sea "No lo ve": es su trabajo.

    Como /datos, si nada de este mundo cambió desde `rev`, contesta "sin
    cambios" y no viaja nada más: el tablero pregunta cada 6 s (15 s hasta
    el 24/11/2026). Quien ve una
    parte (la agencia, un alcance limitado) recibe la huella de lo que ve,
    no el contador de todos. Que una tarjeta pase sola a Archivado no cambia
    la revisión hasta que el loop diario lo anota: por eso la respuesta dice
    `hoy`, y la pantalla trae todo de nuevo cuando cambia el día."""
    exigir_mundo(current_user, mundo)
    if _ve_una_parte(current_user):
        datos = await _datos_del_tablero(db, current_user, mundo)
        huella = externos.huella(datos)
        if rev is not None and rev == huella:
            return {"rev": huella, "sinCambios": True}
        return {"rev": huella, **datos}
    fila = (await db.execute(
        select(
            CalendarioRevision.rev,
            select(CalendarioRevisionMundo.rev).where(CalendarioRevisionMundo.mundo == mundo).scalar_subquery(),
        ).where(CalendarioRevision.id == 1)
    )).first()
    actual = fila[0] if fila else 0
    ultima_del_mundo = fila[1] if fila and fila[1] is not None else actual
    if rev is not None and ultima_del_mundo <= rev <= actual:
        return {"rev": actual, "sinCambios": True}
    return {"rev": actual, **await _datos_del_tablero(db, current_user, mundo)}


@router.get("/entregas/archivadas")
async def mas_archivadas(
    mundo: str,
    desde: int = 0,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """"Ver más" de Archivado: la página siguiente (las de los últimos
    OCULTAR_ARCHIVADAS_DIAS días; lo de antes, con el buscador)."""
    exigir_mundo(current_user, mundo)
    if not (0 <= desde <= 100_000):
        raise HTTPException(status_code=422, detail="Esa página no existe")
    hoy = alcance.hoy_en_uruguay()
    archivadas = _archivadas_primero_las_nuevas(await _filas_del_tablero(db, current_user, mundo), hoy)
    pagina = archivadas[desde:desde + POR_PAGINA]
    return {
        "tarjetas": await _tarjetas(db, pagina, current_user, hoy),
        "total": len(archivadas), "hasta": desde + len(pagina),
    }


# También las mayúsculas acentuadas: que lower() de la base las baje depende
# de su configuración regional (con la "C", "DÍA" queda "dÍa" y no se
# encontraba buscando "dia"). Revisión del 16/11/2026.
_TILDES = (
    "áàâäãéèêëíìîïóòôöõúùûüñçÁÀÂÄÃÉÈÊËÍÌÎÏÓÒÔÖÕÚÙÛÜÑÇ",
    "aaaaaeeeeiiiiooooouuuuncaaaaaeeeeiiiiooooouuuunc",
)


def _normalizado(columna):
    """La columna en minúscula y sin tildes, para buscar como escribe la gente."""
    return func.translate(func.lower(columna), *_TILDES, type_=String)


@router.get("/entregas/buscar")
async def buscar(
    mundo: str,
    q: str,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """El buscador del tablero, por el nombre de la tarjeta y el de su acción:
    "ciberlunes banners" encuentra "Ciberlunes - Banners" (sin mirar
    mayúsculas, tildes ni el guión). Busca también en lo archivado de verdad
    (lo que ya no se carga en el tablero) y lo devuelve aparte, para abrirlo
    y ver sus materiales. Respeta lo mismo que el tablero: la agencia solo
    encuentra lo suyo."""
    exigir_mundo(current_user, mundo)
    palabras = tipos_de_tarea.palabras_de_busqueda(q)
    if not palabras or sum(len(p) for p in palabras) < 2:
        return {"enTablero": [], "archivadas": [], "palabras": palabras}
    texto = _normalizado(func.concat(CalendarioTarea.titulo, " ", CalendarioBarra.nombre))
    condiciones = [texto.contains(p, autoescape=True) for p in palabras]
    filas = (await db.execute(
        _consulta_tarjetas().where(CalendarioBarra.mundo == mundo, _las_que_ve(current_user), *condiciones)
        .order_by(CalendarioBarra.desde.desc(), CalendarioTarea.id)
        .limit(200)
    )).all()
    hoy = alcance.hoy_en_uruguay()
    visibles = [f for f in filas if not _es_oculta(f[0], hoy)][:30]
    ocultas = [f for f in filas if _es_oculta(f[0], hoy)][:30]
    # Las dos listas en una sola tanda de consultas (y después se separan).
    tarjetas = {t["tareaId"]: t for t in await _tarjetas(db, visibles + ocultas, current_user, hoy)}
    return {
        "enTablero": [tarjetas[f[1].id] for f in visibles],
        "archivadas": [tarjetas[f[1].id] for f in ocultas],
        "palabras": palabras,
    }


async def _metricas(db: AsyncSession, usuario: User, mundo: str, dias: int) -> dict:
    """El análisis de entregas de los últimos `dias` días (ex «Retrabajo»,
    Ivan 20/11/2026):

    - las rondas de las fases aprobadas: del mundo que se mira (total, por
      tipo de pieza y por responsable) y la comparación entre los mundos que
      la persona puede abrir;
    - cuánto tarda cada agencia y cuántas piezas se pasan de fecha, en el
      mundo que se mira (ver `_tiempos` y reglas.analisis_por_agencia)."""
    mundos = mundos_de(usuario)
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    consulta = (
        select(CalendarioEntrega.tipo_pieza, CalendarioVersion.subida_por_id, CalendarioBarra.mundo,
               CalendarioVersion.ronda, CalendarioTarea.para, CalendarioTarea.agencia)
        .select_from(CalendarioVersion)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioVersion.tarea_id)
        .join(CalendarioEntrega, CalendarioEntrega.tarea_id == CalendarioTarea.id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .where(
            CalendarioVersion.estado == "aprobada",
            CalendarioBarra.mundo.in_(mundos),
            CalendarioVersion.decidida_at >= desde,
        )
    )
    externo = externos.es_externo(usuario)
    if externo:
        # Una cuenta externa ve SU retrabajo (lo que entregó ella), no el de
        # los demás: ni de otras agencias ni del equipo. Son números, sin
        # nombres de acciones: por eso no se recorta al alcance.
        consulta = consulta.where(CalendarioVersion.subida_por_id == usuario.id)
    # De quién es el retrabajo: de quien subió la versión... salvo en una pieza
    # de una agencia de AFUERA, donde quien la sube es alguien del equipo que
    # carga lo que le mandaron: las rondas son de esa agencia, no de esa
    # persona (revisión del 16/11/2026). Ahí se agrupa por el nombre de la
    # agencia (sin mirar tildes, mayúsculas ni espacios: externos.clave_de_empresa).
    agencias: dict[str, str] = {}
    filas = []
    for tipo, subida, mundo_fila, ronda, para, agencia in (await db.execute(consulta)).all():
        limpia = externos.limpiar_empresa(agencia) if para == "fuera" else None
        if limpia:
            clave = f"fuera:{externos.clave_de_empresa(limpia)}"
            agencias.setdefault(clave, limpia)
            filas.append((tipo, clave, mundo_fila, ronda))
        else:
            filas.append((tipo, subida, mundo_fila, ronda))
    del_mundo = reglas.metricas_de_retrabajo([f for f in filas if f[2] == mundo])
    todos = reglas.metricas_de_retrabajo(filas)
    if externo:
        nombres = {usuario.id: nombre_sin_mail(usuario)}
    else:
        nombres = await _nombres(db, [g["clave"] for g in del_mundo["porResponsable"] if isinstance(g["clave"], int)])
    for g in del_mundo["porResponsable"]:
        if g["clave"] in agencias:
            g["nombre"] = f"{agencias[g['clave']]} (agencia de afuera)"
        else:
            g["nombre"] = nombres.get(g["clave"], "Alguien que ya no está")
    for g in del_mundo["porTipo"]:
        g["nombre"] = reglas.TIPOS_DE_PIEZA.get(g["clave"], g["clave"])
    por_mundo = [{**g, "nombre": MUNDOS.get(g["clave"], g["clave"])} for g in todos["porMundo"]]
    tiempos = await _tiempos(db, usuario, mundo, desde)
    return {
        **del_mundo, "porMundo": por_mundo, "dias": dias,
        "tiempos": tiempos["total"], "porAgencia": tiempos["porAgencia"],
    }


async def _tiempos(db: AsyncSession, usuario: User, mundo: str, desde: datetime) -> dict:
    """Las piezas del mundo que entran en el análisis por agencia: las que
    se entregaron por primera vez o se aprobaron desde `desde`, y las que hoy
    están vencidas esperando a quien las hace. Una cuenta externa (la
    agencia) solo las suyas, como en su tablero. Son números, sin nombres de
    acciones: no se recorta al alcance del calendario (igual que las rondas)."""
    hoy = alcance.hoy_en_uruguay()
    primera = (
        select(CalendarioVersion.tarea_id.label("tarea_id"), func.min(CalendarioVersion.created_at).label("at"))
        .group_by(CalendarioVersion.tarea_id)
        .subquery()
    )
    le_toca = and_(
        CalendarioEntrega.momento.in_(("produccion", "cambios")),
        CalendarioEntrega.archivada_at.is_(None),
        CalendarioTarea.estado != "hecha",
    )
    consulta = (
        select(
            CalendarioEntrega.tarea_id, CalendarioTarea.para, CalendarioTarea.agencia, CalendarioEntrega.created_at,
            primera.c.at, CalendarioEntrega.finalizada_at, CalendarioTarea.vence,
            CalendarioEntrega.momento, CalendarioEntrega.archivada_at, CalendarioTarea.estado,
        )
        .select_from(CalendarioEntrega)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioEntrega.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .outerjoin(primera, primera.c.tarea_id == CalendarioEntrega.tarea_id)
        .where(
            CalendarioBarra.mundo == mundo,
            or_(
                primera.c.at >= desde,
                CalendarioEntrega.finalizada_at >= desde,
                and_(le_toca, CalendarioTarea.vence < hoy),
            ),
        )
    )
    if externos.es_externo(usuario):
        consulta = consulta.where(externos.condicion_tarea_propia(CalendarioTarea, usuario))
    piezas = [
        reglas.PiezaDelAnalisis(
            tarea_id=tarea_id, para=para, agencia=agencia, pedida_at=pedida, primera_entrega_at=primera_at,
            aprobada_at=finalizada, vence=vence,
            le_toca_a_quien_la_hace=momento in ("produccion", "cambios") and archivada is None and estado != "hecha",
        )
        for tarea_id, para, agencia, pedida, primera_at, finalizada, vence, momento, archivada, estado
        in (await db.execute(consulta)).all()
    ]
    return reglas.analisis_por_agencia(piezas, desde, hoy)


@router.get("/entregas/metricas")
async def metricas(
    mundo: str,
    dias: int = 90,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """El análisis de entregas (ex «Retrabajo»): cuántas rondas llevó aprobar
    cada fase, cuánto tarda cada agencia y cuántas piezas se pasan de fecha.
    Aparte del tablero: se pide al abrirlo y al cambiar el período, no en
    cada pregunta. Se sigue llamando /metricas para no romper una pantalla
    que todavía no se actualizó (Vercel y Render despliegan por separado)."""
    exigir_mundo(current_user, mundo)
    if not (7 <= dias <= 730):
        raise HTTPException(status_code=422, detail="El período va de 7 a 730 días")
    return await _metricas(db, current_user, mundo, dias)


@router.get("/mis-entregas")
async def mis_entregas(
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Para "Mis tareas", en todos los mundos de la persona: lo que espera MI
    decisión (soy el aprobador de turno) y lo que me devolvieron con cambios
    (la hago yo, o mi agencia). Son tarjetas propias: se ven aunque la
    campaña quede fuera de su alcance del calendario (0070)."""
    mundos = mundos_de(current_user)
    externo = externos.es_externo(current_user)
    # Ni lo que se canceló (archivada sin terminar) ni lo que quien lidera
    # cerró a mano («hecha»): no espera a nadie (revisión del 16/11/2026).
    vigentes = (CalendarioEntrega.archivada_at.is_(None), CalendarioTarea.estado != "hecha")
    para_revisar = [] if externo else (await db.execute(
        _consulta_tarjetas().where(
            CalendarioBarra.mundo.in_(mundos),
            CalendarioEntrega.momento == "revision",
            CalendarioEntrega.aprobador_de_turno_id == current_user.id,
            *vigentes,
        ).order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioTarea.id)
    )).all()
    mias = externos.condicion_tarea_propia(CalendarioTarea, current_user) if externo \
        else CalendarioTarea.asignado_a_id == current_user.id
    con_cambios = (await db.execute(
        _consulta_tarjetas().where(
            CalendarioBarra.mundo.in_(mundos),
            CalendarioEntrega.momento == "cambios",
            mias,
            *vigentes,
        ).order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioTarea.id)
    )).all()
    return {
        "paraRevisar": await _tarjetas(db, para_revisar, current_user),
        "conCambios": await _tarjetas(db, con_cambios, current_user),
    }
