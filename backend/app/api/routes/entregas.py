"""entregas.py — entregas por fases con rondas de corrección (0064).

  PUT    /calendario/tareas/{id}/entregas     — que la tarea lleve entregas: tipo, brief, fases, aprobadores
  DELETE /calendario/tareas/{id}/entregas     — que deje de llevarlas (solo si no se entregó nada)
  GET    /calendario/tareas/{id}/entregas     — todo: fases, rondas, imágenes (los ids), marcas, decisiones
  POST   /calendario/tareas/{id}/versiones    — entregar una ronda (multipart, con las imágenes)
  POST   /calendario/versiones/{id}/decision  — aprobar, aprobar con cambios o pedir cambios
  PATCH  /calendario/marcas/{id}              — tildar (o destildar) una marca como corregida
  GET    /calendario/entregas/imagenes/{id}   — una imagen (?tam=mini|grande)
  GET    /calendario/entregas?mundo=&rev=     — el tablero del mundo, con las métricas de retrabajo
  GET    /calendario/mis-entregas             — lo que espera MI decisión y lo que me devolvieron

Pedido de Ivan (15/11/2026), como tarjetas de Trello con la agencia. La lógica
pura está en app/services/entregas.py; acá están los permisos, que se cuidan
todos del lado del servidor:

- Ve todo esto quien puede abrir el calendario del mundo de la acción. Cuando
  existan las cuentas de agencia (vista limitada), el lugar para restringirlas
  es `_puede_ver`: hoy es lo mismo que ver el calendario.
- Configura (tipo, brief, fases, aprobadores) quien tiene `calendario.tareas`.
- Entrega SOLO el responsable de la tarea (`asignado_a_id`).
- Decide el aprobador al que le toca; quien tiene `calendario.tareas` puede
  decidir por él como respaldo. Nadie decide sobre lo que subió.

Las imágenes NO viajan en /calendario/datos (que se pregunta cada 15 s): ahí va
solo el resumen de cada tarea (en qué fase, a quién le toca). Las imágenes se
piden al abrir la tarea, de a una.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.calendario import (
    _ID, _barra_o_404, _exigir_gestion_de_tareas, _nueva_revision, _puede_gestionar_tareas, _puede_ver_el_mundo,
)
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.mundos import MUNDOS, exigir_mundo, mundos_de
from app.core.rate_limit import limiter
from app.models.calendario import CalendarioBarra, CalendarioRevision, CalendarioRevisionMundo, CalendarioTarea
from app.models.entregas import (
    CalendarioDecision, CalendarioEntrega, CalendarioFase, CalendarioMarca, CalendarioVersion,
    CalendarioVersionImagen,
)
from app.models.user import User
from app.services import entregas as reglas
from app.services.entregas import (
    MAX_BYTES_IMAGEN, MAX_BYTES_MINIATURA, MAX_IMAGENES, MAX_MARCAS, NoPuedeDecidir, FaseExistente,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendario", tags=["calendario-entregas"])

_NO_LLEVA = "Esta tarea no lleva entregas"
# Cuánto se ven las aprobadas en el tablero después de aprobarse.
DIAS_DE_APROBADAS_EN_EL_TABLERO = 30


# ---------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------

def _puede_ver(usuario: User, mundo: str) -> bool:
    """Quién ve las entregas de una tarea. Hoy, quien abre el calendario del
    mundo; cuando haya cuentas de agencia con vista limitada, acá se las
    restringe a sus propias tareas."""
    return _puede_ver_el_mundo(usuario, mundo)


async def _tarea_y_barra(
    db: AsyncSession, tarea_id: str, usuario: User, *, bloquear: bool = False,
) -> tuple[CalendarioTarea, CalendarioBarra]:
    consulta = select(CalendarioTarea).where(CalendarioTarea.id == tarea_id)
    if bloquear:
        consulta = consulta.with_for_update()
    tarea = (await db.execute(consulta)).scalar_one_or_none()
    if tarea is None:
        raise HTTPException(status_code=404, detail="Esta tarea ya no existe: la borró otra persona.")
    barra = await _barra_o_404(db, tarea.barra_id, usuario)
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
    validos = {u.id for u in usuarios if u.is_active and _puede_ver(u, barra.mundo)}
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
            if tarea.asignado_a_id not in (None, current_user.id) and await reglas.avisar(
                db, tarea.asignado_a_id,
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
    aparte (ver `ver_imagen`)."""
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user)
    if not _puede_ver(current_user, barra.mundo):
        raise HTTPException(status_code=403, detail="No podés ver esta tarea")
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
    nombres = await _nombres(db, personas)

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
            "decisiones": [
                {
                    "aprobador": d.aprobador_id, "decididoPor": d.decidido_por_id, "orden": d.orden,
                    "decision": d.decision, "comentario": d.comentario,
                    "fecha": d.created_at.isoformat() if d.created_at else None,
                }
                for d in decisiones.get(v.id, [])
            ],
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
    es_responsable = tarea.asignado_a_id == current_user.id
    return {
        "tarea": {
            "id": tarea.id, "titulo": tarea.titulo, "descripcion": tarea.descripcion, "estado": tarea.estado,
            "asignadoA": tarea.asignado_a_id, "vence": tarea.vence.isoformat() if tarea.vence else None,
            "creadoPor": tarea.creado_por_id,
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
        "puedo": {
            "entregar": es_responsable and entrega.momento in ("produccion", "cambios"),
            "decidir": puede_decidir,
            "comoRespaldo": como_respaldo,
            "configurar": _puede_gestionar_tareas(current_user),
            "tildarMarcas": es_responsable or _puede_gestionar_tareas(current_user),
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
               CalendarioVersionImagen.purgada_at, CalendarioBarra.mundo)
        .join(CalendarioVersion, CalendarioVersion.id == CalendarioVersionImagen.version_id)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioVersion.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .where(CalendarioVersionImagen.id == imagen_id)
    )).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Esa imagen ya no existe")
    tipo, tipo_mini, purgada, mundo = fila
    exigir_mundo(current_user, mundo)
    if not _puede_ver(current_user, mundo):
        raise HTTPException(status_code=403, detail="No podés ver esta imagen")
    columna = CalendarioVersionImagen.miniatura if tam == "mini" else CalendarioVersionImagen.datos
    datos = (await db.execute(select(columna).where(CalendarioVersionImagen.id == imagen_id))).scalar_one_or_none()
    if datos is None:
        raise HTTPException(
            status_code=410,
            detail="La imagen grande se borró (a los 180 días de terminada la acción). Queda la miniatura.",
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
    tarea_id: str,
    versionId: str = Form(..., pattern=_ID),
    comentario: str = Form("", max_length=5000),
    link: str = Form("", max_length=1000),
    corregidas: str = Form("[]", max_length=20_000),
    imagenes: list[UploadFile] = File(...),
    miniaturas: list[UploadFile] = File(...),
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Entrega una ronda de la fase en curso. Solo el responsable de la tarea.
    Va todo en un pedido (las imágenes también): o queda la versión entera, o
    no queda nada."""
    tarea, barra = await _tarea_y_barra(db, tarea_id, current_user, bloquear=True)
    entrega = await _entrega_bloqueada(db, tarea_id)
    if tarea.asignado_a_id != current_user.id:
        raise HTTPException(status_code=403, detail="Entrega solo la persona que tiene asignada la tarea")

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

    if not imagenes:
        raise HTTPException(status_code=422, detail="Subí al menos una imagen")
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
    return {"id": versionId, "rev": rev, "ronda": ronda, "entrega": resumen, "avisados": avisados}


# ---------------------------------------------------------------------------
# Decidir
# ---------------------------------------------------------------------------

class MarcaNueva(BaseModel):
    imagenId: str = Field(..., pattern=_ID)
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    texto: str = Field(..., min_length=1, max_length=1000)

    @field_validator("texto")
    @classmethod
    def _sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Cada marca necesita un texto: qué hay que cambiar")
        return v


class DecisionNueva(BaseModel):
    decision: Literal["aprobada", "aprobada-con-cambios", "cambios"]
    comentario: str | None = Field(None, max_length=5000)
    marcas: list[MarcaNueva] = Field(default_factory=list, max_length=MAX_MARCAS)


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
    tarea, barra = await _tarea_y_barra(db, version.tarea_id, current_user, bloquear=True)
    entrega = await _entrega_bloqueada(db, tarea.id)
    # Con la entrega bloqueada, se vuelve a leer: otro pudo haber decidido.
    await db.refresh(version)
    if version.fase_id != entrega.fase_actual_id:
        raise HTTPException(status_code=409, detail="Esa versión ya no es la que está en revisión: recargá")

    comentario = (payload.comentario or "").strip() or None
    if payload.decision == "aprobada" and payload.marcas:
        raise HTTPException(
            status_code=422,
            detail="Con marcas, elegí «Aprobado con cambios» o «Pedir cambios»: «Aprobar» las perdería",
        )
    if payload.decision != "aprobada" and not payload.marcas and not comentario:
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
    if any(m.imagenId not in ids_imagenes for m in payload.marcas):
        raise HTTPException(status_code=422, detail="Una marca está sobre una imagen que no es de esta versión")

    ahora = datetime.now(timezone.utc)
    db.add(CalendarioDecision(
        version_id=version.id, aprobador_id=aprobador, decidido_por_id=current_user.id, orden=orden,
        decision=payload.decision, comentario=comentario,
    ))
    hay = (await db.execute(
        select(func.coalesce(func.max(CalendarioMarca.numero), 0)).where(CalendarioMarca.version_id == version.id)
    )).scalar_one()
    tipo_marca = "cambio" if payload.decision == "cambios" else "ajuste"
    for i, m in enumerate(payload.marcas, 1):
        db.add(CalendarioMarca(
            id=reglas.nuevo_id("mk"), version_id=version.id, imagen_id=m.imagenId, tarea_id=tarea.id,
            numero=hay + i, x=m.x, y=m.y, texto=m.texto, tipo=tipo_marca, autor_id=current_user.id,
        ))

    resultado = reglas.resultado_de_version(aprobadores, previas + [(aprobador, payload.decision)])
    fase = await db.get(CalendarioFase, version.fase_id)
    if resultado in ("aprobada", "cambios"):
        version.estado = resultado
        version.decidida_at = ahora
    if resultado == "aprobada":
        fase.estado = "aprobada"
        fase.aprobada_at = ahora
    await db.flush()
    await reglas.recalcular(db, entrega, tarea)

    # Los avisos: uno por persona y por decisión, nunca a uno mismo.
    quien = _quien(current_user)
    responsable = tarea.asignado_a_id
    nombres = await _nombres(db, [entrega.aprobador_de_turno_id])
    ajustes = [m.texto for m in payload.marcas] + ([comentario] if comentario and not payload.marcas else [])
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
        if payload.decision == "aprobada-con-cambios":
            await avisar(responsable, reglas.mensaje_de_aprobacion(
                quien, version.ronda, fase.nombre, tarea.titulo, con_cambios=True, ajustes=ajustes,
                siguiente_fase=None, sigue_revisando=nombres.get(siguiente, "el siguiente aprobador"),
                terminada=False,
            ), f"decision-{orden}")
    elif resultado == "cambios":
        await avisar(responsable, reglas.mensaje_de_cambios(
            quien, version.ronda, fase.nombre, tarea.titulo, len(payload.marcas),
        ), "cambios")
    else:
        terminada = entrega.momento == "aprobada"
        siguiente_fase = None
        if not terminada and entrega.fase_actual_id:
            siguiente_fase = (await db.get(CalendarioFase, entrega.fase_actual_id)).nombre
        await avisar(responsable, reglas.mensaje_de_aprobacion(
            quien, version.ronda, fase.nombre, tarea.titulo,
            con_cambios=payload.decision == "aprobada-con-cambios", ajustes=ajustes,
            siguiente_fase=siguiente_fase, sigue_revisando=None, terminada=terminada,
        ), "aprobada")
        if terminada and tarea.creado_por_id != responsable:
            await avisar(tarea.creado_por_id, reglas.mensaje_de_tarea_aprobada(tarea.titulo, barra.nombre), "hecha")

    resumen = await _resumen(db, tarea.id)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": version.id, "rev": rev, "resultado": resultado, "entrega": resumen, "avisados": avisados}


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
    if tarea.asignado_a_id != current_user.id and not _puede_gestionar_tareas(current_user):
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

async def _tarjetas(db: AsyncSession, filas) -> list[dict]:
    """Una tarjeta por tarea con entregas: lo que muestra el tablero (y "Mis
    tareas"), con la miniatura de la última versión."""
    filas = list(filas)
    if not filas:
        return []
    ids = [t.id for _, t, _ in filas]
    resumenes = await reglas.resumenes_de_entregas(db, ids)
    ultimas = {
        tid: vid for tid, vid in (await db.execute(
            select(CalendarioVersion.tarea_id, CalendarioVersion.id)
            .where(CalendarioVersion.tarea_id.in_(ids))
            .distinct(CalendarioVersion.tarea_id)
            .order_by(CalendarioVersion.tarea_id, CalendarioVersion.created_at.desc())
        )).all()
    }
    miniaturas = {
        vid: iid for vid, iid in (await db.execute(
            select(CalendarioVersionImagen.version_id, CalendarioVersionImagen.id)
            .where(CalendarioVersionImagen.version_id.in_(list(ultimas.values()) or [""]),
                   CalendarioVersionImagen.orden == 0)
        )).all()
    }
    nombres = await _nombres(db, [t.asignado_a_id for _, t, _ in filas] + [e.aprobador_de_turno_id for e, _, _ in filas])
    return [
        {
            "tareaId": t.id, "titulo": t.titulo, "estado": t.estado, "vence": t.vence.isoformat() if t.vence else None,
            "asignadoA": t.asignado_a_id, "responsable": nombres.get(t.asignado_a_id),
            "turno": nombres.get(e.aprobador_de_turno_id),
            "accion": {
                "id": b.id, "mundo": b.mundo, "nombre": b.nombre, "color": b.color,
                "desde": b.desde.isoformat(), "hasta": b.hasta.isoformat(),
            },
            "entrega": resumenes.get(t.id),
            "miniatura": miniaturas.get(ultimas.get(t.id)),
            "actualizada": (e.updated_at or e.created_at).isoformat() if (e.updated_at or e.created_at) else None,
        }
        for e, t, b in filas
    ]


def _consulta_tarjetas():
    return (
        select(CalendarioEntrega, CalendarioTarea, CalendarioBarra)
        .join(CalendarioTarea, CalendarioTarea.id == CalendarioEntrega.tarea_id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
    )


async def _metricas(db: AsyncSession, usuario: User, mundo: str, dias: int) -> dict:
    """El retrabajo de las fases aprobadas en los últimos `dias` días: del
    mundo que se mira (total, por tipo de pieza y por responsable) y la
    comparación entre los mundos que la persona puede abrir."""
    mundos = mundos_de(usuario)
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    filas = (await db.execute(
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
    )).all()
    del_mundo = reglas.metricas_de_retrabajo([tuple(f) for f in filas if f[2] == mundo])
    todos = reglas.metricas_de_retrabajo([tuple(f) for f in filas])
    nombres = await _nombres(db, [g["clave"] for g in del_mundo["porResponsable"]])
    for g in del_mundo["porResponsable"]:
        g["nombre"] = nombres.get(g["clave"], "Alguien que ya no está")
    for g in del_mundo["porTipo"]:
        g["nombre"] = reglas.TIPOS_DE_PIEZA.get(g["clave"], g["clave"])
    por_mundo = [{**g, "nombre": MUNDOS.get(g["clave"], g["clave"])} for g in todos["porMundo"]]
    return {**del_mundo, "porMundo": por_mundo, "dias": dias}


@router.get("/entregas")
async def tablero(
    mundo: str,
    rev: int | None = None,
    dias: int = 90,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """El tablero de entregas de un mundo: una tarjeta por tarea con entregas
    (las aprobadas, solo las de los últimos 30 días) y las métricas de
    retrabajo. Como /datos, si nada de este mundo cambió desde `rev`,
    contesta "sin cambios" y no viaja nada más: el tablero pregunta cada 15 s."""
    exigir_mundo(current_user, mundo)
    if not (7 <= dias <= 730):
        raise HTTPException(status_code=422, detail="El período va de 7 a 730 días")
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

    desde = datetime.now(timezone.utc) - timedelta(days=DIAS_DE_APROBADAS_EN_EL_TABLERO)
    filas = (await db.execute(
        _consulta_tarjetas().where(
            CalendarioBarra.mundo == mundo,
            or_(
                CalendarioEntrega.momento != "aprobada",
                func.coalesce(CalendarioEntrega.updated_at, CalendarioEntrega.created_at) >= desde,
            ),
        ).order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioBarra.desde, CalendarioTarea.id)
    )).all()
    return {
        "rev": actual,
        "mundo": mundo,
        "tarjetas": await _tarjetas(db, filas),
        "metricas": await _metricas(db, current_user, mundo, dias),
    }


@router.get("/mis-entregas")
async def mis_entregas(
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Para "Mis tareas", en todos los mundos de la persona: lo que espera MI
    decisión (soy el aprobador de turno) y lo que me devolvieron con cambios
    (soy el responsable y le toca a la agencia otra ronda)."""
    mundos = mundos_de(current_user)
    para_revisar = (await db.execute(
        _consulta_tarjetas().where(
            CalendarioBarra.mundo.in_(mundos),
            CalendarioEntrega.momento == "revision",
            CalendarioEntrega.aprobador_de_turno_id == current_user.id,
        ).order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioTarea.id)
    )).all()
    con_cambios = (await db.execute(
        _consulta_tarjetas().where(
            CalendarioBarra.mundo.in_(mundos),
            CalendarioEntrega.momento == "cambios",
            CalendarioTarea.asignado_a_id == current_user.id,
        ).order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioTarea.id)
    )).all()
    return {
        "paraRevisar": await _tarjetas(db, para_revisar),
        "conCambios": await _tarjetas(db, con_cambios),
    }
