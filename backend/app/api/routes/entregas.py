"""entregas.py — entregas por fases con rondas de corrección (0067) y el
tablero de tarjetas estilo Trello (0070).

  PUT    /calendario/tareas/{id}/entregas     — que la tarea lleve entregas: tipo, brief, fases, aprobadores
  DELETE /calendario/tareas/{id}/entregas     — que deje de llevarlas (solo si no se entregó nada)
  GET    /calendario/tareas/{id}/entregas     — todo: fases, rondas, imágenes (los ids), marcas, decisiones
  POST   /calendario/tareas/{id}/versiones    — entregar una ronda (multipart: imágenes y/o un link)
  POST   /calendario/tareas/{id}/mover        — arrastrar la tarjeta a otra columna del tablero
  POST   /calendario/versiones/{id}/decision  — aprobar, aprobar con cambios o pedir cambios
  PATCH  /calendario/marcas/{id}              — tildar (o destildar) una marca como corregida
  GET    /calendario/entregas/imagenes/{id}   — una imagen (?tam=mini|grande)
  GET    /calendario/entregas?mundo=&rev=     — el tablero del mundo (5 columnas) y el retrabajo
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
gestiona: ver `puede_ver_revision`.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import String, and_, delete, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.calendario import (
    _ID, _exigir_gestion_de_tareas, _nueva_revision, _puede_gestionar_tareas, _puede_ver_el_mundo,
    _rev_para, _ve_una_parte, ids_de_aprobadores_de, nombre_sin_mail, nombres_para_externo,
)
from app.core.config import settings
from app.core import alcance, externos
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.mundos import MUNDOS, exigir_mundo, mundos_de
from app.core.rate_limit import limiter
from app.models.calendario import CalendarioBarra, CalendarioRevision, CalendarioRevisionMundo, CalendarioTarea
from app.models.entregas import (
    CalendarioDecision, CalendarioEntrega, CalendarioFase, CalendarioMarca, CalendarioVersion,
    CalendarioVersionImagen,
)
from app.models.revision_ia import CalendarioRevisionIA
from app.models.user import User
from app.services import entregas as reglas
from app.services import revision_ia, tipos_de_tarea
from app.services.espacio import exigir_lugar
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
    eso lo controla quien llama."""
    if puede_entregar(usuario, tarea):
        return False
    return revision_ia.puede_ver(
        usuario.id, es_gestor=_puede_gestionar_tareas(usuario), aprobadores=list(entrega.aprobadores or []),
        responsable_id=tarea.asignado_a_id, subida_por_id=version.subida_por_id if version else None,
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
    if tarea.asignado_a_id is not None and tarea.asignado_a_id in aprobadores:
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
    return {"id": tarea_id, "rev": rev, "entrega": resumen, "avisados": avisados}


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
    return {"id": tarea_id, "rev": rev, "borrada": True}


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

def _puede_decidir(usuario: User, entrega: CalendarioEntrega, version: CalendarioVersion | None,
                   decisiones: reglas.Decisiones) -> tuple[bool, bool]:
    """(puede decidir, como respaldo). La misma regla que exige el POST."""
    if version is None or version.estado != "revision":
        return False, False
    try:
        _, _, respaldo = reglas.lugar_para_decidir(
            usuario.id, _puede_gestionar_tareas(usuario), list(entrega.aprobadores or []), decisiones,
            version.subida_por_id,
        )
        return True, respaldo
    except NoPuedeDecidir:
        return False, False


@router.get("/tareas/{tarea_id}/entregas")
async def ver_entregas(
    tarea_id: str,
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
    if ids_v:
        for im in (await db.execute(
            select(CalendarioVersionImagen).where(CalendarioVersionImagen.version_id.in_(ids_v))
            .order_by(CalendarioVersionImagen.orden)
        )).scalars():
            imagenes.setdefault(im.version_id, []).append(im)
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

    personas = [tarea.asignado_a_id, tarea.creado_por_id, *list(entrega.aprobadores or [])]
    personas += [v.subida_por_id for v in versiones]
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
            "imagenes": [
                {"id": im.id, "orden": im.orden, "purgada": im.purgada_at is not None}
                for im in imagenes.get(v.id, [])
            ],
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
    puede_decidir, como_respaldo = _puede_decidir(current_user, entrega, actual, decisiones_actual)
    entrega_yo = puede_entregar(current_user, tarea)
    quien = _quien_mueve(current_user, tarea, entrega, puede_decidir)
    columna = reglas.columna_de_entrega(entrega)
    return {
        "tarea": {
            "id": tarea.id, "titulo": tarea.titulo, "descripcion": tarea.descripcion, "estado": tarea.estado,
            "asignadoA": tarea.asignado_a_id, "vence": tarea.vence.isoformat() if tarea.vence else None,
            "creadoPor": tarea.creado_por_id,
            "ancla": tarea.ancla, "anclaDias": tarea.ancla_dias,
            "tipo": tarea.tipo, "opciones": list(tarea.opciones or []), "detalles": dict(tarea.detalles or {}),
            # Lo que se pidió con sus medidas ("Banners: Header (web 1920×416 ·
            # mobile 640×260)"), así quien la hace lo ve sin buscarlo.
            "pedido": tipos_de_tarea.descripcion_del_pedido(tarea.tipo, list(tarea.opciones or []), tarea.detalles),
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
                "versiones": [version_json(v) for v in versiones if v.fase_id == f.id],
            }
            for f in fases
        ],
        "personas": {str(k): v for k, v in nombres.items()},
        "columna": columna,
        "puedo": {
            "entregar": entrega_yo and entrega.momento in ("produccion", "cambios"),
            "decidir": puede_decidir,
            "comoRespaldo": como_respaldo,
            "configurar": _puede_gestionar_tareas(current_user),
            "tildarMarcas": entrega_yo or _puede_gestionar_tareas(current_user),
            # A qué columnas del tablero la puede llevar (ver reglas.movimiento).
            "mover": reglas.destinos_posibles(columna, quien, hay_versiones=bool(versiones)),
            # Si le mostramos lo que encontró la IA en la versión en curso (el
            # front la pide aparte, y el servidor lo vuelve a controlar ahí).
            "verRevisionIA": puede_ver_revision(current_user, entrega, tarea, actual),
        },
        "limites": {"imagenes": MAX_IMAGENES, "bytesImagen": MAX_BYTES_IMAGEN, "marcas": MAX_MARCAS},
    }


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
    fila = (await db.execute(
        select(CalendarioVersionImagen.tipo_mime, CalendarioVersionImagen.tipo_mime_miniatura,
               CalendarioTarea, CalendarioBarra, CalendarioEntrega)
        .join(CalendarioVersion, CalendarioVersion.id == CalendarioVersionImagen.version_id)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioVersion.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .join(CalendarioEntrega, CalendarioEntrega.tarea_id == CalendarioTarea.id, isouter=True)
        .where(CalendarioVersionImagen.id == imagen_id)
    )).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Esa imagen ya no existe")
    tipo, tipo_mini, tarea, barra, entrega = fila
    # Lo mismo que la tarea (`_tarea_y_barra`): una cuenta externa, solo las
    # de sus tarjetas; nadie, las de una acción fuera de su alcance que no
    # sea una tarjeta suya. Lo demás, el mismo 404 que una que no existe.
    propia = entrega is not None and reglas.es_tarjeta_propia(current_user, tarea, entrega)
    if externos.es_externo(current_user) and not propia:
        raise HTTPException(status_code=404, detail="Esa imagen ya no existe")
    if not propia and not alcance.toca(barra.desde, barra.hasta, alcance.ventana_de(current_user)):
        raise HTTPException(status_code=404, detail="Esa imagen ya no existe")
    exigir_mundo(current_user, barra.mundo)
    if not _puede_ver(current_user, barra.mundo, tarea):
        raise HTTPException(status_code=403, detail="No podés ver esta imagen")
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


# ---------------------------------------------------------------------------
# Entregar
# ---------------------------------------------------------------------------

async def _leer(archivo: UploadFile, maximo: int, que: str) -> tuple[bytes, str]:
    # Se lee uno más que el máximo: alcanza para saber que se pasó sin leer
    # un archivo gigante entero.
    datos = await archivo.read(maximo + 1)
    try:
        return datos, reglas.validar_imagen(datos, maximo=maximo, que=que)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


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
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Entrega una ronda de la fase en curso: la manda a "Esperando feedback".
    Solo quien la hace (`puede_entregar`). Los materiales son imágenes y/o un
    link al original (Drive, WeTransfer: 16/11/2026, "imágenes como hoy y/o un
    link"). Va todo en un pedido (las imágenes también): o queda la versión
    entera, o no queda nada."""
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
    fase = await db.get(CalendarioFase, entrega.fase_actual_id)
    ultima = await _ultima_version(db, entrega.fase_actual_id)
    if ultima is not None and ultima.estado == "revision":
        raise HTTPException(
            status_code=409,
            detail=f"La ronda {ultima.ronda} de {fase.nombre} todavía está en revisión: esperá a que la decidan",
        )

    if not imagenes and not (link or "").strip():
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

    leidas = []
    for i, (grande, mini) in enumerate(zip(imagenes, miniaturas), 1):
        cual = f"La imagen {i}" if len(imagenes) > 1 else "La imagen"
        datos, tipo = await _leer(grande, MAX_BYTES_IMAGEN, cual)
        datos_mini, tipo_mini = await _leer(mini, MAX_BYTES_MINIATURA, f"La miniatura de {cual.lower()}")
        leidas.append((datos, tipo, datos_mini, tipo_mini))
    # El freno general: con la base casi llena no se guarda ninguna imagen
    # (507, con el mensaje para la persona, y un error en el log).
    await exigir_lugar(db, sum(len(g) + len(m) for g, _, m, _ in leidas))

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
    ))
    # La versión tiene que existir antes que sus imágenes (FK): se manda ya.
    await db.flush()
    for orden, (datos, tipo, datos_mini, tipo_mini) in enumerate(leidas):
        db.add(CalendarioVersionImagen(
            id=reglas.nuevo_id("im"), version_id=versionId, orden=orden, tipo_mime=tipo, datos=datos,
            tipo_mime_miniatura=tipo_mini, miniatura=datos_mini, tamano=len(datos),
        ))
    for m in marcas:
        m.corregida = True
        m.corregida_en_version_id = versionId
        m.corregida_at = ahora
    await db.flush()
    await reglas.recalcular(db, entrega, tarea)

    # Al aprobador que le toca; sin cadena, a quien creó la tarea (que la
    # puede decidir como respaldo si tiene calendario.tareas).
    destino = entrega.aprobador_de_turno_id or tarea.creado_por_id
    avisados = 0
    if destino != current_user.id and await reglas.avisar(
        db, destino,
        reglas.mensaje_para_revisar(_quien(current_user), ronda, fase.nombre, tarea.titulo, barra.nombre),
        reglas.referencia(barra.id, tarea.id, versionId, f"revisar-{destino}"),
    ):
        avisados = 1
    resumen = await _resumen(db, tarea_id)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    # La IA la revisa en segundo plano: arranca después de contestar (y ya
    # con la versión guardada, por el commit de arriba), abre su propia
    # sesión y no levanta nunca. Si falla, la entrega queda igual.
    if revision_ia.activa() and leidas:
        # Solo con imágenes: un link solo no hay cómo mirarlo.
        background_tasks.add_task(revision_ia.revisar_version, versionId)
    return {"id": versionId, "rev": _rev_para(current_user, rev), "ronda": ronda, "entrega": resumen, "avisados": avisados}


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
    decision: Literal["aprobada", "aprobada-con-cambios", "cambios"]
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
    resultado, avisados = await _aplicar_decision(
        db, current_user, tarea, barra, entrega, version, payload.decision,
        comentario=payload.comentario, marcas=payload.marcas, nota_interna=payload.notaInterna,
    )
    resumen = await _resumen(db, tarea.id)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": version.id, "rev": rev, "resultado": resultado, "entrega": resumen, "avisados": avisados}


async def _aplicar_decision(
    db: AsyncSession, current_user: User, tarea: CalendarioTarea, barra: CalendarioBarra,
    entrega: CalendarioEntrega, version: CalendarioVersion, decision: str, *,
    comentario: str | None, marcas: list, nota_interna: str | None,
) -> tuple[str, int]:
    """Aprobar, aprobar con cambios o pedir cambios sobre la versión que
    espera, con la tarea y la entrega ya bloqueadas. Es lo mismo desde el
    revisor (POST /decision) que arrastrando la tarjeta en el tablero
    (POST /mover): las reglas de la cadena son una sola. No hace commit.
    Devuelve (resultado de la versión, a cuántos se avisó)."""
    comentario = (comentario or "").strip() or None
    nota_interna = (nota_interna or "").strip() or None
    if decision == "aprobada" and marcas:
        raise HTTPException(
            status_code=422,
            detail="Con marcas, elegí «Aprobado con cambios» o «Pedir cambios»: «Aprobar» las perdería",
        )
    if decision != "aprobada" and not marcas and not comentario:
        # La nota interna no cuenta: quien entrega no la ve, y no sabría qué cambiar.
        raise HTTPException(status_code=422, detail="Decí qué hay que cambiar: poné una marca sobre la imagen o un comentario")

    aprobadores = list(entrega.aprobadores or [])
    previas = await reglas.decisiones_de(db, version.id)
    try:
        aprobador, orden, _ = reglas.lugar_para_decidir(
            current_user.id, _puede_gestionar_tareas(current_user), aprobadores, previas, version.subida_por_id,
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
    tipo_marca = "cambio" if decision == "cambios" else "ajuste"
    de_la_ia: dict[str, tuple[str, int]] = {}
    for i, m in enumerate(marcas, 1):
        marca_id = reglas.nuevo_id("mk")
        db.add(CalendarioMarca(
            id=marca_id, version_id=version.id, imagen_id=m.imagenId, tarea_id=tarea.id,
            numero=hay + i, x=m.x, y=m.y, texto=m.texto, tipo=tipo_marca, autor_id=current_user.id,
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
    nombres = await _nombres(db, [entrega.aprobador_de_turno_id])
    ajustes = [m.texto for m in marcas] + ([comentario] if comentario and not marcas else [])
    avisados = 0

    async def avisar(uid: int | None, mensaje: str, evento: str) -> None:
        nonlocal avisados
        if uid is None or uid == current_user.id:
            return
        if await reglas.avisar(db, uid, mensaje, reglas.referencia(barra.id, tarea.id, version.id, evento)):
            avisados += 1

    if resultado == "revision":
        # Aprobó y sigue la cadena: le toca al siguiente.
        siguiente = entrega.aprobador_de_turno_id
        await avisar(siguiente, reglas.mensaje_para_revisar(
            "", version.ronda, fase.nombre, tarea.titulo, barra.nombre, aprobo_antes=quien,
        ), f"revisar-{siguiente}")
        # Un "aprobado con cambios" en el medio le interesa ya a quien entrega
        # (puede ir aplicando los ajustes). Un "aprobado" en el medio no: no
        # tiene nada que hacer todavía, y sería ruido.
        if decision == "aprobada-con-cambios":
            for uid in quienes_la_hacen:
                await avisar(uid, reglas.mensaje_de_aprobacion(
                    quien, version.ronda, fase.nombre, tarea.titulo, con_cambios=True, ajustes=ajustes,
                    siguiente_fase=None, sigue_revisando=nombres.get(siguiente, "el siguiente aprobador"),
                    terminada=False,
                ), f"decision-{orden}")
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
                con_cambios=decision == "aprobada-con-cambios", ajustes=ajustes,
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
        decide, _ = _puede_decidir(current_user, entrega, version, await reglas.decisiones_de(db, version.id))
    quien = _quien_mueve(current_user, tarea, entrega, decide)
    try:
        accion = reglas.movimiento(actual, payload.a, quien, hay_versiones=hay_versiones)
    except reglas.MovimientoInvalido as exc:
        raise HTTPException(status_code=exc.codigo, detail=str(exc))

    ahora = datetime.now(timezone.utc)
    avisados = 0
    resultado = None
    if accion == "nada":
        return {"id": tarea_id, "columna": actual, "rev": None, "avisados": 0}
    if accion == "arrancar":
        entrega.iniciada_at = ahora
    elif accion == "volver":
        entrega.iniciada_at = None
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
    elif accion == "desarchivar":
        entrega.archivada_at = None
        entrega.archivada_por_id = None
        entrega.desarchivada_at = ahora
    await db.flush()
    columna = reglas.columna_de_entrega(entrega)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {
        "id": tarea_id, "columna": columna, "resultado": resultado, "avisados": avisados,
        "rev": _rev_para(current_user, rev), "entrega": await _resumen(db, tarea_id),
    }


class MarcaCambios(BaseModel):
    corregida: bool


@router.patch("/marcas/{marca_id}")
async def tildar_marca(
    marca_id: str,
    payload: MarcaCambios,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Tildar suelto un ajuste ("aprobado con cambios") como aplicado, sin
    entregar otra ronda. Lo hace quien entrega, o quien lidera."""
    marca = await db.get(CalendarioMarca, marca_id)
    if marca is None:
        raise HTTPException(status_code=404, detail="Esa marca ya no existe")
    tarea, _ = await _tarea_y_barra(db, marca.tarea_id, current_user)
    if not puede_entregar(current_user, tarea) and not _puede_gestionar_tareas(current_user):
        raise HTTPException(status_code=403, detail="Tilda las marcas quien entrega la pieza")
    marca.corregida = payload.corregida
    marca.corregida_at = datetime.now(timezone.utc) if payload.corregida else None
    if not payload.corregida:
        marca.corregida_en_version_id = None
    await db.commit()
    return {"id": marca_id, "corregida": marca.corregida}


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
# Las métricas de retrabajo van aparte (GET /entregas/metricas): no cambian
# con cada movimiento y no tienen por qué viajar en cada pregunta.

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
    """El WHERE de lo que todavía se muestra: lo activo, y de lo aprobado lo
    que no lleva OCULTAR_ARCHIVADAS_DIAS en Archivado. Es un filtro grueso
    (con un día de margen, para no depender de la hora): el fino, en días de
    Uruguay, lo hace reglas.oculta al clasificar."""
    archivar = timedelta(days=max(0, settings.ARCHIVAR_TARJETAS_DIAS))
    margen = datetime.now(timezone.utc) - timedelta(days=max(0, settings.OCULTAR_ARCHIVADAS_DIAS) + 1)
    se_archiva = func.coalesce(
        CalendarioEntrega.archivada_at,
        func.greatest(CalendarioEntrega.finalizada_at, CalendarioEntrega.desarchivada_at) + archivar,
        func.coalesce(CalendarioEntrega.updated_at, CalendarioEntrega.created_at) + archivar,
    )
    return or_(
        CalendarioEntrega.momento.in_(_ACTIVOS),
        and_(CalendarioEntrega.momento == "aprobada", se_archiva > margen),
    )


def _columna(e: CalendarioEntrega, hoy) -> str:
    return reglas.columna_de_entrega(e, hoy)


def _es_oculta(e: CalendarioEntrega, hoy) -> bool:
    return e.momento == "aprobada" and reglas.oculta(
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
    resumenes = await reglas.resumenes_de_entregas(db, ids)
    ultimas = {
        tid: (vid, estado) for tid, vid, estado in (await db.execute(
            select(CalendarioVersion.tarea_id, CalendarioVersion.id, CalendarioVersion.estado)
            .where(CalendarioVersion.tarea_id.in_(ids))
            .distinct(CalendarioVersion.tarea_id)
            .order_by(CalendarioVersion.tarea_id, CalendarioVersion.created_at.desc())
        )).all()
    }
    miniaturas = {
        vid: iid for vid, iid in (await db.execute(
            select(CalendarioVersionImagen.version_id, CalendarioVersionImagen.id)
            .where(CalendarioVersionImagen.version_id.in_([v for v, _ in ultimas.values()] or [""]),
                   CalendarioVersionImagen.orden == 0, CalendarioVersionImagen.purgada_at.is_(None))
        )).all()
    }
    # Para saber quién puede aprobarlas arrastrando: las decisiones de las
    # versiones que esperan feedback, de una sola vez.
    en_revision = [v for v, estado in ultimas.values() if estado == "revision"]
    decisiones: dict[str, reglas.Decisiones] = {}
    if en_revision:
        for vid, a, d in (await db.execute(
            select(CalendarioDecision.version_id, CalendarioDecision.aprobador_id, CalendarioDecision.decision)
            .where(CalendarioDecision.version_id.in_(en_revision)).order_by(CalendarioDecision.id)
        )).all():
            decisiones.setdefault(vid, []).append((a, d))
    subidas = dict((await db.execute(
        select(CalendarioVersion.id, CalendarioVersion.subida_por_id).where(CalendarioVersion.id.in_(en_revision or [""]))
    )).all()) if en_revision else {}

    ids_personas = [t.asignado_a_id for _, t, _ in filas] + [e.aprobador_de_turno_id for e, _, _ in filas]
    if externos.es_externo(usuario):
        nombres = await nombres_para_externo(db, usuario, ids_personas, await ids_de_aprobadores_de(db, usuario))
    else:
        nombres = await _nombres(db, ids_personas)
    gestor = _puede_gestionar_tareas(usuario)

    def tarjeta(e: CalendarioEntrega, t: CalendarioTarea, b: CalendarioBarra) -> dict:
        ultima = ultimas.get(t.id)
        decide = False
        if ultima and ultima[1] == "revision" and e.momento == "revision" and not externos.es_externo(usuario):
            try:
                reglas.lugar_para_decidir(
                    usuario.id, gestor, list(e.aprobadores or []), decisiones.get(ultima[0], []), subidas.get(ultima[0]),
                )
                decide = True
            except NoPuedeDecidir:
                decide = False
        columna = _columna(e, hoy)
        quien = _quien_mueve(usuario, t, e, decide)
        archivo = _dia_de_archivo(e) if e.momento == "aprobada" else None
        return {
            "tareaId": t.id, "titulo": t.titulo, "estado": t.estado,
            "columna": columna, "volvioConCambios": e.momento == "cambios",
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
                "entregar": quien.entrega and e.momento in ("produccion", "cambios"),
                "decidir": decide,
                "mover": reglas.destinos_posibles(columna, quien, hay_versiones=ultima is not None),
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
    cambios" y no viaja nada más: el tablero pregunta cada 15 s. Quien ve una
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


_TILDES = ("áàâäãéèêëíìîïóòôöõúùûüñç", "aaaaaeeeeiiiiooooouuuunc")


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
    return {
        "enTablero": await _tarjetas(db, visibles, current_user, hoy),
        "archivadas": await _tarjetas(db, ocultas, current_user, hoy),
        "palabras": palabras,
    }


async def _metricas(db: AsyncSession, usuario: User, mundo: str, dias: int) -> dict:
    """El retrabajo de las fases aprobadas en los últimos `dias` días: del
    mundo que se mira (total, por tipo de pieza y por responsable) y la
    comparación entre los mundos que la persona puede abrir."""
    mundos = mundos_de(usuario)
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    consulta = (
        select(CalendarioEntrega.tipo_pieza, CalendarioVersion.subida_por_id, CalendarioBarra.mundo,
               CalendarioVersion.ronda)
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
    filas = (await db.execute(consulta)).all()
    del_mundo = reglas.metricas_de_retrabajo([tuple(f) for f in filas if f[2] == mundo])
    todos = reglas.metricas_de_retrabajo([tuple(f) for f in filas])
    if externo:
        nombres = {usuario.id: nombre_sin_mail(usuario)}
    else:
        nombres = await _nombres(db, [g["clave"] for g in del_mundo["porResponsable"]])
    for g in del_mundo["porResponsable"]:
        g["nombre"] = nombres.get(g["clave"], "Alguien que ya no está")
    for g in del_mundo["porTipo"]:
        g["nombre"] = reglas.TIPOS_DE_PIEZA.get(g["clave"], g["clave"])
    por_mundo = [{**g, "nombre": MUNDOS.get(g["clave"], g["clave"])} for g in todos["porMundo"]]
    return {**del_mundo, "porMundo": por_mundo, "dias": dias}


@router.get("/entregas/metricas")
async def metricas(
    mundo: str,
    dias: int = 90,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """El retrabajo (cuántas rondas llevó aprobar cada fase). Aparte del
    tablero: se pide al abrirlo y al cambiar el período, no en cada pregunta."""
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
    para_revisar = [] if externo else (await db.execute(
        _consulta_tarjetas().where(
            CalendarioBarra.mundo.in_(mundos),
            CalendarioEntrega.momento == "revision",
            CalendarioEntrega.aprobador_de_turno_id == current_user.id,
        ).order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioTarea.id)
    )).all()
    mias = externos.condicion_tarea_propia(CalendarioTarea, current_user) if externo \
        else CalendarioTarea.asignado_a_id == current_user.id
    con_cambios = (await db.execute(
        _consulta_tarjetas().where(
            CalendarioBarra.mundo.in_(mundos),
            CalendarioEntrega.momento == "cambios",
            mias,
        ).order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioTarea.id)
    )).all()
    return {
        "paraRevisar": await _tarjetas(db, para_revisar, current_user),
        "conCambios": await _tarjetas(db, con_cambios, current_user),
    }
