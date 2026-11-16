"""colocacion.py — la foto de colocación: promo la pide, el local la sube.

Para promo (`calendario.edit` en el mundo de la acción):

  GET    /colocacion/disponibles?mundo=        — a qué locales se les puede pedir
  GET    /colocacion/resumen?mundo=            — la vista general: acciones con pedidos abiertos
  GET    /colocacion/acciones/{barra_id}       — el tablero de una acción
  POST   /colocacion/acciones/{barra_id}       — pedir la foto a los locales
  PATCH  /colocacion/pedidos/{id}              — fecha límite, indicación, sumar o sacar locales
  DELETE /colocacion/pedidos/{id}              — cancelar el pedido entero
  POST   /colocacion/locales/{id}/aprobar
  POST   /colocacion/locales/{id}/devolver     — con un comentario, que le llega al local

Para el local (tener el local asignado en `local_asignaciones`):

  GET    /colocacion/mis-fotos                 — lo que tiene que subir
  POST   /colocacion/locales/{id}/fotos        — sube una foto (hasta 3 por pedido)
  DELETE /colocacion/fotos/{id}                — saca una foto suya que todavía no revisaron

Para los dos:

  GET    /colocacion/fotos/{id}?tamano=mini|grande — la imagen

Todo se cuida acá, del lado del servidor: un local solo ve y toca lo de sus
locales (y en los mundos que abre); promo, lo de los mundos que abre y con
`calendario.edit`. Un pedido ajeno contesta 404 y no 403: un local no tiene
por qué enterarse de qué ids existen.

Las fotos llegan achicadas desde el teléfono (lib/colocacion/imagen.ts) y acá
se vuelven a revisar: tipo real por los bytes, tamaño y que Pillow las pueda
abrir. Viven en su propia tabla y no en /calendario/datos, que se consulta
cada 15 s: de las fotos, /datos solo dice cuántos locales y hasta cuándo, y
eso cambia solo cuando promo crea, cambia o cancela un pedido (ahí sube la
revisión del mundo). Que un local suba una foto no la sube: con 60 locales
subiendo, cada persona mirando el calendario se lo bajaría entero 60 veces.

Avisos a la campanita: al local cuando le piden una foto y cuando se la
devuelven. A promo, uno solo por pedido, cuando mandaron todos (no uno por
foto: serían 60).
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import AfterValidator, BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from app.api.routes.calendario import _fecha_razonable, _nueva_revision
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import client_ip, get_current_user, require_permission
from app.core.mundos import MUNDOS, exigir_mundo, mundos_de, puede_abrir
from app.core.rate_limit import limiter
from app.models.audit_log import AuditLog
from app.models.calendario import CalendarioBarra
from app.models.colocacion import ColocacionFoto, ColocacionLocal, ColocacionPedido
from app.models.local_asignacion import LocalAsignacion
from app.models.notificacion import Notificacion
from app.models.user import User
from app.services import colocacion as reglas
from app.services.calendario_avisos import hoy_en_uruguay
from app.services.espacio import MENSAJE_SIN_LUGAR, hay_lugar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/colocacion", tags=["colocacion"])

PERMISO = "calendario.edit"

# Los avisos de la campanita (los orígenes están en services/colocacion.py).
# Los del local llevan "{acción}:{local}" en la referencia y los de promo
# "{acción}:{pedido}": empiezan por la acción, igual que los del calendario
# (ver resolverDestino en el Sidebar).
ORIGEN_PEDIDO = reglas.ORIGEN_PEDIDO
ORIGEN_DEVUELTA = reglas.ORIGEN_DEVUELTA
ORIGEN_COMPLETA = reglas.ORIGEN_COMPLETA
ORIGENES_DEL_LOCAL = reglas.ORIGENES_DEL_LOCAL

# Cuánto sigue viendo el local un pedido después de que terminó la acción (si
# no lo terminó) y uno aprobado: después deja de ocupar su pantalla.
DIAS_VISIBLE_DESPUES_DE_LA_ACCION = 30
DIAS_VISIBLE_APROBADA = 14
# Las acciones con todo aprobado que todavía muestra la vista general.
DIAS_COMPLETAS_EN_EL_RESUMEN = 30

# Lo que pesa una subida como mucho: la foto, la miniatura y lo que agrega el
# formulario. Se mira ANTES de leer el cuerpo, para no recibir 100 MB para
# después rechazarlos.
_MAX_CUERPO = reglas.MAX_BYTES_FOTO + reglas.MAX_BYTES_MINIATURA + 64 * 1024

_NO_ESTA = "No encontramos ese pedido de foto: puede que lo hayan cancelado."
_YA_APROBADA = "Esta foto ya está aprobada: no hace falta subir otra"


# ---------------------------------------------------------------------------
# Reglas de acceso (puras, se prueban sin base)
# ---------------------------------------------------------------------------

def es_promo_del_mundo(usuario, mundo: str) -> bool:
    """Puede pedir, ver y revisar fotos de las acciones de ese mundo."""
    permisos = getattr(usuario, "permissions", None) or []
    return bool(getattr(usuario, "is_superuser", False) or PERMISO in permisos) and puede_abrir(usuario, mundo)


def es_del_local(usuario, asignaciones: set[tuple[str, str]], local_nombre: str, tipo: str, mundo: str) -> bool:
    """Si el usuario es de ese local: lo tiene asignado (con el tipo del
    pedido) y abre el mundo de la acción. Un superusuario NO es un local: ve
    las fotos como promo, no las sube."""
    return (local_nombre, tipo) in asignaciones and puede_abrir(usuario, mundo)


def referencia_local(barra_id: str, local_id: int) -> str:
    return f"{barra_id}:{local_id}"


def referencia_pedido(barra_id: str, pedido_id: int) -> str:
    return f"{barra_id}:{pedido_id}"


def mensaje_pedido(accion: str, limite: date) -> str:
    return f"Te pidieron una foto de «{accion}» para ver cómo quedó en el local. Hay tiempo hasta el {limite.strftime('%d/%m')}."


def mensaje_devuelta(accion: str, comentario: str) -> str:
    comentario = comentario.strip()
    if len(comentario) > 200:
        comentario = comentario[:199].rstrip() + "…"
    return f"Te devolvieron la foto de «{accion}»: {comentario}"


def mensaje_completa(accion: str, total: int) -> str:
    if total == 1:
        return f"El local mandó la foto de «{accion}». Falta revisarla."
    return f"Los {total} locales mandaron la foto de «{accion}». Faltan revisarlas."


# ---------------------------------------------------------------------------
# Lo que viaja
# ---------------------------------------------------------------------------

def _iso(d: datetime | date | None) -> str | None:
    return d.isoformat() if d else None


def _foto_json(f) -> dict:
    return {"id": f.id, "ancho": f.ancho, "alto": f.alto, "devuelta": f.devuelta, "subidaAt": _iso(f.created_at)}


def _local_json(l: ColocacionLocal, pedido: ColocacionPedido, fotos: list, hoy: date, nombres: dict[int, str]) -> dict:
    return {
        "id": l.id,
        "local": l.local_nombre,
        "estado": l.estado,
        "visible": reglas.estado_visible(l.estado, pedido.limite, hoy),
        "tarde": reglas.mando_tarde(l.enviada_at, pedido.limite, reglas.URUGUAY),
        "comentario": l.comentario,
        "enviadaAt": _iso(l.enviada_at),
        "revisadoAt": _iso(l.revisado_at),
        "revisadoPor": nombres.get(l.revisado_por_id) if l.revisado_por_id else None,
        "fotos": [_foto_json(f) for f in fotos],
    }


async def _nombres(db: AsyncSession, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    filas = await db.execute(select(User.id, User.full_name, User.email).where(User.id.in_(ids)))
    return {i: (n or e) for i, n, e in filas.all()}


async def _fotos_de(db: AsyncSession, local_ids: list[int]) -> dict[int, list]:
    """Las fotos de esos locales, SIN los bytes: solo lo que se lista."""
    if not local_ids:
        return {}
    out: dict[int, list] = {}
    for f in (await db.execute(
        select(
            ColocacionFoto.id, ColocacionFoto.local_id, ColocacionFoto.ancho, ColocacionFoto.alto,
            ColocacionFoto.devuelta, ColocacionFoto.created_at,
        ).where(ColocacionFoto.local_id.in_(local_ids)).order_by(ColocacionFoto.created_at, ColocacionFoto.id)
    )).all():
        out.setdefault(f.local_id, []).append(f)
    return out


async def _pedido_json(db: AsyncSession, pedido: ColocacionPedido, hoy: date) -> dict:
    locales = (await db.execute(
        select(ColocacionLocal).where(ColocacionLocal.pedido_id == pedido.id).order_by(ColocacionLocal.local_nombre)
    )).scalars().all()
    fotos = await _fotos_de(db, [l.id for l in locales])
    nombres = await _nombres(db, [pedido.creado_por_id, *(l.revisado_por_id for l in locales)])
    filas = [_local_json(l, pedido, fotos.get(l.id, []), hoy, nombres) for l in locales]
    return {
        "id": pedido.id,
        "tipoLocal": pedido.tipo_local,
        "limite": pedido.limite.isoformat(),
        "indicacion": pedido.indicacion,
        "creadoPor": nombres.get(pedido.creado_por_id) if pedido.creado_por_id else None,
        "createdAt": _iso(pedido.created_at),
        "resumen": reglas.resumen([f["visible"] for f in filas]),
        "locales": filas,
    }


# ---------------------------------------------------------------------------
# Ayudas con la base
# ---------------------------------------------------------------------------

async def _disponibles(db: AsyncSession, tipo: str | None) -> list[str]:
    """Los locales de ese tipo que tienen al menos un login activo: son los
    únicos que pueden subir la foto."""
    if not tipo:
        return []
    nombres = (await db.execute(
        select(LocalAsignacion.local_nombre)
        .join(User, User.id == LocalAsignacion.user_id)
        .where(LocalAsignacion.tipo == tipo, User.is_active == True)  # noqa: E712
        .distinct()
    )).scalars().all()
    return sorted(nombres, key=str.casefold)


async def _asignaciones(db: AsyncSession, user_id: int) -> set[tuple[str, str]]:
    filas = await db.execute(
        select(LocalAsignacion.local_nombre, LocalAsignacion.tipo).where(LocalAsignacion.user_id == user_id)
    )
    return {(n, t) for n, t in filas.all()}


async def _usuarios_de(db: AsyncSession, tipo: str, locales) -> dict[str, list[int]]:
    """Los logins activos de cada local: a quienes les llega el aviso."""
    locales = list(locales)
    if not locales:
        return {}
    out: dict[str, list[int]] = {}
    for nombre, uid in (await db.execute(
        select(LocalAsignacion.local_nombre, LocalAsignacion.user_id)
        .join(User, User.id == LocalAsignacion.user_id)
        .where(LocalAsignacion.tipo == tipo, LocalAsignacion.local_nombre.in_(locales), User.is_active == True)  # noqa: E712
    )).all():
        out.setdefault(nombre, []).append(uid)
    return out


def _avisar(db: AsyncSession, user_ids, tipo: str, mensaje: str, ref: str) -> int:
    n = 0
    for uid in user_ids:
        db.add(Notificacion(user_id=uid, tipo=tipo, mensaje=mensaje, origen_tipo=tipo, origen_ref=ref))
        n += 1
    return n


async def _borrar_avisos_del_local(db: AsyncSession, barra_id: str, local_ids) -> None:
    """Cuando a un local lo sacan del pedido (o se cancela), el "te pidieron
    una foto" que todavía tiene en la campanita ya no lleva a nada."""
    refs = [referencia_local(barra_id, i) for i in local_ids]
    if refs:
        await db.execute(delete(Notificacion).where(
            Notificacion.origen_tipo.in_(ORIGENES_DEL_LOCAL), Notificacion.origen_ref.in_(refs),
        ))


async def _barra_de_promo(db: AsyncSession, barra_id: str, usuario: User, *, bloquear: bool = False) -> CalendarioBarra:
    consulta = select(CalendarioBarra).where(CalendarioBarra.id == barra_id)
    if bloquear:
        consulta = consulta.with_for_update()
    barra = (await db.execute(consulta)).scalar_one_or_none()
    if barra is None:
        raise HTTPException(status_code=404, detail="Esta acción ya no existe: la borró otra persona.")
    exigir_mundo(usuario, barra.mundo)
    return barra


async def _pedido_de_promo(
    db: AsyncSession, pedido_id: int, usuario: User, *, bloquear: bool = False,
) -> tuple[ColocacionPedido, CalendarioBarra]:
    consulta = (
        select(ColocacionPedido, CalendarioBarra)
        .join(CalendarioBarra, CalendarioBarra.id == ColocacionPedido.barra_id)
        .where(ColocacionPedido.id == pedido_id)
    )
    if bloquear:
        # populate_existing: lo bloqueado se lee de nuevo aunque ya estuviera
        # cargado en la sesión, si no se seguiría usando la copia de antes.
        consulta = consulta.with_for_update(of=ColocacionPedido).execution_options(populate_existing=True)
    fila = (await db.execute(consulta)).first()
    if fila is None:
        raise HTTPException(status_code=404, detail=_NO_ESTA)
    exigir_mundo(usuario, fila[1].mundo)
    return fila[0], fila[1]


async def _local_con_pedido(
    db: AsyncSession, local_id: int, *, bloquear: bool = False,
) -> tuple[ColocacionLocal, ColocacionPedido, CalendarioBarra]:
    consulta = (
        select(ColocacionLocal, ColocacionPedido, CalendarioBarra)
        .join(ColocacionPedido, ColocacionPedido.id == ColocacionLocal.pedido_id)
        .join(CalendarioBarra, CalendarioBarra.id == ColocacionPedido.barra_id)
        .where(ColocacionLocal.id == local_id)
    )
    if bloquear:
        consulta = consulta.with_for_update(of=ColocacionLocal).execution_options(populate_existing=True)
    fila = (await db.execute(consulta)).first()
    if fila is None:
        raise HTTPException(status_code=404, detail=_NO_ESTA)
    return fila[0], fila[1], fila[2]


async def _avisar_si_mandaron_todos(db: AsyncSession, pedido: ColocacionPedido, barra: CalendarioBarra) -> None:
    """El único aviso a promo: cuando el último local manda su foto. Una vez
    por pedido (se vuelve a armar si se suman locales)."""
    if pedido.aviso_completo_at is not None or not pedido.creado_por_id:
        return
    estados = (await db.execute(
        select(ColocacionLocal.estado).where(ColocacionLocal.pedido_id == pedido.id)
    )).scalars().all()
    if not reglas.mandaron_todos(list(estados)):
        return
    pedido.aviso_completo_at = datetime.now(timezone.utc)
    quien = await db.get(User, pedido.creado_por_id)
    if quien is not None and quien.is_active and es_promo_del_mundo(quien, barra.mundo):
        _avisar(db, [quien.id], ORIGEN_COMPLETA, mensaje_completa(barra.nombre, len(estados)),
                referencia_pedido(barra.id, pedido.id))


# ---------------------------------------------------------------------------
# Promo
# ---------------------------------------------------------------------------

def _fecha_limite(v: date) -> date:
    return _fecha_razonable(v)


FechaLimite = Annotated[date, AfterValidator(_fecha_limite)]


class PedidoNuevo(BaseModel):
    # None = todos los locales del tipo del mundo.
    locales: list[str] | None = Field(None, max_length=500)
    limite: FechaLimite | None = None
    indicacion: str | None = Field(None, max_length=1000)

    @field_validator("indicacion")
    @classmethod
    def _sin_espacios(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class PedidoCambios(BaseModel):
    """Solo lo que vino. `locales` es la lista ENTERA como tiene que quedar:
    se suman los nuevos y se sacan los que no están."""
    locales: list[str] | None = Field(None, max_length=500)
    limite: FechaLimite | None = None
    indicacion: str | None = Field(None, max_length=1000)


class Devolucion(BaseModel):
    comentario: str = Field(..., min_length=1, max_length=1000)

    @field_validator("comentario")
    @classmethod
    def _con_algo(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Escribí qué hay que arreglar: es lo que le llega al local")
        return v


def _validar_locales(pedidos: list[str], disponibles: list[str]) -> list[str]:
    """Los locales pedidos, sin repetir, y todos de los que pueden subir."""
    limpios = list(dict.fromkeys(n.strip() for n in pedidos if n and n.strip()))
    if not limpios:
        raise HTTPException(status_code=422, detail="Elegí al menos un local")
    validos = set(disponibles)
    faltan = [n for n in limpios if n not in validos]
    if faltan:
        raise HTTPException(
            status_code=422,
            detail=f"{faltan[0]} no es un local con usuario: no podría subir la foto" if len(faltan) == 1
            else f"Hay {len(faltan)} locales elegidos que no tienen usuario: no podrían subir la foto",
        )
    return limpios


@router.get("/disponibles")
async def locales_disponibles(
    mundo: str,
    current_user: User = Depends(require_permission(PERMISO)),
    db: AsyncSession = Depends(get_db),
):
    """Los locales a los que se les puede pedir una foto en ese mundo. Una
    lista vacía quiere decir que en ese mundo no se piden fotos (todavía): el
    front no muestra la pestaña."""
    exigir_mundo(current_user, mundo)
    tipo = reglas.tipo_de_local(mundo)
    return {"mundo": mundo, "tipoLocal": tipo, "locales": await _disponibles(db, tipo)}


@router.get("/acciones/{barra_id}")
async def tablero(
    barra_id: str,
    current_user: User = Depends(require_permission(PERMISO)),
    db: AsyncSession = Depends(get_db),
):
    """El tablero de una acción: el pedido con cada local y sus fotos. Sin
    pedido, lo que hace falta para pedir (los locales y la fecha por defecto)."""
    barra = await _barra_de_promo(db, barra_id, current_user)
    hoy = hoy_en_uruguay()
    tipo = reglas.tipo_de_local(barra.mundo)
    pedido = (await db.execute(
        select(ColocacionPedido).where(ColocacionPedido.barra_id == barra_id)
    )).scalar_one_or_none()
    return {
        "accion": {
            "id": barra.id, "mundo": barra.mundo, "nombre": barra.nombre,
            "desde": barra.desde.isoformat(), "hasta": barra.hasta.isoformat(),
        },
        "hoy": hoy.isoformat(),
        "tipoLocal": pedido.tipo_local if pedido else tipo,
        "disponibles": await _disponibles(db, pedido.tipo_local if pedido else tipo),
        "limitePorDefecto": reglas.limite_por_defecto(barra.desde, hoy).isoformat(),
        "pedido": await _pedido_json(db, pedido, hoy) if pedido else None,
    }


@router.post("/acciones/{barra_id}", status_code=201)
async def pedir_fotos(
    barra_id: str,
    payload: PedidoNuevo,
    request: Request,
    current_user: User = Depends(require_permission(PERMISO)),
    db: AsyncSession = Depends(get_db),
):
    """Le pide la foto a los locales y le avisa a cada uno."""
    barra = await _barra_de_promo(db, barra_id, current_user, bloquear=True)
    if barra.seccion != "comercial":
        raise HTTPException(status_code=422, detail="Las fotos de colocación se piden en las acciones del calendario comercial")
    tipo = reglas.tipo_de_local(barra.mundo)
    if tipo is None:
        raise HTTPException(status_code=422, detail=f"En {MUNDOS.get(barra.mundo, barra.mundo)} no hay locales para pedirles fotos")
    if (await db.execute(select(ColocacionPedido.id).where(ColocacionPedido.barra_id == barra_id))).first():
        raise HTTPException(status_code=409, detail="Esta acción ya tiene un pedido de fotos: sumá o sacá locales desde el tablero.")
    hoy = hoy_en_uruguay()
    disponibles = await _disponibles(db, tipo)
    if not disponibles:
        raise HTTPException(status_code=422, detail="Todavía no hay locales con usuario para pedirles la foto")
    locales = _validar_locales(payload.locales if payload.locales is not None else disponibles, disponibles)
    limite = payload.limite or reglas.limite_por_defecto(barra.desde, hoy)
    if limite < hoy:
        raise HTTPException(status_code=422, detail="La fecha límite no puede ser anterior a hoy")

    pedido = ColocacionPedido(
        barra_id=barra_id, tipo_local=tipo, limite=limite, indicacion=payload.indicacion,
        creado_por_id=current_user.id,
    )
    db.add(pedido)
    await db.flush()
    filas = [ColocacionLocal(pedido_id=pedido.id, local_nombre=n, estado=reglas.PENDIENTE) for n in locales]
    db.add_all(filas)
    await db.flush()
    usuarios = await _usuarios_de(db, tipo, locales)
    texto = mensaje_pedido(barra.nombre, limite)
    avisados = sum(
        _avisar(db, usuarios.get(f.local_nombre, []), ORIGEN_PEDIDO, texto, referencia_local(barra_id, f.id))
        for f in filas
    )
    db.add(AuditLog(
        user_id=current_user.id, action="colocacion.pedir", resource="calendario_barra", resource_id=barra_id,
        details={"locales": len(locales), "limite": limite.isoformat()}, ip_address=client_ip(request),
    ))
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    # created_at lo pone la base: sin esto, leerlo acá rompe (sesión async).
    await db.refresh(pedido)
    return {"rev": rev, "avisados": avisados, "pedido": await _pedido_json(db, pedido, hoy)}


@router.patch("/pedidos/{pedido_id}")
async def cambiar_pedido(
    pedido_id: int,
    payload: PedidoCambios,
    current_user: User = Depends(require_permission(PERMISO)),
    db: AsyncSession = Depends(get_db),
):
    pedido, barra = await _pedido_de_promo(db, pedido_id, current_user, bloquear=True)
    hoy = hoy_en_uruguay()
    campos = payload.model_fields_set
    avisados = 0
    if "limite" in campos and payload.limite is not None and payload.limite != pedido.limite:
        if payload.limite < hoy:
            raise HTTPException(status_code=422, detail="La fecha límite no puede ser anterior a hoy")
        pedido.limite = payload.limite
    if "indicacion" in campos:
        pedido.indicacion = (payload.indicacion or "").strip() or None
    if "locales" in campos and payload.locales is not None:
        actuales = {
            l.local_nombre: l for l in (await db.execute(
                select(ColocacionLocal).where(ColocacionLocal.pedido_id == pedido.id)
            )).scalars()
        }
        # Un local que ya estaba sigue valiendo aunque hoy no tenga login
        # (se lo dieron de baja): sacarlo es decisión de quien edita.
        disponibles = sorted(set(await _disponibles(db, pedido.tipo_local)) | set(actuales), key=str.casefold)
        quedan = _validar_locales(payload.locales, disponibles)
        nuevos = [n for n in quedan if n not in actuales]
        sacados = [l for n, l in actuales.items() if n not in set(quedan)]
        if sacados:
            await _borrar_avisos_del_local(db, barra.id, [l.id for l in sacados])
            await db.execute(delete(ColocacionLocal).where(ColocacionLocal.id.in_([l.id for l in sacados])))
        if nuevos:
            filas = [ColocacionLocal(pedido_id=pedido.id, local_nombre=n, estado=reglas.PENDIENTE) for n in nuevos]
            db.add_all(filas)
            await db.flush()
            usuarios = await _usuarios_de(db, pedido.tipo_local, nuevos)
            texto = mensaje_pedido(barra.nombre, pedido.limite)
            avisados = sum(
                _avisar(db, usuarios.get(f.local_nombre, []), ORIGEN_PEDIDO, texto, referencia_local(barra.id, f.id))
                for f in filas
            )
            # Con locales nuevos, "mandaron todos" vuelve a estar por pasar.
            pedido.aviso_completo_at = None
        elif sacados:
            # Sacar a los que faltaban puede dejar el pedido completo.
            await db.flush()
            await _avisar_si_mandaron_todos(db, pedido, barra)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"rev": rev, "avisados": avisados, "pedido": await _pedido_json(db, pedido, hoy)}


@router.delete("/pedidos/{pedido_id}")
async def cancelar_pedido(
    pedido_id: int,
    request: Request,
    current_user: User = Depends(require_permission(PERMISO)),
    db: AsyncSession = Depends(get_db),
):
    """Cancela el pedido entero: se van los estados y las fotos."""
    pedido, barra = await _pedido_de_promo(db, pedido_id, current_user, bloquear=True)
    ids = (await db.execute(
        select(ColocacionLocal.id).where(ColocacionLocal.pedido_id == pedido.id)
    )).scalars().all()
    await _borrar_avisos_del_local(db, barra.id, ids)
    db.add(AuditLog(
        user_id=current_user.id, action="colocacion.cancelar", resource="calendario_barra", resource_id=barra.id,
        details={"pedido": pedido.id, "locales": len(ids), "accion": barra.nombre}, ip_address=client_ip(request),
    ))
    await db.delete(pedido)
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"rev": rev, "cancelado": True}


async def _local_de_promo(db: AsyncSession, local_id: int, usuario: User):
    local, pedido, barra = await _local_con_pedido(db, local_id, bloquear=True)
    exigir_mundo(usuario, barra.mundo)
    return local, pedido, barra


@router.post("/locales/{local_id}/aprobar")
async def aprobar(
    local_id: int,
    current_user: User = Depends(require_permission(PERMISO)),
    db: AsyncSession = Depends(get_db),
):
    local, pedido, barra = await _local_de_promo(db, local_id, current_user)
    fotos = (await db.execute(
        select(func.count(ColocacionFoto.id)).where(ColocacionFoto.local_id == local.id)
    )).scalar_one()
    if not fotos:
        raise HTTPException(status_code=409, detail=f"{local.local_nombre} todavía no mandó ninguna foto")
    if local.estado != reglas.APROBADA:
        local.estado = reglas.APROBADA
        local.revisado_por_id = current_user.id
        local.revisado_at = datetime.now(timezone.utc)
        # Si se aprueba una que se había devuelto (se cambió de idea), sus
        # fotos dejan de figurar como devueltas.
        await db.execute(
            ColocacionFoto.__table__.update().where(ColocacionFoto.local_id == local.id).values(devuelta=False)
        )
        await _avisar_si_mandaron_todos(db, pedido, barra)
    await db.commit()
    hoy = hoy_en_uruguay()
    nombres = await _nombres(db, [local.revisado_por_id])
    return _local_json(local, pedido, (await _fotos_de(db, [local.id])).get(local.id, []), hoy, nombres)


@router.post("/locales/{local_id}/devolver")
async def devolver(
    local_id: int,
    payload: Devolucion,
    current_user: User = Depends(require_permission(PERMISO)),
    db: AsyncSession = Depends(get_db),
):
    """Le devuelve la foto al local con lo que hay que arreglar. Las fotos
    quedan a la vista (marcadas como devueltas) hasta que mande la nueva."""
    local, pedido, barra = await _local_de_promo(db, local_id, current_user)
    if local.estado not in (reglas.ENVIADA, reglas.APROBADA):
        raise HTTPException(status_code=409, detail=f"{local.local_nombre} no tiene una foto para devolver")
    local.estado = reglas.DEVUELTA
    local.comentario = payload.comentario
    local.revisado_por_id = current_user.id
    local.revisado_at = datetime.now(timezone.utc)
    await db.execute(
        ColocacionFoto.__table__.update().where(ColocacionFoto.local_id == local.id).values(devuelta=True)
    )
    usuarios = await _usuarios_de(db, pedido.tipo_local, [local.local_nombre])
    _avisar(db, usuarios.get(local.local_nombre, []), ORIGEN_DEVUELTA,
            mensaje_devuelta(barra.nombre, payload.comentario), referencia_local(barra.id, local.id))
    await db.commit()
    hoy = hoy_en_uruguay()
    nombres = await _nombres(db, [local.revisado_por_id])
    return _local_json(local, pedido, (await _fotos_de(db, [local.id])).get(local.id, []), hoy, nombres)


@router.get("/resumen")
async def resumen_del_mundo(
    mundo: str,
    current_user: User = Depends(require_permission(PERMISO)),
    db: AsyncSession = Depends(get_db),
):
    """La vista general: cada acción con pedido abierto, su porcentaje y los
    locales atrasados; abajo, las que se completaron hace poco."""
    exigir_mundo(current_user, mundo)
    hoy = hoy_en_uruguay()
    pares = (await db.execute(
        select(ColocacionPedido, CalendarioBarra)
        .join(CalendarioBarra, CalendarioBarra.id == ColocacionPedido.barra_id)
        .where(CalendarioBarra.mundo == mundo)
    )).all()
    por_pedido: dict[int, list] = {}
    if pares:
        for l in (await db.execute(
            select(ColocacionLocal.pedido_id, ColocacionLocal.local_nombre, ColocacionLocal.estado)
            .where(ColocacionLocal.pedido_id.in_([p.id for p, _ in pares]))
            .order_by(ColocacionLocal.local_nombre)
        )).all():
            por_pedido.setdefault(l.pedido_id, []).append(l)
    abiertas, completas = [], []
    for pedido, barra in pares:
        locales = por_pedido.get(pedido.id, [])
        visibles = [(l.local_nombre, reglas.estado_visible(l.estado, pedido.limite, hoy)) for l in locales]
        r = reglas.resumen([v for _, v in visibles])
        fila = {
            "pedidoId": pedido.id,
            "accion": {
                "id": barra.id, "nombre": barra.nombre, "color": barra.color,
                "desde": barra.desde.isoformat(), "hasta": barra.hasta.isoformat(),
            },
            "limite": pedido.limite.isoformat(),
            "indicacion": pedido.indicacion,
            "resumen": r,
            "atrasados": [n for n, v in visibles if v == reglas.ATRASADA],
        }
        if r["total"] and r["aprobadas"] == r["total"]:
            if barra.hasta >= hoy - timedelta(days=DIAS_COMPLETAS_EN_EL_RESUMEN):
                completas.append(fila)
        else:
            abiertas.append(fila)
    abiertas.sort(key=lambda f: (f["limite"], f["accion"]["desde"]))
    completas.sort(key=lambda f: f["accion"]["hasta"], reverse=True)
    ocupado = (await db.execute(select(func.coalesce(func.sum(ColocacionFoto.peso), 0)))).scalar_one()
    return {
        "mundo": mundo,
        "hoy": hoy.isoformat(),
        "tipoLocal": reglas.tipo_de_local(mundo),
        "abiertas": abiertas,
        "completas": completas,
        "espacio": {"ocupadoMb": round(ocupado / 1024 / 1024, 1), "topeMb": settings.COLOCACION_TOPE_MB, "retencionDias": settings.COLOCACION_RETENCION_DIAS},
    }


# ---------------------------------------------------------------------------
# El local
# ---------------------------------------------------------------------------

def _mi_pedido_json(l: ColocacionLocal, pedido: ColocacionPedido, barra: CalendarioBarra, fotos: list, hoy: date) -> dict:
    """Lo que ve el local de un pedido: la acción (nombre y fechas, nada más
    del calendario), qué fotografiar, hasta cuándo y sus fotos."""
    activas = [f for f in fotos if not f.devuelta]
    return {
        "id": l.id,
        "local": l.local_nombre,
        "estado": l.estado,
        "visible": reglas.estado_visible(l.estado, pedido.limite, hoy),
        # El comentario es de la última devolución: se muestra mientras siga devuelta.
        "comentario": l.comentario if l.estado == reglas.DEVUELTA else None,
        "limite": pedido.limite.isoformat(),
        "indicacion": pedido.indicacion,
        "accion": {"nombre": barra.nombre, "desde": barra.desde.isoformat(), "hasta": barra.hasta.isoformat()},
        "fotos": [_foto_json(f) for f in fotos],
        "puedeSubir": reglas.puede_subir(l.estado) and len(activas) < reglas.MAX_FOTOS_POR_LOCAL,
        "quedan": max(0, reglas.MAX_FOTOS_POR_LOCAL - len(activas)) if reglas.puede_subir(l.estado) else 0,
    }


@router.get("/mis-fotos")
async def mis_fotos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lo que tiene que subir el local que entró: lo de sus locales, en los
    mundos que abre. Lo abierto primero (por fecha límite) y, abajo, lo
    aprobado hace poco. Quien no tiene locales asignados recibe una lista
    vacía (no un error): la pantalla dice que no hay nada."""
    asignaciones = await _asignaciones(db, current_user.id)
    if not asignaciones:
        return {"locales": [], "pedidos": [], "maxFotos": reglas.MAX_FOTOS_POR_LOCAL}
    hoy = hoy_en_uruguay()
    desde_accion = hoy - timedelta(days=DIAS_VISIBLE_DESPUES_DE_LA_ACCION)
    desde_aprobada = datetime.now(timezone.utc) - timedelta(days=DIAS_VISIBLE_APROBADA)
    filas = (await db.execute(
        select(ColocacionLocal, ColocacionPedido, CalendarioBarra)
        .join(ColocacionPedido, ColocacionPedido.id == ColocacionLocal.pedido_id)
        .join(CalendarioBarra, CalendarioBarra.id == ColocacionPedido.barra_id)
        .where(
            ColocacionLocal.local_nombre.in_(sorted({n for n, _ in asignaciones})),
            CalendarioBarra.mundo.in_(mundos_de(current_user)),
        )
    )).all()
    propias = [
        (l, p, b) for l, p, b in filas
        if es_del_local(current_user, asignaciones, l.local_nombre, p.tipo_local, b.mundo)
        and (
            (l.estado != reglas.APROBADA and b.hasta >= desde_accion)
            or (l.estado == reglas.APROBADA and l.revisado_at is not None and l.revisado_at >= desde_aprobada)
        )
    ]
    fotos = await _fotos_de(db, [l.id for l, _, _ in propias])
    pedidos = [_mi_pedido_json(l, p, b, fotos.get(l.id, []), hoy) for l, p, b in propias]
    # Primero lo que hay que hacer (atrasado, devuelto, pendiente), después lo
    # que espera revisión y al final lo aprobado. Dentro, por fecha límite.
    orden = {reglas.ATRASADA: 0, reglas.DEVUELTA: 1, reglas.PENDIENTE: 2, reglas.ENVIADA: 3, reglas.APROBADA: 4}
    pedidos.sort(key=lambda x: (orden.get(x["visible"], 5), x["limite"], x["local"]))
    return {
        "locales": sorted({n for n, _ in asignaciones}, key=str.casefold),
        "pedidos": pedidos,
        "maxFotos": reglas.MAX_FOTOS_POR_LOCAL,
    }


async def _local_propio(db: AsyncSession, local_id: int, usuario: User, *, bloquear: bool = False):
    local, pedido, barra = await _local_con_pedido(db, local_id, bloquear=bloquear)
    if not es_del_local(usuario, await _asignaciones(db, usuario.id), local.local_nombre, pedido.tipo_local, barra.mundo):
        raise HTTPException(status_code=404, detail=_NO_ESTA)
    return local, pedido, barra


async def _leer_archivo(form, campo: str) -> bytes | None:
    archivo = form.get(campo)
    if archivo is None or isinstance(archivo, str):
        return None
    return await archivo.read()


@router.post("/locales/{local_id}/fotos", status_code=201)
@limiter.limit("20/minute")
async def subir_foto(
    local_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sube una foto del local. Llega como formulario con `foto` (ya achicada
    en el teléfono) y `miniatura`; si la miniatura no vino, se hace acá.

    El cuerpo se lee a mano (y no con UploadFile en la firma) para poder
    frenar una subida enorme mirando el Content-Length, antes de recibirla."""
    largo = request.headers.get("content-length")
    if largo is None:
        raise HTTPException(status_code=411, detail="Falta el tamaño de la subida")
    try:
        largo_n = int(largo)
    except ValueError:
        raise HTTPException(status_code=400, detail="Subida inválida")
    if largo_n > _MAX_CUERPO:
        raise HTTPException(status_code=413, detail="La foto es demasiado pesada: el máximo es 3 MB")

    # Primero si es suyo y si todavía se puede: un 404 o un 409 sale antes de
    # recibir la foto.
    local, pedido, barra = await _local_propio(db, local_id, current_user)
    if not reglas.puede_subir(local.estado):
        raise HTTPException(status_code=409, detail=_YA_APROBADA)
    # Mientras llega la foto (desde un teléfono con mala señal pueden ser
    # varios segundos) la conexión a la base vuelve al pool: con 60 locales
    # subiendo a la vez, tenerlas tomadas esperando la red agotaba las 35.
    await db.commit()

    try:
        form = await request.form(max_files=2, max_fields=4)
    except Exception:
        raise HTTPException(status_code=400, detail="No se pudo leer la subida. Probá de nuevo.")
    try:
        datos = await _leer_archivo(form, "foto")
        mini = await _leer_archivo(form, "miniatura")
    finally:
        await form.close()
    if datos is None:
        raise HTTPException(status_code=422, detail="Falta la foto")
    try:
        imagen = reglas.validar_imagen(datos)
        if mini:
            tipo_mini = reglas.validar_imagen(mini, reglas.MAX_BYTES_MINIATURA, "La miniatura").tipo
        else:
            mini, tipo_mini = reglas.hacer_miniatura(datos), "image/jpeg"
    except reglas.ImagenInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Ahora sí, bloqueado: dos fotos del mismo local llegando juntas se
    # ordenan y la cuenta de "hasta 3" no se pasa. El estado se vuelve a
    # mirar: pudieron aprobarla mientras subía.
    local, pedido, barra = await _local_con_pedido(db, local_id, bloquear=True)
    if not reglas.puede_subir(local.estado):
        raise HTTPException(status_code=409, detail=_YA_APROBADA)

    # Las devueltas se van cuando llega la nueva: ya cumplieron (el local vio
    # qué le devolvieron) y así no se acumulan.
    if local.estado == reglas.DEVUELTA:
        await db.execute(delete(ColocacionFoto).where(
            ColocacionFoto.local_id == local.id, ColocacionFoto.devuelta == True,  # noqa: E712
        ))
    activas = (await db.execute(
        select(func.count(ColocacionFoto.id)).where(ColocacionFoto.local_id == local.id)
    )).scalar_one()
    if activas >= reglas.MAX_FOTOS_POR_LOCAL:
        raise HTTPException(
            status_code=409,
            detail=f"Ya subiste {reglas.MAX_FOTOS_POR_LOCAL} fotos para este pedido: sacá una para subir otra",
        )
    peso = len(datos) + len(mini)
    ocupado = (await db.execute(select(func.coalesce(func.sum(ColocacionFoto.peso), 0)))).scalar_one()
    if not reglas.entra_en_el_tope(ocupado, peso, settings.COLOCACION_TOPE_MB):
        logger.error("colocacion: se llegó al tope de %d MB de fotos", settings.COLOCACION_TOPE_MB)
        raise HTTPException(
            status_code=507,
            detail="No hay más lugar para fotos en este momento. Avisale a marketing.",
        )
    if not await hay_lugar(db, peso):
        raise HTTPException(status_code=507, detail=MENSAJE_SIN_LUGAR)

    db.add(ColocacionFoto(
        local_id=local.id, subida_por_id=current_user.id, tipo=imagen.tipo, tipo_miniatura=tipo_mini,
        ancho=imagen.ancho, alto=imagen.alto, peso=peso, devuelta=False, datos=datos, miniatura=mini,
    ))
    local.estado = reglas.ENVIADA
    local.enviada_at = datetime.now(timezone.utc)
    await db.flush()
    await _avisar_si_mandaron_todos(db, pedido, barra)
    await db.commit()
    hoy = hoy_en_uruguay()
    return _mi_pedido_json(local, pedido, barra, (await _fotos_de(db, [local.id])).get(local.id, []), hoy)


@router.delete("/fotos/{foto_id}")
async def sacar_foto(
    foto_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """El local saca una foto suya (se equivocó de foto) mientras no la
    aprobaron. Si era la última, el pedido vuelve a quedar para subir."""
    local_id = (await db.execute(
        select(ColocacionFoto.local_id).where(ColocacionFoto.id == foto_id)
    )).scalar_one_or_none()
    if local_id is None:
        raise HTTPException(status_code=404, detail="Esa foto ya no está")
    local, pedido, barra = await _local_propio(db, local_id, current_user, bloquear=True)
    if local.estado == reglas.APROBADA:
        raise HTTPException(status_code=409, detail="Esta foto ya está aprobada: no se puede sacar")
    await db.execute(delete(ColocacionFoto).where(ColocacionFoto.id == foto_id))
    quedan = (await db.execute(
        select(func.count(ColocacionFoto.id)).where(
            ColocacionFoto.local_id == local.id, ColocacionFoto.devuelta == False,  # noqa: E712
        )
    )).scalar_one()
    if quedan == 0:
        local.estado = reglas.estado_al_sacar_la_ultima(local.estado, local.comentario)
    await db.commit()
    hoy = hoy_en_uruguay()
    return _mi_pedido_json(local, pedido, barra, (await _fotos_de(db, [local.id])).get(local.id, []), hoy)


# ---------------------------------------------------------------------------
# La imagen
# ---------------------------------------------------------------------------

# Su propio balde, y grande: el tablero de una acción pide la miniatura de
# cada local (60) y con el balde general (200 por minuto, compartido con el
# calendario y la campanita) abrir dos tableros seguidos daba 429.
@router.get("/fotos/{foto_id}")
@limiter.limit("600/minute")
async def ver_foto(
    foto_id: int,
    request: Request,
    tamano: Literal["mini", "grande"] = "grande",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """La imagen, para promo del mundo de la acción o para el local que la
    subió. Se trae solo la columna pedida: la miniatura del tablero no carga
    la foto grande.

    Una foto no cambia nunca (si el local manda otra, es otra foto, con otro
    id): el navegador la guarda un año y no la vuelve a pedir. "private"
    porque es de una persona con sesión: ningún proxy en el medio la guarda."""
    columna = ColocacionFoto.miniatura if tamano == "mini" else ColocacionFoto.datos
    tipo = ColocacionFoto.tipo_miniatura if tamano == "mini" else ColocacionFoto.tipo
    fila = (await db.execute(
        select(ColocacionFoto.local_id, ColocacionLocal.local_nombre, ColocacionPedido.tipo_local, CalendarioBarra.mundo)
        .join(ColocacionLocal, ColocacionLocal.id == ColocacionFoto.local_id)
        .join(ColocacionPedido, ColocacionPedido.id == ColocacionLocal.pedido_id)
        .join(CalendarioBarra, CalendarioBarra.id == ColocacionPedido.barra_id)
        .where(ColocacionFoto.id == foto_id)
    )).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Esa foto ya no está")
    puede = es_promo_del_mundo(current_user, fila.mundo) or es_del_local(
        current_user, await _asignaciones(db, current_user.id), fila.local_nombre, fila.tipo_local, fila.mundo,
    )
    if not puede:
        raise HTTPException(status_code=404, detail="Esa foto ya no está")
    datos, media = (await db.execute(select(columna, tipo).where(ColocacionFoto.id == foto_id))).one()
    return Response(
        content=datos,
        media_type=media,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            # Ya viene comprimida: que el GZip de la app no pierda tiempo con ella.
            "Content-Encoding": "identity",
        },
    )
