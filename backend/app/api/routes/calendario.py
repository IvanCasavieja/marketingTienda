"""calendario.py — el calendario comercial, el de Retail Media y los headers.

  GET    /calendario/datos?rev=N              — todo, o "sin cambios" si sigue en la N
  GET    /calendario/personas                 — a quién se le puede mandar un aviso
  POST   /calendario/barras                   — una acción, campaña o banner nuevo
  PATCH  /calendario/barras/{id}              — cambia solo los campos que manda
  DELETE /calendario/barras/{id}
  POST   /calendario/barras/{id}/piezas       — agrega una pieza a una acción
  PATCH  /calendario/piezas/{id}              — estado, fecha u hora de una pieza
  DELETE /calendario/piezas/{id}
  POST   /calendario/barras/{id}/avisos       — configura un aviso en una acción
  DELETE /calendario/avisos/{id}
  PUT    /calendario/posiciones-rm/{clave}    — mueve las posiciones de RM de un mes

Hasta el 28/09/2026 había un solo PUT que subía el mes entero: una acción no
podía cruzar de mes, y dos personas editando el mismo mes se pisaban (ganaba
el último que guardaba). Ahora cada cambio toca solo lo suyo: si una persona le
cambia el nombre a una acción mientras otra le mueve las fechas, quedan las dos
cosas; si dos mueven el estado de dos piezas distintas, también.

Cada escritura sube `calendario_revision` en la misma transacción. El front
pregunta cada tanto si la revisión cambió y, si cambió, trae todo: así ve lo
que hicieron los demás sin recargar la página.
"""
import logging
import re
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import client_ip as _client_ip, require_permission
from app.models.audit_log import AuditLog
from app.models.calendario import (
    CalendarioAviso, CalendarioBarra, CalendarioPieza, CalendarioPosicionesRM, CalendarioRevision,
)
from app.models.notificacion import Notificacion
from app.models.user import User
from app.services.calendario_avisos import puede_ver_el_calendario, revisar_avisos

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendario", tags=["calendario"])

_CLAVE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_ID = r"^[A-Za-z0-9_-]{1,64}$"
_HORA = r"^([01]\d|2[0-3]):[0-5]\d$"
# Una barra de más de esto es casi seguro un error de tipeo en el año.
_DURACION_MAXIMA = timedelta(days=3 * 366)
_RM_POR_DEFECTO = [4, 5, 6]

Seccion = Literal["comercial", "retail", "header"]
Area = Literal["web-home", "web-landing", "fisico", "email", "whatsapp", "push"]
Estado = Literal["pendiente", "en-proceso", "aprobado", "publicado"]

_YA_NO_EXISTE = "Esta acción ya no existe: la borró otra persona. Se recargó el calendario."


def _validar_clave(clave: str) -> str:
    if not _CLAVE.match(clave):
        raise HTTPException(status_code=422, detail="El mes se escribe 'YYYY-MM'")
    return clave


def _validar_rango(desde: date, hasta: date) -> None:
    if hasta < desde:
        raise HTTPException(status_code=422, detail="La fecha de fin no puede ser anterior a la de inicio")
    if hasta - desde > _DURACION_MAXIMA:
        raise HTTPException(status_code=422, detail="Dura más de tres años: revisá el año de las fechas")


async def _nueva_revision(db: AsyncSession) -> int:
    """Sube el contador en la misma transacción que el cambio: quien pregunte
    ve la revisión nueva recién cuando el cambio ya está guardado."""
    rev = (await db.execute(
        update(CalendarioRevision).where(CalendarioRevision.id == 1)
        .values(rev=CalendarioRevision.rev + 1).returning(CalendarioRevision.rev)
    )).scalar_one_or_none()
    if rev is None:
        # Una base donde la fila no existe (no debería pasar: la crea la 0057).
        db.add(CalendarioRevision(id=1, rev=1))
        rev = 1
    return rev


async def _revision_actual(db: AsyncSession) -> int:
    return (await db.execute(
        select(CalendarioRevision.rev).where(CalendarioRevision.id == 1)
    )).scalar_one_or_none() or 0


async def _avisar_sin_romper(db: AsyncSession, barra_id: str) -> int:
    """Manda en el momento los avisos de una acción que ya tocan. Se corre
    DESPUÉS de guardar el cambio: si esto falla, el cambio igual quedó, así que
    no puede terminar en un 500 que le diga a la persona "no se guardó". El
    loop de cada 6 horas lo vuelve a intentar."""
    try:
        return await revisar_avisos(db, barra_id=barra_id)
    except Exception as exc:
        logger.error("calendario: no se pudieron mandar los avisos de %s: %s", barra_id, exc, exc_info=True)
        await db.rollback()
        return 0


async def _barra_o_404(db: AsyncSession, barra_id: str, *, bloquear: bool = False) -> CalendarioBarra:
    consulta = select(CalendarioBarra).where(CalendarioBarra.id == barra_id)
    if bloquear:
        consulta = consulta.with_for_update()
    barra = (await db.execute(consulta)).scalar_one_or_none()
    if barra is None:
        raise HTTPException(status_code=404, detail=_YA_NO_EXISTE)
    return barra


# ---------------------------------------------------------------------------
# Lo que viaja
# ---------------------------------------------------------------------------

def _pieza_json(p: CalendarioPieza) -> dict:
    out = {"id": p.id, "area": p.area, "formato": p.formato, "estado": p.estado}
    if p.desde is not None:
        out["desde"] = p.desde.isoformat()
    if p.hasta is not None:
        out["hasta"] = p.hasta.isoformat()
    if p.hora:
        out["hora"] = p.hora
    if p.en_sharepoint:
        out["enSharePoint"] = True
    return out


def _aviso_json(a: CalendarioAviso) -> dict:
    return {
        "id": a.id,
        "diasAntes": a.dias_antes,
        "destinatarios": list(a.destinatarios or []),
        "creadoPor": a.creado_por_id,
    }


def _barra_json(b: CalendarioBarra, piezas: list[CalendarioPieza], avisos: list[CalendarioAviso]) -> dict:
    out = {
        "id": b.id,
        "seccion": b.seccion,
        "banda": b.banda,
        "carril": b.carril,
        "nombre": b.nombre,
        "color": b.color,
        "desde": b.desde.isoformat(),
        "hasta": b.hasta.isoformat(),
    }
    if b.seccion == "comercial":
        out["piezas"] = [_pieza_json(p) for p in piezas]
        out["avisos"] = [_aviso_json(a) for a in avisos]
    return out


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

@router.get("/datos")
async def traer_datos(
    rev: int | None = None,
    _: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Todo el calendario. Si el front ya tiene la revisión actual, contesta
    solo eso y no viaja nada más.

    La revisión se lee ANTES que los datos: si alguien guarda en el medio, los
    datos pueden venir un poco más nuevos que la revisión (y la próxima
    pregunta los vuelve a traer), pero nunca más viejos."""
    actual = await _revision_actual(db)
    if rev is not None and rev == actual:
        return {"rev": actual, "sinCambios": True}

    barras = (await db.execute(
        select(CalendarioBarra).order_by(CalendarioBarra.desde, CalendarioBarra.id)
    )).scalars().all()
    piezas: dict[str, list[CalendarioPieza]] = {}
    for p in (await db.execute(
        select(CalendarioPieza).order_by(CalendarioPieza.orden, CalendarioPieza.id)
    )).scalars():
        piezas.setdefault(p.barra_id, []).append(p)
    avisos: dict[str, list[CalendarioAviso]] = {}
    for a in (await db.execute(
        select(CalendarioAviso).order_by(CalendarioAviso.dias_antes.desc(), CalendarioAviso.id)
    )).scalars():
        avisos.setdefault(a.barra_id, []).append(a)
    posiciones = {
        p.clave: list(p.posiciones)
        for p in (await db.execute(select(CalendarioPosicionesRM))).scalars()
    }
    return {
        "rev": actual,
        "barras": [_barra_json(b, piezas.get(b.id, []), avisos.get(b.id, [])) for b in barras],
        "posicionesRM": posiciones,
    }


@router.get("/personas")
async def listar_personas(
    _: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Quiénes pueden recibir un aviso: los que pueden abrir el calendario.
    Solo id y nombre."""
    usuarios = (await db.execute(
        select(User).where(User.is_active == True).order_by(User.full_name)  # noqa: E712
    )).scalars()
    return [
        {"id": u.id, "nombre": u.full_name or u.email}
        for u in usuarios if puede_ver_el_calendario(u)
    ]


# ---------------------------------------------------------------------------
# Barras
# ---------------------------------------------------------------------------

class BarraNueva(BaseModel):
    id: str = Field(..., pattern=_ID)
    seccion: Seccion
    banda: str = Field(..., min_length=1, max_length=200)
    carril: int = Field(0, ge=0, le=500)
    nombre: str = Field(..., min_length=1, max_length=1000)
    color: str | None = Field(None, max_length=32)
    desde: date
    hasta: date

    @field_validator("nombre")
    @classmethod
    def _sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede quedar vacío")
        return v


class BarraCambios(BaseModel):
    """Solo viaja lo que cambió, y solo eso se escribe."""
    banda: str | None = Field(None, min_length=1, max_length=200)
    carril: int | None = Field(None, ge=0, le=500)
    nombre: str | None = Field(None, min_length=1, max_length=1000)
    color: str | None = Field(None, max_length=32)
    desde: date | None = None
    hasta: date | None = None

    @field_validator("nombre")
    @classmethod
    def _sin_espacios(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede quedar vacío")
        return v


@router.post("/barras", status_code=201)
async def crear_barra(
    payload: BarraNueva,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    _validar_rango(payload.desde, payload.hasta)
    existente = (await db.execute(
        select(CalendarioBarra.id).where(CalendarioBarra.id == payload.id)
    )).scalar_one_or_none()
    if existente is not None:
        # El id lo genera el front: si ya está, es un reintento del mismo alta.
        # `yaExistia` le dice al front que esta revisión NO es la suya.
        return {"id": payload.id, "rev": await _revision_actual(db), "yaExistia": True}
    db.add(CalendarioBarra(
        **payload.model_dump(),
        creado_por_id=current_user.id,
        actualizado_por_id=current_user.id,
    ))
    rev = await _nueva_revision(db)
    await db.commit()
    return {"id": payload.id, "rev": rev}


@router.patch("/barras/{barra_id}")
async def cambiar_barra(
    barra_id: str,
    payload: BarraCambios,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    barra = await _barra_o_404(db, barra_id, bloquear=True)
    cambios = {k: getattr(payload, k) for k in payload.model_fields_set}
    if "nombre" in cambios and cambios["nombre"] is None:
        raise HTTPException(status_code=422, detail="El nombre no puede quedar vacío")
    for campo in ("banda", "carril", "desde", "hasta"):
        if campo in cambios and cambios[campo] is None:
            del cambios[campo]
    desde = cambios.get("desde", barra.desde)
    hasta = cambios.get("hasta", barra.hasta)
    _validar_rango(desde, hasta)
    cambio_la_fecha = desde != barra.desde
    for campo, valor in cambios.items():
        setattr(barra, campo, valor)
    barra.actualizado_por_id = current_user.id
    rev = await _nueva_revision(db)
    await db.commit()
    if cambio_la_fecha:
        # Un aviso que con la fecha nueva ya tendría que haber salido, sale ya.
        await _avisar_sin_romper(db, barra_id)
    return {"id": barra_id, "rev": rev}


@router.delete("/barras/{barra_id}")
async def borrar_barra(
    barra_id: str,
    request: Request,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    barra = (await db.execute(
        select(CalendarioBarra).where(CalendarioBarra.id == barra_id).with_for_update()
    )).scalar_one_or_none()
    if barra is None:
        # Ya la había borrado otro: el resultado es el mismo.
        return {"id": barra_id, "borrada": True}
    # Queda quién la borró y qué era: con varias personas en el mismo
    # calendario, "¿quién sacó tal acción?" es la pregunta que va a aparecer.
    db.add(AuditLog(
        user_id=current_user.id, action="calendario.borrar", resource="calendario_barra",
        resource_id=barra_id, ip_address=_client_ip(request),
        details={
            "seccion": barra.seccion, "banda": barra.banda, "nombre": barra.nombre,
            "desde": barra.desde.isoformat(), "hasta": barra.hasta.isoformat(),
        },
    ))
    await db.delete(barra)
    rev = await _nueva_revision(db)
    await db.commit()
    return {"id": barra_id, "borrada": True, "rev": rev}


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------

class PiezaNueva(BaseModel):
    id: str = Field(..., pattern=_ID)
    area: Area
    formato: str = Field(..., min_length=1, max_length=100)
    estado: Estado = "pendiente"
    desde: date | None = None
    hasta: date | None = None
    hora: str | None = Field(None, pattern=_HORA)


class PiezaCambios(BaseModel):
    estado: Estado | None = None
    desde: date | None = None
    hasta: date | None = None
    hora: str | None = Field(None, pattern=_HORA)
    enSharePoint: bool | None = None


@router.post("/barras/{barra_id}/piezas", status_code=201)
async def agregar_pieza(
    barra_id: str,
    payload: PiezaNueva,
    _: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    # Bloquear la acción ordena a dos personas agregando piezas a la vez: la
    # segunda ve la pieza de la primera y no la duplica.
    barra = await _barra_o_404(db, barra_id, bloquear=True)
    if barra.seccion != "comercial":
        raise HTTPException(status_code=422, detail="Solo las acciones del calendario comercial llevan piezas")
    piezas = (await db.execute(
        select(CalendarioPieza).where(CalendarioPieza.barra_id == barra_id)
    )).scalars().all()
    igual = next((p for p in piezas if p.id == payload.id or
                  (p.area == payload.area and p.formato == payload.formato)), None)
    if igual is not None:
        # Otra persona la agregó primero (o es un reintento). El front tiene
        # que traer todo: su copia local puede tener otro id para esta pieza.
        return {"id": igual.id, "rev": await _revision_actual(db), "yaExistia": True}
    db.add(CalendarioPieza(
        id=payload.id, barra_id=barra_id, area=payload.area, formato=payload.formato,
        estado=payload.estado, desde=payload.desde, hasta=payload.hasta, hora=payload.hora,
        orden=max((p.orden for p in piezas), default=-1) + 1,
    ))
    rev = await _nueva_revision(db)
    await db.commit()
    return {"id": payload.id, "rev": rev}


@router.patch("/piezas/{pieza_id}")
async def cambiar_pieza(
    pieza_id: str,
    payload: PiezaCambios,
    _: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    pieza = (await db.execute(
        select(CalendarioPieza).where(CalendarioPieza.id == pieza_id).with_for_update()
    )).scalar_one_or_none()
    if pieza is None:
        raise HTTPException(status_code=404, detail="Esta pieza ya no existe: la sacó otra persona.")
    # `desde`, `hasta` y `hora` pueden venir en null a propósito (volver a "con
    # la acción"), por eso se mira qué campos vinieron y no si son None.
    campos = payload.model_fields_set
    if "estado" in campos and payload.estado is not None:
        pieza.estado = payload.estado
    if "desde" in campos:
        pieza.desde = payload.desde
    if "hasta" in campos:
        pieza.hasta = payload.hasta
    if "hora" in campos:
        pieza.hora = payload.hora
    if "enSharePoint" in campos and payload.enSharePoint is not None:
        pieza.en_sharepoint = payload.enSharePoint
    rev = await _nueva_revision(db)
    await db.commit()
    return {"id": pieza_id, "rev": rev}


@router.delete("/piezas/{pieza_id}")
async def quitar_pieza(
    pieza_id: str,
    _: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(CalendarioPieza).where(CalendarioPieza.id == pieza_id))
    rev = await _nueva_revision(db)
    await db.commit()
    return {"id": pieza_id, "borrada": True, "rev": rev}


# ---------------------------------------------------------------------------
# Avisos
# ---------------------------------------------------------------------------

class AvisoNuevo(BaseModel):
    id: str = Field(..., pattern=_ID)
    diasAntes: int = Field(..., ge=1, le=365)
    destinatarios: list[int] = Field(..., min_length=1, max_length=200)


@router.post("/barras/{barra_id}/avisos", status_code=201)
async def configurar_aviso(
    barra_id: str,
    payload: AvisoNuevo,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Un aviso configurado a mano. No hay ninguno por defecto: "cuando nos
    llegue una notificación, es porque alguien la configuró"."""
    barra = await _barra_o_404(db, barra_id)
    if barra.seccion != "comercial":
        raise HTTPException(status_code=422, detail="Los avisos se configuran en las acciones del calendario comercial")

    pedidos = list(dict.fromkeys(payload.destinatarios))
    usuarios = (await db.execute(select(User).where(User.id.in_(pedidos)))).scalars().all()
    validos = {u.id for u in usuarios if puede_ver_el_calendario(u)}
    faltan = [uid for uid in pedidos if uid not in validos]
    if faltan:
        raise HTTPException(
            status_code=422,
            detail="Hay personas elegidas que no pueden abrir el calendario: no les llegaría el aviso",
        )

    existente = (await db.execute(
        select(CalendarioAviso.id).where(CalendarioAviso.id == payload.id)
    )).scalar_one_or_none()
    if existente is None:
        db.add(CalendarioAviso(
            id=payload.id, barra_id=barra_id, dias_antes=payload.diasAntes,
            destinatarios=pedidos, creado_por_id=current_user.id,
        ))
    rev = await _nueva_revision(db)
    await db.commit()
    # Si la fecha del aviso ya pasó (10 días antes de algo que arranca en 5),
    # sale ahora y no en la próxima vuelta del loop.
    enviados = await _avisar_sin_romper(db, barra_id)
    return {"id": payload.id, "rev": rev, "enviadosAhora": enviados}


@router.delete("/avisos/{aviso_id}")
async def quitar_aviso(
    aviso_id: str,
    _: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(CalendarioAviso).where(CalendarioAviso.id == aviso_id))
    rev = await _nueva_revision(db)
    await db.commit()
    return {"id": aviso_id, "borrado": True, "rev": rev}


# ---------------------------------------------------------------------------
# Posiciones de Retail Media en el header
# ---------------------------------------------------------------------------

class PosicionesRM(BaseModel):
    posiciones: list[int] = Field(..., min_length=1, max_length=10)

    @field_validator("posiciones")
    @classmethod
    def _validas(cls, v: list[int]) -> list[int]:
        if any(p < 1 or p > 10 for p in v):
            raise ValueError("Las posiciones van de la 1 a la 10")
        if len(set(v)) != len(v):
            raise ValueError("Una posición no puede estar dos veces")
        return v


@router.put("/posiciones-rm/{clave}")
async def mover_posiciones_rm(
    clave: str,
    payload: PosicionesRM,
    request: Request,
    current_user: User = Depends(require_permission("calendario.retail_media")),
    db: AsyncSession = Depends(get_db),
):
    """Guarda las posiciones de RM de un mes y le avisa a quien lleva Retail
    Media, menos al que las movió — avisarse a uno mismo es ruido.

    Antes esto eran dos llamadas: el PUT del mes entero (que pedía
    `calendario.edit`) y el aviso (que pedía `calendario.retail_media`), así
    que alguien con solo el permiso de RM movía las posiciones y no se
    guardaban."""
    _validar_clave(clave)
    fila = (await db.execute(
        select(CalendarioPosicionesRM).where(CalendarioPosicionesRM.clave == clave).with_for_update()
    )).scalar_one_or_none()
    antes = list(fila.posiciones) if fila else list(_RM_POR_DEFECTO)
    ahora = payload.posiciones
    if antes == ahora:
        return {"clave": clave, "avisados": 0}
    if fila is None:
        db.add(CalendarioPosicionesRM(clave=clave, posiciones=ahora, actualizado_por_id=current_user.id))
    else:
        fila.posiciones = ahora
        fila.actualizado_por_id = current_user.id

    usuarios = (await db.execute(select(User).where(User.is_active == True))).scalars()  # noqa: E712
    destinatarios = [
        u for u in usuarios
        if u.id != current_user.id
        and (u.is_superuser or "calendario.retail_media" in (u.permissions or []))
    ]
    mensaje = (
        f"{current_user.full_name} movió las posiciones de Retail Media en "
        f"{clave}: {', '.join(map(str, antes)) or '—'} → {', '.join(map(str, ahora)) or '—'}"
    )
    ref = f"{clave}:{'-'.join(map(str, ahora))}"
    for usuario in destinatarios:
        db.add(Notificacion(
            user_id=usuario.id,
            tipo="calendario_header",
            mensaje=mensaje,
            origen_tipo="calendario_header",
            origen_ref=ref,
        ))
    db.add(AuditLog(
        user_id=current_user.id, action="calendario.posiciones_rm", resource="calendario_posiciones_rm",
        resource_id=clave, details={"antes": antes, "ahora": ahora},
        ip_address=_client_ip(request),
    ))
    rev = await _nueva_revision(db)
    await db.commit()
    return {"clave": clave, "avisados": len(destinatarios), "rev": rev}
