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
  POST   /calendario/barras/{id}/tareas       — una tarea (o subtarea) de una acción
  PATCH  /calendario/tareas/{id}              — título, estado, a quién, cuándo vence
  DELETE /calendario/tareas/{id}
  GET    /calendario/mis-tareas               — lo que tengo asignado, de todos mis mundos
  GET    /calendario/ubicar/{id}              — en qué mundo está una acción
  PUT    /calendario/plantillas/{id}          — crea o reemplaza una plantilla de tareas
  DELETE /calendario/plantillas/{id}
  POST   /calendario/barras/{id}/plantilla    — crea en una acción las tareas de una plantilla

Las plantillas (0064) viajan con /datos, como todo lo del mundo: guardar una
sube la revisión y los demás la ven aparecer sola.

Desde la 0060 la plataforma entera se divide en MUNDOS (Tienda Inglesa,
Redexpres...) y cada uno tiene su calendario: cada barra es de un mundo,
`GET /datos?mundo=` trae solo ese, y nadie lee ni escribe en un mundo al que no
entra (`users.mundos`, ver app/core/mundos.py).

Hasta el 28/09/2026 había un solo PUT que subía el mes entero: una acción no
podía cruzar de mes, y dos personas editando el mismo mes se pisaban (ganaba
el último que guardaba). Ahora cada cambio toca solo lo suyo: si una persona le
cambia el nombre a una acción mientras otra le mueve las fechas, quedan las dos
cosas; si dos mueven el estado de dos piezas distintas, también.

Cada escritura sube `calendario_revision` en la misma transacción. El front
pregunta cada tanto si la revisión cambió y, si cambió, trae todo: así ve lo
que hicieron los demás sin recargar la página.

Los envíos sueltos (0058) son barras de la sección 'envio': un mailing, un
WhatsApp o una push sin una acción detrás. Van por las mismas rutas de barras,
con el canal en `banda`, un solo día (`desde` = `hasta`) y su formato, hora y
estado; y aceptan avisos, como una acción.
"""
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import client_ip as _client_ip, require_permission
from app.core.mundos import MUNDO_POR_DEFECTO, MUNDOS, exigir_mundo, mundos_de, puede_abrir
from app.models.audit_log import AuditLog
from app.models.calendario import (
    CalendarioAviso, CalendarioBarra, CalendarioPieza, CalendarioPlantilla, CalendarioPosicionesRM,
    CalendarioRevision, CalendarioRevisionMundo,
    CalendarioTarea,
)
from app.models.notificacion import Notificacion
from app.models.user import User
from app.services.calendario_avisos import SIN_CATEGORIA, puede_ver_el_calendario, revisar_avisos

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendario", tags=["calendario"])

_CLAVE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_ID = r"^[A-Za-z0-9_-]{1,64}$"
_HORA = r"^([01]\d|2[0-3]):[0-5]\d$"
# Una barra de más de esto es casi seguro un error de tipeo en el año.
_DURACION_MAXIMA = timedelta(days=3 * 366)
_RM_POR_DEFECTO = [4, 5, 6]
# Una fecha fuera de esto es un error de tipeo: el campo de fecha del
# navegador manda el año a medida que se escribe (0002, 0020, 0202...).
_ANIO_MINIMO, _ANIO_MAXIMO = 2000, 2100


def _fecha_razonable(v: date) -> date:
    if not (_ANIO_MINIMO <= v.year <= _ANIO_MAXIMO):
        raise ValueError(f"La fecha {v.strftime('%d/%m/%Y')} no parece real: revisá el año")
    return v


# Toda fecha que llega del front pasa por acá.
Fecha = Annotated[date, AfterValidator(_fecha_razonable)]

Seccion = Literal["comercial", "retail", "header", "envio"]
Area = Literal["web-home", "web-landing", "fisico", "email", "whatsapp", "push"]
Estado = Literal["pendiente", "en-proceso", "aprobado", "publicado"]
# Los canales de un envío suelto: lo que va en `banda`.
_CANALES = ("email", "whatsapp", "push")
# Las secciones cuya ficha lleva avisos.
_CON_AVISOS = ("comercial", "envio")
EstadoTarea = Literal["pendiente", "en-proceso", "hecha"]
# Tarea → subtarea → sub-subtarea, y no más hondo.
_NIVELES_DE_TAREA = 3
PERMISO_TAREAS = "calendario.tareas"

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


async def _nueva_revision(db: AsyncSession, mundo: str | None) -> int:
    """Sube el contador en la misma transacción que el cambio: quien pregunte
    ve la revisión nueva recién cuando el cambio ya está guardado.

    Y anota que esa revisión tocó `mundo` (0063): quien mira otro mundo sigue
    "sin cambios". Sin mundo (algo que colgaba de una acción que ya no está)
    se anota en todos, por las dudas."""
    rev = (await db.execute(
        update(CalendarioRevision).where(CalendarioRevision.id == 1)
        .values(rev=CalendarioRevision.rev + 1).returning(CalendarioRevision.rev)
    )).scalar_one_or_none()
    if rev is None:
        # Una base donde la fila no existe (no debería pasar: la crea la 0057).
        db.add(CalendarioRevision(id=1, rev=1))
        rev = 1
    if mundo is None:
        await db.execute(update(CalendarioRevisionMundo).values(rev=rev))
    else:
        await db.execute(
            pg_insert(CalendarioRevisionMundo).values(mundo=mundo, rev=rev)
            .on_conflict_do_update(index_elements=[CalendarioRevisionMundo.mundo], set_={"rev": rev})
        )
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


async def _barra_o_404(
    db: AsyncSession, barra_id: str, usuario: User, *, bloquear: bool = False,
) -> CalendarioBarra:
    """La barra, si existe y es de un mundo que la persona puede abrir."""
    consulta = select(CalendarioBarra).where(CalendarioBarra.id == barra_id)
    if bloquear:
        consulta = consulta.with_for_update()
    barra = (await db.execute(consulta)).scalar_one_or_none()
    if barra is None:
        raise HTTPException(status_code=404, detail=_YA_NO_EXISTE)
    exigir_mundo(usuario, barra.mundo)
    return barra


async def _exigir_mundo_de(db: AsyncSession, barra_id: str | None, usuario: User) -> str | None:
    """Para lo que se toca por su propio id (una pieza, un aviso): que la
    acción de la que cuelga sea de un mundo de la persona. Si la acción ya no
    está, no hay nada que cuidar. Devuelve el mundo (para la revisión)."""
    if barra_id is None:
        return None
    mundo = (await db.execute(
        select(CalendarioBarra.mundo).where(CalendarioBarra.id == barra_id)
    )).scalar_one_or_none()
    if mundo is not None:
        exigir_mundo(usuario, mundo)
    return mundo


def _puede_ver_el_mundo(usuario: User, mundo: str) -> bool:
    return puede_ver_el_calendario(usuario) and puede_abrir(usuario, mundo)


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


def _tarea_json(t: CalendarioTarea) -> dict:
    out = {
        "id": t.id,
        "parentId": t.parent_id,
        "titulo": t.titulo,
        "descripcion": t.descripcion,
        "estado": t.estado,
        "asignadoA": t.asignado_a_id,
        "vence": t.vence.isoformat() if t.vence else None,
        "creadoPor": t.creado_por_id,
    }
    # Solo las que vinieron de una plantilla: /datos viaja entero cada vez que
    # algo cambia, y tres null por tarea en todas las demás no dicen nada.
    if t.ancla is not None and t.ancla_dias is not None:
        out["ancla"] = t.ancla
        out["anclaDias"] = t.ancla_dias
    if t.plantilla_id:
        out["plantillaId"] = t.plantilla_id
    return out


def _plantilla_json(p: CalendarioPlantilla) -> dict:
    return {
        "id": p.id,
        "mundo": p.mundo,
        "nombre": p.nombre,
        "categoria": p.categoria,
        "tareas": list(p.tareas or []),
    }


def _barra_json(
    b: CalendarioBarra, piezas: list[CalendarioPieza], avisos: list[CalendarioAviso],
    tareas: list[CalendarioTarea] | None = None,
) -> dict:
    out = {
        "id": b.id,
        "mundo": b.mundo,
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
    if b.seccion == "envio":
        out["formato"] = b.formato
        out["estado"] = b.estado or "pendiente"
        if b.hora:
            out["hora"] = b.hora
    if b.seccion in _CON_AVISOS:
        out["avisos"] = [_aviso_json(a) for a in avisos]
        out["tareas"] = [_tarea_json(t) for t in (tareas or [])]
    return out


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

@router.get("/datos")
async def traer_datos(
    rev: int | None = None,
    mundo: str = MUNDO_POR_DEFECTO,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Todo el calendario de UN mundo. Si el front ya tiene la revisión actual,
    contesta solo eso y no viaja nada más.

    El contador es uno solo para todos los mundos, pero cada mundo anota la
    última revisión que lo tocó (0063): si nada de ESTE mundo cambió después
    de la revisión del front, es "sin cambios" aunque en otro mundo sí haya
    habido. Antes un cambio en Redexpres le hacía bajar todo de nuevo a quien
    miraba Tienda Inglesa. Una revisión más nueva que el contador (una base
    restaurada) se trata como vieja: se trae todo.

    La revisión se lee ANTES que los datos: si alguien guarda en el medio, los
    datos pueden venir un poco más nuevos que la revisión (y la próxima
    pregunta los vuelve a traer), pero nunca más viejos."""
    exigir_mundo(current_user, mundo)
    fila = (await db.execute(
        select(
            CalendarioRevision.rev,
            select(CalendarioRevisionMundo.rev)
            .where(CalendarioRevisionMundo.mundo == mundo).scalar_subquery(),
        ).where(CalendarioRevision.id == 1)
    )).first()
    actual = fila[0] if fila else 0
    # Un mundo sin fila (uno nuevo, antes de su primer cambio): como antes, solo la revisión exacta.
    ultima_del_mundo = fila[1] if fila and fila[1] is not None else actual
    if rev is not None and ultima_del_mundo <= rev <= actual:
        return {"rev": actual, "sinCambios": True}

    barras = (await db.execute(
        select(CalendarioBarra).where(CalendarioBarra.mundo == mundo)
        .order_by(CalendarioBarra.desde, CalendarioBarra.id)
    )).scalars().all()
    del_mundo = select(CalendarioBarra.id).where(CalendarioBarra.mundo == mundo)
    piezas: dict[str, list[CalendarioPieza]] = {}
    for p in (await db.execute(
        select(CalendarioPieza).where(CalendarioPieza.barra_id.in_(del_mundo))
        .order_by(CalendarioPieza.orden, CalendarioPieza.id)
    )).scalars():
        piezas.setdefault(p.barra_id, []).append(p)
    avisos: dict[str, list[CalendarioAviso]] = {}
    for a in (await db.execute(
        select(CalendarioAviso).where(CalendarioAviso.barra_id.in_(del_mundo))
        .order_by(CalendarioAviso.dias_antes.desc(), CalendarioAviso.id)
    )).scalars():
        avisos.setdefault(a.barra_id, []).append(a)
    tareas: dict[str, list[CalendarioTarea]] = {}
    for t in (await db.execute(
        select(CalendarioTarea).where(CalendarioTarea.barra_id.in_(del_mundo))
        .order_by(CalendarioTarea.orden, CalendarioTarea.created_at, CalendarioTarea.id)
    )).scalars():
        tareas.setdefault(t.barra_id, []).append(t)
    # Retail Media es de la web de Tienda Inglesa: los otros mundos no tienen
    # esa parte del calendario y no tienen por qué bajar sus posiciones.
    posiciones = {
        p.clave: list(p.posiciones)
        for p in (await db.execute(select(CalendarioPosicionesRM))).scalars()
    } if mundo == MUNDO_POR_DEFECTO else {}
    plantillas = (await db.execute(
        select(CalendarioPlantilla).where(CalendarioPlantilla.mundo == mundo)
        .order_by(CalendarioPlantilla.nombre, CalendarioPlantilla.id)
    )).scalars().all()
    return {
        "rev": actual,
        "mundo": mundo,
        "barras": [
            _barra_json(b, piezas.get(b.id, []), avisos.get(b.id, []), tareas.get(b.id, []))
            for b in barras
        ],
        "posicionesRM": posiciones,
        "plantillas": [_plantilla_json(p) for p in plantillas],
    }


@router.get("/personas")
async def listar_personas(
    mundo: str = MUNDO_POR_DEFECTO,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Quiénes pueden recibir un aviso o una tarea: los que pueden abrir el
    calendario de ese mundo. Solo id y nombre."""
    exigir_mundo(current_user, mundo)
    usuarios = (await db.execute(
        select(User).where(User.is_active == True).order_by(User.full_name)  # noqa: E712
    )).scalars()
    return [
        {"id": u.id, "nombre": u.full_name or u.email}
        for u in usuarios if _puede_ver_el_mundo(u, mundo)
    ]


# ---------------------------------------------------------------------------
# Barras
# ---------------------------------------------------------------------------

class BarraNueva(BaseModel):
    id: str = Field(..., pattern=_ID)
    mundo: str = Field(MUNDO_POR_DEFECTO, max_length=32)
    seccion: Seccion
    banda: str = Field(..., min_length=1, max_length=200)
    carril: int = Field(0, ge=0, le=500)
    nombre: str = Field(..., min_length=1, max_length=1000)
    color: str | None = Field(None, max_length=32)
    desde: Fecha
    hasta: Fecha
    # Solo los envíos sueltos: en las demás secciones se ignoran.
    formato: str | None = Field(None, max_length=100)
    hora: str | None = Field(None, pattern=_HORA)
    estado: Estado | None = None

    @field_validator("nombre")
    @classmethod
    def _sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede quedar vacío")
        return v

    # `min_length=1` deja pasar un espacio solo. En una acción la banda es la
    # categoría, que es además la fila del mes: un " " armaría una fila
    # fantasma, sin nombre.
    @field_validator("banda")
    @classmethod
    def _banda_sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La categoría no puede quedar vacía")
        return v

    @model_validator(mode="after")
    def _envio_suelto(self):
        if self.seccion == "envio":
            if self.banda not in _CANALES:
                raise ValueError("Un envío va por email, whatsapp o push")
            if self.hasta != self.desde:
                raise ValueError("Un envío sale un solo día: la fecha de fin es la misma que la de inicio")
            self.estado = self.estado or "pendiente"
        else:
            self.formato = self.hora = self.estado = None
        return self


class BarraCambios(BaseModel):
    """Solo viaja lo que cambió, y solo eso se escribe."""
    banda: str | None = Field(None, min_length=1, max_length=200)
    carril: int | None = Field(None, ge=0, le=500)
    nombre: str | None = Field(None, min_length=1, max_length=1000)
    color: str | None = Field(None, max_length=32)
    desde: Fecha | None = None
    hasta: Fecha | None = None
    # Solo los envíos sueltos. La hora puede venir en null (se saca la hora).
    formato: str | None = Field(None, max_length=100)
    hora: str | None = Field(None, pattern=_HORA)
    estado: Estado | None = None

    @field_validator("nombre")
    @classmethod
    def _sin_espacios(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede quedar vacío")
        return v

    # Igual que al crear: un " " no es una categoría. El null pasa como vino,
    # que `cambios_de_barra` lo toma como "no vino".
    @field_validator("banda")
    @classmethod
    def _banda_sin_espacios(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("La categoría no puede quedar vacía")
        return v


def cambios_de_barra(seccion: str, payload: BarraCambios, desde_actual: date, hasta_actual: date) -> dict:
    """Qué se escribe de un PATCH: solo lo que vino, y solo lo que esa sección
    admite. Pura a propósito, para probarla sin base. Un ValueError trae el
    mensaje para la persona."""
    cambios = {k: getattr(payload, k) for k in payload.model_fields_set}
    if "nombre" in cambios and cambios["nombre"] is None:
        raise ValueError("El nombre no puede quedar vacío")
    # Lo que no se puede vaciar: si viene en null, es como si no hubiera venido.
    # La hora y el formato de un envío SÍ se pueden vaciar.
    for campo in ("banda", "carril", "desde", "hasta", "estado"):
        if campo in cambios and cambios[campo] is None:
            del cambios[campo]
    if seccion == "envio":
        if "banda" in cambios and cambios["banda"] not in _CANALES:
            raise ValueError("Un envío va por email, whatsapp o push")
        # Otro canal tiene otros formatos ("Mailing digital" no es una push):
        # si cambia el canal y no se dice el formato, se vacía, y se muestra el
        # primero del canal nuevo.
        if "banda" in cambios and "formato" not in cambios:
            cambios["formato"] = None
    else:
        # Formato, hora y estado son de los envíos sueltos: en una acción esas
        # cosas las lleva cada pieza.
        for campo in ("formato", "hora", "estado"):
            cambios.pop(campo, None)
    desde = cambios.get("desde", desde_actual)
    hasta = cambios.get("hasta", hasta_actual)
    if hasta < desde:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
    if hasta - desde > _DURACION_MAXIMA:
        raise ValueError("Dura más de tres años: revisá el año de las fechas")
    if seccion == "envio" and hasta != desde:
        raise ValueError("Un envío sale un solo día: la fecha de fin es la misma que la de inicio")
    return cambios


@router.post("/barras", status_code=201)
async def crear_barra(
    payload: BarraNueva,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    _validar_rango(payload.desde, payload.hasta)
    exigir_mundo(current_user, payload.mundo)
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
    rev = await _nueva_revision(db, payload.mundo)
    await db.commit()
    return {"id": payload.id, "rev": rev}


@router.patch("/barras/{barra_id}")
async def cambiar_barra(
    barra_id: str,
    payload: BarraCambios,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    barra = await _barra_o_404(db, barra_id, current_user, bloquear=True)
    try:
        cambios = cambios_de_barra(barra.seccion, payload, barra.desde, barra.hasta)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    cambio_la_fecha = cambios.get("desde", barra.desde) != barra.desde
    cambio_el_fin = cambios.get("hasta", barra.hasta) != barra.hasta
    for campo, valor in cambios.items():
        setattr(barra, campo, valor)
    barra.actualizado_por_id = current_user.id
    movidas = 0
    if cambio_la_fecha or cambio_el_fin:
        # Las tareas que vinieron de una plantilla y no están hechas se mueven
        # con la acción, en la misma transacción: nadie ve la acción en la
        # fecha nueva con las tareas todavía en la vieja.
        ancladas = (await db.execute(
            select(CalendarioTarea).where(
                CalendarioTarea.barra_id == barra_id,
                CalendarioTarea.ancla.is_not(None),
                CalendarioTarea.estado != "hecha",
            ).with_for_update()
        )).scalars().all()
        nuevas = vencimientos_al_mover(ancladas, barra.desde, barra.hasta)
        for t in ancladas:
            if t.id in nuevas:
                t.vence = nuevas[t.id]
        movidas = len(nuevas)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    if cambio_la_fecha:
        # Un aviso que con la fecha nueva ya tendría que haber salido, sale ya.
        await _avisar_sin_romper(db, barra_id)
    return {"id": barra_id, "rev": rev, "tareasMovidas": movidas}


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
    exigir_mundo(current_user, barra.mundo)
    # Queda quién la borró y qué era: con varias personas en el mismo
    # calendario, "¿quién sacó tal acción?" es la pregunta que va a aparecer.
    db.add(AuditLog(
        user_id=current_user.id, action="calendario.borrar", resource="calendario_barra",
        resource_id=barra_id, ip_address=_client_ip(request),
        details={
            "mundo": barra.mundo, "seccion": barra.seccion, "banda": barra.banda, "nombre": barra.nombre,
            "desde": barra.desde.isoformat(), "hasta": barra.hasta.isoformat(),
        },
    ))
    mundo = barra.mundo
    await db.delete(barra)
    rev = await _nueva_revision(db, mundo)
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
    desde: Fecha | None = None
    hasta: Fecha | None = None
    hora: str | None = Field(None, pattern=_HORA)


class PiezaCambios(BaseModel):
    estado: Estado | None = None
    desde: Fecha | None = None
    hasta: Fecha | None = None
    hora: str | None = Field(None, pattern=_HORA)
    enSharePoint: bool | None = None


@router.post("/barras/{barra_id}/piezas", status_code=201)
async def agregar_pieza(
    barra_id: str,
    payload: PiezaNueva,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    # Bloquear la acción ordena a dos personas agregando piezas a la vez: la
    # segunda ve la pieza de la primera y no la duplica.
    barra = await _barra_o_404(db, barra_id, current_user, bloquear=True)
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
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": payload.id, "rev": rev}


@router.patch("/piezas/{pieza_id}")
async def cambiar_pieza(
    pieza_id: str,
    payload: PiezaCambios,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    pieza = (await db.execute(
        select(CalendarioPieza).where(CalendarioPieza.id == pieza_id).with_for_update()
    )).scalar_one_or_none()
    if pieza is None:
        raise HTTPException(status_code=404, detail="Esta pieza ya no existe: la sacó otra persona.")
    mundo = await _exigir_mundo_de(db, pieza.barra_id, current_user)
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
    rev = await _nueva_revision(db, mundo)
    await db.commit()
    return {"id": pieza_id, "rev": rev}


@router.delete("/piezas/{pieza_id}")
async def quitar_pieza(
    pieza_id: str,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    mundo = await _exigir_mundo_de(db, (await db.execute(
        select(CalendarioPieza.barra_id).where(CalendarioPieza.id == pieza_id)
    )).scalar_one_or_none(), current_user)
    await db.execute(delete(CalendarioPieza).where(CalendarioPieza.id == pieza_id))
    rev = await _nueva_revision(db, mundo)
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
    barra = await _barra_o_404(db, barra_id, current_user)
    if barra.seccion not in _CON_AVISOS:
        raise HTTPException(
            status_code=422,
            detail="Los avisos se configuran en las acciones del calendario comercial y en los envíos",
        )

    pedidos = list(dict.fromkeys(payload.destinatarios))
    usuarios = (await db.execute(select(User).where(User.id.in_(pedidos)))).scalars().all()
    validos = {u.id for u in usuarios if _puede_ver_el_mundo(u, barra.mundo)}
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
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    # Si la fecha del aviso ya pasó (10 días antes de algo que arranca en 5),
    # sale ahora y no en la próxima vuelta del loop.
    enviados = await _avisar_sin_romper(db, barra_id)
    return {"id": payload.id, "rev": rev, "enviadosAhora": enviados}


@router.delete("/avisos/{aviso_id}")
async def quitar_aviso(
    aviso_id: str,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    mundo = await _exigir_mundo_de(db, (await db.execute(
        select(CalendarioAviso.barra_id).where(CalendarioAviso.id == aviso_id)
    )).scalar_one_or_none(), current_user)
    await db.execute(delete(CalendarioAviso).where(CalendarioAviso.id == aviso_id))
    rev = await _nueva_revision(db, mundo)
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
    # El header de la home es de Tienda Inglesa: los otros mundos no tienen.
    exigir_mundo(current_user, MUNDO_POR_DEFECTO)
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
    # Retail Media es solo del calendario de Tienda Inglesa.
    rev = await _nueva_revision(db, MUNDO_POR_DEFECTO)
    await db.commit()
    return {"clave": clave, "avisados": len(destinatarios), "rev": rev}


# ---------------------------------------------------------------------------
# Tareas
# ---------------------------------------------------------------------------
# Pedido de Ivan (12/11/2026): quien lidera abre una acción, le crea tareas y
# subtareas y se las asigna a cada persona, que se entera por la campanita.
#
# Crear, editar, asignar y borrar pide `calendario.tareas`. Mover el ESTADO de
# una tarea lo puede hacer además la persona que la tiene asignada, aunque no
# tenga ese permiso ni `calendario.edit`: es su tarea.

TIPO_TAREA = "calendario_tarea"


def _puede_gestionar_tareas(usuario: User) -> bool:
    return bool(usuario.is_superuser) or PERMISO_TAREAS in (usuario.permissions or [])


def _exigir_gestion_de_tareas(usuario: User) -> None:
    if not _puede_gestionar_tareas(usuario):
        raise HTTPException(status_code=403, detail=f"Permiso requerido: {PERMISO_TAREAS}")


def referencia_de_tarea(barra_id: str, tarea_id: str) -> str:
    """Empieza por el id de la acción, igual que la de un aviso: es lo que usa
    la campanita para llevar a su ficha."""
    return f"{barra_id}:{tarea_id}"


def mensaje_de_asignacion(quien: str, titulo: str, accion: str, vence: date | None) -> str:
    cuando = f" Vence el {vence.strftime('%d/%m')}." if vence else ""
    return f"{quien} te asignó una tarea en {accion or 'una acción'}: {titulo}.{cuando}"


def mensaje_de_tarea_hecha(quien: str, titulo: str, accion: str) -> str:
    return f"{quien} terminó la tarea «{titulo}» de {accion or 'una acción'}."


def nivel_de(tarea_id: str | None, padres: dict[str, str | None]) -> int:
    """A qué profundidad queda algo que cuelga de `tarea_id`: 1 si no cuelga
    de nada. Pura, para probarla sin base. El tope corta un ciclo."""
    nivel = 1
    while tarea_id is not None and nivel <= _NIVELES_DE_TAREA + 1:
        nivel += 1
        tarea_id = padres.get(tarea_id)
    return nivel


# --- Vencimientos anclados a la acción (0064) ---------------------------------
# Una tarea que vino de una plantilla vence "N días antes/después del inicio o
# del fin" de su acción. Se guarda la fecha calculada (es lo que leen "Mis
# tareas", los vencidos y los avisos) y además de dónde sale, para poder
# recalcularla si la acción se mueve. Estas funciones no usan la base (la que
# cambia algo, cambia solo la tarea que recibe), para probarlas sin ella;
# reciben cualquier cosa con los campos de una tarea.

def vence_anclado(ancla: str, dias: int, desde: date, hasta: date) -> date:
    """`dias` contados desde el inicio o el fin de la acción. Negativo = antes."""
    return (desde if ancla == "inicio" else hasta) + timedelta(days=dias)


def vencimientos_al_mover(tareas, desde: date, hasta: date) -> dict[str, date]:
    """Las tareas que se mueven porque la acción pasó a ir de `desde` a
    `hasta`, con su vencimiento nuevo. Solo las ancladas que no están hechas
    (lo hecho, hecho está: su fecha queda como registro) y solo si cambia."""
    nuevas: dict[str, date] = {}
    for t in tareas:
        if t.ancla is None or t.ancla_dias is None or t.estado == "hecha":
            continue
        vence = vence_anclado(t.ancla, t.ancla_dias, desde, hasta)
        if vence != t.vence:
            nuevas[t.id] = vence
    return nuevas


def poner_vence_a_mano(tarea, vence: date | None) -> None:
    """Alguien eligió la fecha: manda esa, y la tarea deja de moverse con la
    acción. Volver a mandar la misma fecha no es elegir otra: el ancla queda."""
    if vence == tarea.vence:
        return
    tarea.vence = vence
    tarea.ancla = None
    tarea.ancla_dias = None


def vence_al_reabrir(tarea, desde: date, hasta: date) -> date | None:
    """El vencimiento de una tarea hecha que se vuelve a abrir. Mientras
    estuvo hecha no se movió con la acción; si sigue anclada, vuelve a la
    fecha que le toca hoy. Una sin ancla queda como estaba."""
    if tarea.ancla is None or tarea.ancla_dias is None:
        return tarea.vence
    return vence_anclado(tarea.ancla, tarea.ancla_dias, desde, hasta)


def _avisar(db: AsyncSession, user_id: int, mensaje: str, barra_id: str, tarea_id: str) -> None:
    db.add(Notificacion(
        user_id=user_id, tipo=TIPO_TAREA, mensaje=mensaje,
        origen_tipo=TIPO_TAREA, origen_ref=referencia_de_tarea(barra_id, tarea_id),
    ))


async def _asignable_o_422(db: AsyncSession, user_id: int, mundo: str) -> User:
    usuario = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if usuario is None or not _puede_ver_el_mundo(usuario, mundo):
        raise HTTPException(
            status_code=422,
            detail=f"Esa persona no puede abrir el calendario de {MUNDOS.get(mundo, mundo)}: no vería la tarea",
        )
    return usuario


class TareaNueva(BaseModel):
    id: str = Field(..., pattern=_ID)
    parentId: str | None = Field(None, pattern=_ID)
    titulo: str = Field(..., min_length=1, max_length=500)
    descripcion: str | None = Field(None, max_length=5000)
    asignadoA: int | None = None
    vence: Fecha | None = None

    @field_validator("titulo")
    @classmethod
    def _sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La tarea necesita un título")
        return v


class TareaCambios(BaseModel):
    """Solo viaja lo que cambió. `asignadoA`, `vence` y `descripcion` pueden
    venir en null a propósito: es sacarle la persona, la fecha o el detalle."""
    titulo: str | None = Field(None, min_length=1, max_length=500)
    descripcion: str | None = Field(None, max_length=5000)
    estado: EstadoTarea | None = None
    asignadoA: int | None = None
    vence: Fecha | None = None


@router.post("/barras/{barra_id}/tareas", status_code=201)
async def crear_tarea(
    barra_id: str,
    payload: TareaNueva,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    _exigir_gestion_de_tareas(current_user)
    barra = await _barra_o_404(db, barra_id, current_user, bloquear=True)
    if barra.seccion not in _CON_AVISOS:
        raise HTTPException(
            status_code=422,
            detail="Las tareas se cargan en las acciones del calendario comercial y en los envíos",
        )
    existentes = (await db.execute(
        select(CalendarioTarea).where(CalendarioTarea.barra_id == barra_id)
    )).scalars().all()
    if any(t.id == payload.id for t in existentes):
        return {"id": payload.id, "rev": await _revision_actual(db), "yaExistia": True}
    # El id lo genera el front; si ya lo usa una tarea de OTRA acción, la
    # clave primaria lo frenaría con un 500 sin explicación.
    if await db.get(CalendarioTarea, payload.id) is not None:
        raise HTTPException(status_code=409, detail="Esa tarea ya existe en otra acción")
    padres = {t.id: t.parent_id for t in existentes}
    if payload.parentId is not None:
        if payload.parentId not in padres:
            raise HTTPException(status_code=404, detail="La tarea de la que cuelga ya no existe: la borraron.")
        if nivel_de(payload.parentId, padres) > _NIVELES_DE_TAREA:
            raise HTTPException(status_code=422, detail="Una sub-subtarea no puede tener más tareas adentro")
    if payload.asignadoA is not None:
        await _asignable_o_422(db, payload.asignadoA, barra.mundo)
    db.add(CalendarioTarea(
        id=payload.id, barra_id=barra_id, parent_id=payload.parentId, titulo=payload.titulo,
        descripcion=(payload.descripcion or "").strip() or None,
        asignado_a_id=payload.asignadoA, vence=payload.vence,
        orden=max((t.orden for t in existentes), default=-1) + 1,
        creado_por_id=current_user.id,
    ))
    avisados = 0
    if payload.asignadoA is not None and payload.asignadoA != current_user.id:
        _avisar(db, payload.asignadoA, mensaje_de_asignacion(
            current_user.full_name, payload.titulo, barra.nombre, payload.vence,
        ), barra_id, payload.id)
        avisados = 1
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": payload.id, "rev": rev, "avisados": avisados}


@router.patch("/tareas/{tarea_id}")
async def cambiar_tarea(
    tarea_id: str,
    payload: TareaCambios,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    tarea = (await db.execute(
        select(CalendarioTarea).where(CalendarioTarea.id == tarea_id).with_for_update()
    )).scalar_one_or_none()
    if tarea is None:
        raise HTTPException(status_code=404, detail="Esta tarea ya no existe: la borró otra persona.")
    barra = await _barra_o_404(db, tarea.barra_id, current_user)

    campos = payload.model_fields_set
    solo_estado = campos <= {"estado"}
    es_suya = tarea.asignado_a_id == current_user.id
    if not _puede_gestionar_tareas(current_user) and not (solo_estado and es_suya):
        raise HTTPException(
            status_code=403,
            detail="Solo podés cambiar el estado de las tareas que tenés asignadas",
        )

    avisados = 0
    if "titulo" in campos and payload.titulo is not None:
        titulo = payload.titulo.strip()
        if not titulo:
            raise HTTPException(status_code=422, detail="La tarea necesita un título")
        tarea.titulo = titulo
    if "descripcion" in campos:
        tarea.descripcion = (payload.descripcion or "").strip() or None
    if "vence" in campos:
        poner_vence_a_mano(tarea, payload.vence)
    if "asignadoA" in campos and payload.asignadoA != tarea.asignado_a_id:
        if payload.asignadoA is not None:
            await _asignable_o_422(db, payload.asignadoA, barra.mundo)
            if payload.asignadoA != current_user.id:
                _avisar(db, payload.asignadoA, mensaje_de_asignacion(
                    current_user.full_name, tarea.titulo, barra.nombre, tarea.vence,
                ), barra.id, tarea.id)
                avisados += 1
        tarea.asignado_a_id = payload.asignadoA
    if "estado" in campos and payload.estado is not None and payload.estado != tarea.estado:
        if tarea.estado == "hecha" and "vence" not in campos:
            # Hecha no se movía con la acción; si se reabre, vuelve a su fecha
            # contada desde la acción como está hoy (ver vence_al_reabrir).
            tarea.vence = vence_al_reabrir(tarea, barra.desde, barra.hasta)
        tarea.estado = payload.estado
        # A quien la creó le interesa saber que se terminó, salvo que la haya
        # terminado esa misma persona.
        if payload.estado == "hecha" and tarea.creado_por_id and tarea.creado_por_id != current_user.id:
            _avisar(db, tarea.creado_por_id, mensaje_de_tarea_hecha(
                current_user.full_name, tarea.titulo, barra.nombre,
            ), barra.id, tarea.id)
            avisados += 1
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": tarea_id, "rev": rev, "avisados": avisados}


@router.delete("/tareas/{tarea_id}")
async def borrar_tarea(
    tarea_id: str,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Borra la tarea y todo lo que cuelga de ella."""
    _exigir_gestion_de_tareas(current_user)
    mundo = await _exigir_mundo_de(db, (await db.execute(
        select(CalendarioTarea.barra_id).where(CalendarioTarea.id == tarea_id)
    )).scalar_one_or_none(), current_user)
    await db.execute(delete(CalendarioTarea).where(CalendarioTarea.id == tarea_id))
    rev = await _nueva_revision(db, mundo)
    await db.commit()
    return {"id": tarea_id, "borrada": True, "rev": rev}


DIAS_DE_HECHAS_EN_MIS_TAREAS = 30


@router.get("/mis-tareas")
async def mis_tareas(
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Lo que la persona tiene asignado, en todos los mundos que puede abrir,
    con la acción de cada tarea. Es lo que muestra el inicio.

    Las abiertas, todas; las hechas, solo las de los últimos
    DIAS_DE_HECHAS_EN_MIS_TAREAS días. Antes venía todo lo de siempre: con el
    uso se iba a cientos de tareas viejas (medido: 269 KB con 668) que nadie
    mira y que se bajaban cada vez que se abría la pantalla."""
    mundos = mundos_de(current_user)
    if not mundos:
        return []
    desde = datetime.now(timezone.utc) - timedelta(days=DIAS_DE_HECHAS_EN_MIS_TAREAS)
    filas = (await db.execute(
        select(CalendarioTarea, CalendarioBarra)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .where(
            CalendarioTarea.asignado_a_id == current_user.id,
            CalendarioBarra.mundo.in_(mundos),
            or_(
                CalendarioTarea.estado != "hecha",
                # Se tildó (o se tocó por última vez) hace menos de eso.
                func.coalesce(CalendarioTarea.updated_at, CalendarioTarea.created_at) >= desde,
            ),
        )
        .order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioBarra.desde, CalendarioTarea.id)
    )).all()
    return [
        {
            **_tarea_json(t),
            "accion": {
                "id": b.id, "mundo": b.mundo, "nombre": b.nombre, "banda": b.banda,
                "seccion": b.seccion, "color": b.color,
                "desde": b.desde.isoformat(), "hasta": b.hasta.isoformat(),
            },
        }
        for t, b in filas
    ]


@router.get("/ubicar/{barra_id}")
async def ubicar_barra(
    barra_id: str,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """En qué mundo y en qué fecha está una acción: lo necesita un aviso de la
    campanita para abrir su ficha aunque se esté mirando otro mundo."""
    barra = await _barra_o_404(db, barra_id, current_user)
    return {"id": barra.id, "mundo": barra.mundo, "desde": barra.desde.isoformat()}


# ---------------------------------------------------------------------------
# Plantillas de tareas (0064)
# ---------------------------------------------------------------------------
# Cada tipo de acción lleva casi siempre las mismas tareas (el brief a la
# agencia, las entregas, la aprobación, las cenefas a los locales, el retiro).
# Una plantilla las guarda con su vencimiento relativo y, al aplicarla en una
# acción, se crean con la fecha ya calculada y ancladas: si la acción se
# mueve, se mueven con ella (ver cambiar_barra).
#
# Armarlas, cambiarlas, borrarlas y aplicarlas pide `calendario.tareas`, igual
# que crear tareas a mano: aplicar una es crear varias de una vez. Cada
# plantilla es de un mundo, y solo se ve y se usa en ese.

Ancla = Literal["inicio", "fin"]
_DIAS_DE_ANCLA = 365
_TAREAS_POR_PLANTILLA = 60


class TareaDePlantilla(BaseModel):
    """Una tarea de la plantilla. `parentId` es otra tarea de la MISMA
    plantilla: una subtarea, de un nivel nomás."""
    id: str = Field(..., pattern=_ID)
    parentId: str | None = Field(None, pattern=_ID)
    titulo: str = Field(..., min_length=1, max_length=500)
    descripcion: str | None = Field(None, max_length=5000)
    # Una persona fija. Sin nadie, la tarea se crea sin asignar.
    asignadoA: int | None = None
    # Desde dónde se cuenta el vencimiento, y cuántos días (negativo = antes).
    # Sin ancla, la tarea se crea sin fecha.
    ancla: Ancla | None = "inicio"
    dias: int = Field(0, ge=-_DIAS_DE_ANCLA, le=_DIAS_DE_ANCLA)

    @field_validator("titulo")
    @classmethod
    def _titulo_sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Cada tarea de la plantilla necesita un título")
        return v

    @field_validator("descripcion")
    @classmethod
    def _descripcion_o_nada(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @model_validator(mode="after")
    def _sin_ancla_no_hay_dias(self):
        if self.ancla is None:
            self.dias = 0
        return self


def revisar_estructura(tareas: list[TareaDePlantilla]) -> None:
    """Que la plantilla se pueda aplicar tal cual: ids sin repetir, y cada
    subtarea colgando de una tarea de la plantilla que no es a su vez una
    subtarea. Pura; un ValueError trae el mensaje para la persona."""
    ids = [t.id for t in tareas]
    if len(set(ids)) != len(ids):
        raise ValueError("Hay dos tareas con el mismo id en la plantilla")
    padres = {t.id: t.parentId for t in tareas}
    for t in tareas:
        if t.parentId is None:
            continue
        if t.parentId == t.id or t.parentId not in padres:
            raise ValueError(f"La subtarea «{t.titulo}» cuelga de una tarea que no está en la plantilla")
        if padres[t.parentId] is not None:
            raise ValueError("En una plantilla las subtareas son de un nivel: una subtarea no lleva otras adentro")


def categoria_de_plantilla(v: str | None) -> str | None:
    """La categoría con la que se guarda una plantilla. "Sin categoría" (lo
    que lleva en `banda` una acción a la que no se le eligió ninguna) no es
    una categoría: es que la plantilla sirve para cualquiera."""
    v = (v or "").strip()
    if not v or v.casefold() == SIN_CATEGORIA.casefold():
        return None
    return v


class PlantillaDatos(BaseModel):
    """Una plantilla entera: se guarda siempre completa, como se ve en su editor."""
    mundo: str = Field(MUNDO_POR_DEFECTO, max_length=32)
    nombre: str = Field(..., min_length=1, max_length=200)
    categoria: str | None = Field(None, max_length=200)
    tareas: list[TareaDePlantilla] = Field(..., min_length=1, max_length=_TAREAS_POR_PLANTILLA)

    @field_validator("nombre")
    @classmethod
    def _nombre_sin_espacios(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La plantilla necesita un nombre")
        return v

    @field_validator("categoria")
    @classmethod
    def _categoria(cls, v: str | None) -> str | None:
        return categoria_de_plantilla(v)

    @model_validator(mode="after")
    def _estructura(self):
        revisar_estructura(self.tareas)
        return self


_PATRON_ID = re.compile(_ID)


class PlantillaAplicada(BaseModel):
    plantillaId: str = Field(..., pattern=_ID)
    # El id de cada tarea nueva, por el id de su tarea en la plantilla. Los
    # genera el front, como el de cualquier tarea: así la ficha las muestra
    # antes de que conteste el servidor, y un reintento no las duplica.
    ids: dict[str, str] = Field(..., min_length=1, max_length=_TAREAS_POR_PLANTILLA)

    @field_validator("ids")
    @classmethod
    def _ids_validos(cls, v: dict[str, str]) -> dict[str, str]:
        if any(not _PATRON_ID.match(k) or not _PATRON_ID.match(x) for k, x in v.items()):
            raise ValueError("Hay un id de tarea que no es válido")
        if len(set(v.values())) != len(v):
            raise ValueError("Dos tareas nuevas no pueden tener el mismo id")
        return v


class PlantillaCambio(ValueError):
    """Los ids que mandó el front no son los de la plantilla guardada: otra
    persona la editó desde que el front la leyó."""


def tareas_de_plantilla(tareas: list[dict], ids: dict[str, str], desde: date, hasta: date) -> list[dict]:
    """Las tareas que crea una plantilla en una acción que va de `desde` a
    `hasta`, con el vencimiento calculado y anclado. Las tareas sueltas
    primero y las subtareas después, cada grupo en el orden de la plantilla:
    una subtarea no se puede guardar antes que la tarea de la que cuelga. Pura.

    Si `ids` no trae exactamente las tareas de la plantilla, lo que vio el
    front ya no es lo guardado: PlantillaCambio, y que vuelva a mirar."""
    if set(ids) != {t["id"] for t in tareas}:
        raise PlantillaCambio("La plantilla cambió")
    sueltas = [t for t in tareas if not t.get("parentId")]
    subtareas = [t for t in tareas if t.get("parentId")]
    out = []
    for t in sueltas + subtareas:
        ancla = t.get("ancla") or None
        dias = int(t.get("dias") or 0)
        out.append({
            "id": ids[t["id"]],
            "parent_id": ids.get(t["parentId"]) if t.get("parentId") else None,
            "titulo": t["titulo"],
            "descripcion": t.get("descripcion") or None,
            "asignado_a_id": t.get("asignadoA"),
            "vence": vence_anclado(ancla, dias, desde, hasta) if ancla else None,
            "ancla": ancla,
            "ancla_dias": dias if ancla else None,
        })
    return out


def mensaje_de_asignaciones(quien: str, tareas: list[tuple[str, date | None]], accion: str) -> str:
    """El aviso a quien recibe tareas de una plantilla: UNO por persona con
    todas las suyas, no uno por tarea (diez avisos seguidos de la misma acción
    son ruido, y el que importa se pierde). Con una sola, el aviso de siempre."""
    if len(tareas) == 1:
        titulo, vence = tareas[0]
        return mensaje_de_asignacion(quien, titulo, accion, vence)
    titulos = [t for t, _ in tareas]
    if len(titulos) <= 3:
        lista = f"{', '.join(titulos[:-1])} y {titulos[-1]}"
    else:
        lista = f"{', '.join(titulos[:3])} y {len(titulos) - 3} más"
    vences = [v for _, v in tareas if v]
    cuando = f" La primera vence el {min(vences).strftime('%d/%m')}." if vences else ""
    return f"{quien} te asignó {len(tareas)} tareas en {accion or 'una acción'}: {lista}.{cuando}"


async def _asignables(db: AsyncSession, ids: set[int], mundo: str) -> set[int]:
    """De esas personas, las que pueden abrir el calendario de `mundo`."""
    if not ids:
        return set()
    usuarios = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {u.id for u in usuarios if _puede_ver_el_mundo(u, mundo)}


@router.put("/plantillas/{plantilla_id}")
async def guardar_plantilla(
    payload: PlantillaDatos,
    plantilla_id: str = Path(..., pattern=_ID),
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Crea la plantilla o la reemplaza entera. El id lo genera el front: un
    reintento del mismo guardado vuelve a escribir lo mismo."""
    _exigir_gestion_de_tareas(current_user)
    exigir_mundo(current_user, payload.mundo)
    plantilla = (await db.execute(
        select(CalendarioPlantilla).where(CalendarioPlantilla.id == plantilla_id).with_for_update()
    )).scalar_one_or_none()
    if plantilla is not None and plantilla.mundo != payload.mundo:
        # Una plantilla no se muda de mundo, ni se pisa una ajena con el mismo id.
        raise HTTPException(status_code=409, detail="Esa plantilla es de otro mundo")
    pedidos = {t.asignadoA for t in payload.tareas if t.asignadoA is not None}
    if pedidos - await _asignables(db, pedidos, payload.mundo):
        raise HTTPException(
            status_code=422,
            detail=(f"Hay responsables que no pueden abrir el calendario de "
                    f"{MUNDOS.get(payload.mundo, payload.mundo)}: no verían sus tareas. Elegí a otra persona."),
        )
    tareas = [t.model_dump() for t in payload.tareas]
    if plantilla is None:
        db.add(CalendarioPlantilla(
            id=plantilla_id, mundo=payload.mundo, nombre=payload.nombre, categoria=payload.categoria,
            tareas=tareas, creado_por_id=current_user.id, actualizado_por_id=current_user.id,
        ))
    else:
        plantilla.nombre = payload.nombre
        plantilla.categoria = payload.categoria
        plantilla.tareas = tareas
        plantilla.actualizado_por_id = current_user.id
    rev = await _nueva_revision(db, payload.mundo)
    await db.commit()
    return {"id": plantilla_id, "rev": rev}


@router.delete("/plantillas/{plantilla_id}")
async def borrar_plantilla(
    plantilla_id: str,
    request: Request,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Borra la plantilla. Las tareas que ya creó en las acciones se quedan, y
    siguen moviéndose con su acción: el ancla está en cada tarea."""
    _exigir_gestion_de_tareas(current_user)
    plantilla = (await db.execute(
        select(CalendarioPlantilla).where(CalendarioPlantilla.id == plantilla_id).with_for_update()
    )).scalar_one_or_none()
    if plantilla is None:
        # Ya la había borrado otro: el resultado es el mismo.
        return {"id": plantilla_id, "borrada": True}
    exigir_mundo(current_user, plantilla.mundo)
    # Como con las acciones: queda quién la borró y qué tenía.
    db.add(AuditLog(
        user_id=current_user.id, action="calendario.borrar_plantilla", resource="calendario_plantilla",
        resource_id=plantilla_id, ip_address=_client_ip(request),
        details={
            "mundo": plantilla.mundo, "nombre": plantilla.nombre, "categoria": plantilla.categoria,
            "tareas": [t.get("titulo") for t in (plantilla.tareas or [])],
        },
    ))
    mundo = plantilla.mundo
    await db.delete(plantilla)
    rev = await _nueva_revision(db, mundo)
    await db.commit()
    return {"id": plantilla_id, "borrada": True, "rev": rev}


@router.post("/barras/{barra_id}/plantilla", status_code=201)
async def aplicar_plantilla(
    barra_id: str,
    payload: PlantillaAplicada,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Crea en la acción las tareas de una plantilla, con el vencimiento
    calculado desde las fechas de la acción y anclado a ellas.

    A cada responsable le llega UN aviso con todas sus tareas. Si la plantilla
    nombra a alguien que ya no abre este calendario, su tarea se crea sin
    asignar (no se frena todo por una persona) y se dice cuántas quedaron así."""
    _exigir_gestion_de_tareas(current_user)
    barra = await _barra_o_404(db, barra_id, current_user, bloquear=True)
    if barra.seccion not in _CON_AVISOS:
        raise HTTPException(
            status_code=422,
            detail="Las tareas se cargan en las acciones del calendario comercial y en los envíos",
        )
    plantilla = await db.get(CalendarioPlantilla, payload.plantillaId)
    if plantilla is None or plantilla.mundo != barra.mundo:
        raise HTTPException(status_code=404, detail="Esa plantilla ya no existe: la borró otra persona.")

    ya_estan = (await db.execute(
        select(CalendarioTarea.barra_id).where(CalendarioTarea.id.in_(list(payload.ids.values())))
    )).scalars().all()
    if ya_estan:
        if all(b == barra_id for b in ya_estan):
            # Un reintento de lo mismo: ya se crearon.
            return {"id": barra_id, "rev": await _revision_actual(db), "yaExistia": True}
        raise HTTPException(status_code=409, detail="Esa tarea ya existe en otra acción")
    try:
        plan = tareas_de_plantilla(list(plantilla.tareas or []), payload.ids, barra.desde, barra.hasta)
    except PlantillaCambio:
        raise HTTPException(
            status_code=409,
            detail="Otra persona cambió esa plantilla recién. Se recargó el calendario: probá de nuevo.",
        )

    pedidos = {t["asignado_a_id"] for t in plan if t["asignado_a_id"] is not None}
    validos = await _asignables(db, pedidos, barra.mundo)
    sin_asignar = 0
    for t in plan:
        if t["asignado_a_id"] is not None and t["asignado_a_id"] not in validos:
            t["asignado_a_id"] = None
            sin_asignar += 1

    ultimo = (await db.execute(
        select(func.max(CalendarioTarea.orden)).where(CalendarioTarea.barra_id == barra_id)
    )).scalar_one_or_none()
    base = (ultimo if ultimo is not None else -1) + 1
    nuevas = [
        CalendarioTarea(**t, barra_id=barra_id, orden=base + i, plantilla_id=plantilla.id,
                        creado_por_id=current_user.id)
        for i, t in enumerate(plan)
    ]
    # Primero las tareas sueltas y después las subtareas, cada tanda en su
    # INSERT: la subtarea apunta a una tarea de esta misma tanda, que tiene
    # que existir antes.
    db.add_all([t for t in nuevas if t.parent_id is None])
    await db.flush()
    db.add_all([t for t in nuevas if t.parent_id is not None])

    # Un aviso por persona, con todas sus tareas (no a quien la aplicó: se
    # las asignó él mismo). Lleva a la ficha de la acción, como el de siempre.
    por_persona: dict[int, list[dict]] = {}
    for t in plan:
        if t["asignado_a_id"] is not None and t["asignado_a_id"] != current_user.id:
            por_persona.setdefault(t["asignado_a_id"], []).append(t)
    for user_id, suyas in por_persona.items():
        _avisar(db, user_id, mensaje_de_asignaciones(
            current_user.full_name, [(t["titulo"], t["vence"]) for t in suyas], barra.nombre,
        ), barra_id, suyas[0]["id"])

    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {
        "id": barra_id, "rev": rev, "creadas": len(plan),
        "avisados": len(por_persona), "sinAsignar": sin_asignar,
    }
