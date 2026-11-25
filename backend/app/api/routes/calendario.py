"""calendario.py — el calendario comercial, el de Retail Media y los headers.

  GET    /calendario/datos?rev=N              — todo, o "sin cambios" si sigue en la N
  GET    /calendario/personas                 — a quién se le puede mandar un aviso
  POST   /calendario/barras                   — una acción, campaña o banner nuevo
  PATCH  /calendario/barras/{id}              — cambia solo los campos que manda
  DELETE /calendario/barras/{id}
  POST   /calendario/barras/{id}/copiar       — la copia a otra fecha, con piezas, tareas y avisos
  POST   /calendario/barras/{id}/piezas       — agrega una pieza a una acción
  PATCH  /calendario/piezas/{id}              — estado, fecha u hora de una pieza
  DELETE /calendario/piezas/{id}
  POST   /calendario/barras/{id}/avisos       — configura un aviso en una acción
  DELETE /calendario/avisos/{id}
  PUT    /calendario/posiciones-rm/{clave}    — mueve las posiciones de RM de un mes
  POST   /calendario/barras/{id}/tareas       — una tarea de una acción (un pedido, en el primer nivel)
  PATCH  /calendario/tareas/{id}              — título, estado, a quién, cuándo vence
  DELETE /calendario/tareas/{id}
  GET    /calendario/mis-tareas               — lo que tengo asignado, de todos mis mundos
  GET    /calendario/ubicar/{id}              — en qué mundo está una acción
  PUT    /calendario/plantillas/{id}          — crea o reemplaza una plantilla de tareas
  DELETE /calendario/plantillas/{id}
  POST   /calendario/barras/{id}/plantilla    — crea en una acción las tareas de una plantilla

Las plantillas (0065) viajan con /datos, como todo lo del mundo: guardar una
sube la revisión y los demás la ven aparecer sola.

Las fotos de colocación que se le piden a los locales desde la ficha de una
acción están en routes/colocacion.py. Acá solo viaja, en cada acción que tiene
un pedido, cuántos locales y hasta cuándo (`fotos`): nunca las fotos.

Las entregas por fases de una tarea (0067) están en entregas.py.

Cuánto del calendario ve cada persona lo dice su alcance (0070, app/core/
alcance.py): No lo ve / 1 mes / 2 meses / 12 meses / Todo. Quien no lo ve
recibe 403 en todo lo de acá; quien lo ve limitado, solo las acciones que
tocan su ventana. Vale igual para el equipo y para la agencia.

Las cuentas externas (la agencia, 0069) además ven la vista limitada de
app/core/externos.py: solo sus tareas, sin avisos ni plantillas ni fotos
de colocación, y de las personas solo las de su empresa y quienes aprueban sus
entregas. Se cuida en cada ruta de lectura de acá (/datos y su revisión,
/personas, /mis-tareas, /ubicar) y en `_barra_o_404`, por donde pasa todo lo
que se toca por el id de una acción: fuera de su alcance, para esa persona la
acción no existe.

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
from types import SimpleNamespace
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import client_ip as _client_ip, require_permission
from app.core import alcance, externos
from app.core.tableros import TABLEROS, tablero_de
from app.core.mundos import MUNDO_POR_DEFECTO, MUNDOS, exigir_mundo, mundos_de, puede_abrir
from app.models.adjuntos import CalendarioAdjunto
from app.models.audit_log import AuditLog
from app.models.entregas import CalendarioDecision, CalendarioEntrega, CalendarioMarca, CalendarioVersion
from app.models.calendario import (
    CalendarioAviso, CalendarioBarra, CalendarioPieza, CalendarioPlantilla, CalendarioPosicionesRM,
    CalendarioRevision, CalendarioRevisionMundo,
    CalendarioTarea,
)
from app.models.colocacion import ColocacionLocal, ColocacionPedido
from app.models.notificacion import Notificacion
from app.models.user import User
from app.services.calendario_avisos import SIN_CATEGORIA, puede_ver_el_calendario, revisar_avisos
from app.services.calendario_copia import (
    copiar_avisos, copiar_la_accion, copiar_piezas, copiar_tareas, fechas_corridas, ids_de_personas,
    nombre_para_la_copia, tareas_por_responsable,
)
from app.services.colocacion import ORIGENES_DEL_LOCAL
from app.services import agencias, controles_redexpres, entregas as reglas_entregas, tipos_de_tarea
from app.services.entregas import resumenes_de_entregas

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
# Para quién es una tarea (0070) y desde dónde se cuenta un vencimiento
# anclado a la acción (0065).
ParaQuien = Literal["tienda", "agencia", "fuera"]
Ancla = Literal["inicio", "fin"]
_DIAS_DE_ANCLA = 365
PERMISO_TAREAS = "calendario.tareas"
# Desde el 24/11/2026 (0090) las tareas van todas en un solo nivel: "una
# tarea = un pedido". Lo que pide una tarea adentro de otra se rechaza con esto.
_UN_SOLO_NIVEL = (
    "Las tareas van todas en el primer nivel: ya no hay subtareas ni piezas adentro de otra tarea. "
    "Recargá la página."
)

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


async def _avisar_sin_romper(db: AsyncSession, barra_id: str | None) -> int:
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
    # Una acción fuera del alcance de la persona (0070) no existe para ella:
    # el mismo 404 que una borrada, así no se puede deducir que está. Quien no
    # ve el calendario no ve ninguna.
    if not alcance.toca(barra.desde, barra.hasta, alcance.ventana_de(usuario)):
        raise HTTPException(status_code=404, detail=_YA_NO_EXISTE)
    return barra


async def _exigir_mundo_de(db: AsyncSession, barra_id: str | None, usuario: User) -> str | None:
    """Para lo que se toca por su propio id (una pieza, un aviso): que la
    acción de la que cuelga sea de un mundo de la persona. Si la acción ya no
    está, no hay nada que cuidar. Devuelve el mundo (para la revisión)."""
    if barra_id is None:
        return None
    fila = (await db.execute(
        select(CalendarioBarra.mundo, CalendarioBarra.desde, CalendarioBarra.hasta)
        .where(CalendarioBarra.id == barra_id)
    )).first()
    if fila is None:
        return None
    exigir_mundo(usuario, fila.mundo)
    if not alcance.toca(fila.desde, fila.hasta, alcance.ventana_de(usuario)):
        raise HTTPException(status_code=404, detail=_YA_NO_EXISTE)
    return fila.mundo


def _puede_ver_el_mundo(usuario: User, mundo: str) -> bool:
    """Si la persona tiene el calendario de ese mundo (el permiso y el mundo).
    Es lo que hace falta para asignarle una tarea o ponerla a aprobar: aunque
    su alcance sea "No lo ve", su tablero de tarjetas lo sigue viendo."""
    return puede_ver_el_calendario(usuario) and puede_abrir(usuario, mundo)


def _exigir_en_su_alcance(usuario: User, desde: date, hasta: date) -> None:
    """Que una acción nueva (o la fecha nueva de una que se mueve) caiga en lo
    que la persona ve del calendario (0070): si no, la dejaría donde ella
    misma no la puede ver ni corregir."""
    alcance.exigir_calendario(usuario)
    if not alcance.toca(desde, hasta, alcance.ventana_de(usuario)):
        raise HTTPException(
            status_code=422,
            detail=f"Esa fecha queda fuera de lo que ves del calendario ({alcance.en_palabras(alcance.alcance_de(usuario))}). "
                   "Pedile a alguien que lo vea entero que la cargue.",
        )


def _ve_una_parte(usuario: User) -> bool:
    """Si a esta persona se le recorta lo que ve: una cuenta externa (solo lo
    suyo) o cualquiera con el alcance limitado. A ella no se le da el contador
    de todos, sino la huella de lo que ve (`externos.huella`)."""
    return externos.es_externo(usuario) or alcance.es_limitado(usuario)


def _rev_para(usuario: User, rev: int) -> int | None:
    """La revisión que se le devuelve a quien escribió. A quien ve una parte,
    ninguna: el contador es de todo el calendario y le diría cuánto se movió
    fuera de lo que ve (ver `externos.huella`). Su pantalla se pone al día
    sola en la próxima pregunta."""
    return None if _ve_una_parte(usuario) else rev


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
    out = {
        "id": a.id,
        "diasAntes": a.dias_antes,
        "destinatarios": list(a.destinatarios or []),
        "creadoPor": a.creado_por_id,
    }
    if a.pieza_id:
        # Se cuenta desde que sale ese envío (0084).
        out["piezaId"] = a.pieza_id
    if a.control:
        # Lanzar o Cierre (0077): le llega a todo el equipo del mundo.
        out["control"] = a.control
    return out


def _tarea_json(t: CalendarioTarea, entrega: dict | None = None, archivos: int = 0) -> dict:
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
    # Quién la hace y qué tipo de pieza es (0070): solo si no es lo de
    # siempre (una tarea común de Tienda), que /datos viaja entero cada vez.
    if t.para != "tienda":
        out["para"] = t.para
        out["agencia"] = t.agencia
    # Quién la lleva por Tienda cuando la hace una agencia (0090).
    if t.responsable_id is not None:
        out["responsable"] = t.responsable_id
    if t.tipo:
        out["tipo"] = t.tipo
        out["opciones"] = list(t.opciones or [])
        if t.detalles:
            out["detalles"] = dict(t.detalles)
    # Si lleva entregas por fases (0067): en qué fase va y a quién le toca.
    # Solo el resumen: las imágenes y la historia se piden al abrirla.
    if entrega is not None:
        out["entrega"] = entrega
    # Cuántos archivos lleva el pedido (24/11/2026): la fila de la tarea dice
    # "Publicis · 2 archivos" sin pedir la lista. Solo si tiene.
    if archivos:
        out["archivos"] = archivos
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
    tareas: list[CalendarioTarea] | None = None, fotos: dict | None = None,
    entregas: dict[str, dict] | None = None, archivos: dict[str, int] | None = None,
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
        # El pedido de foto de colocación, si tiene: cuántos locales y hasta
        # cuándo. Lo demás (estados, fotos) lo trae el tablero aparte.
        if fotos:
            out["fotos"] = fotos
    if b.seccion == "envio":
        out["formato"] = b.formato
        out["estado"] = b.estado or "pendiente"
        if b.hora:
            out["hora"] = b.hora
    if b.seccion in _CON_AVISOS:
        out["avisos"] = [_aviso_json(a) for a in avisos]
        out["tareas"] = [
            _tarea_json(t, (entregas or {}).get(t.id), (archivos or {}).get(t.id, 0)) for t in (tareas or [])
        ]
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
    """Todo el calendario de UN mundo que la persona ve. Si el front ya tiene
    la revisión actual, contesta solo eso y no viaja nada más.

    El contador es uno solo para todos los mundos, pero cada mundo anota la
    última revisión que lo tocó (0063): si nada de ESTE mundo cambió después
    de la revisión del front, es "sin cambios" aunque en otro mundo sí haya
    habido. Antes un cambio en Redexpres le hacía bajar todo de nuevo a quien
    miraba Tienda Inglesa. Una revisión más nueva que el contador (una base
    restaurada) se trata como vieja: se trae todo.

    La revisión se lee ANTES que los datos: si alguien guarda en el medio, los
    datos pueden venir un poco más nuevos que la revisión (y la próxima
    pregunta los vuelve a traer), pero nunca más viejos.

    Quien ve una parte (alcance limitado, o una cuenta externa) recibe solo
    eso, y como revisión la huella de lo que ve: ver `_datos_recortados`."""
    exigir_mundo(current_user, mundo)
    alcance.exigir_calendario(current_user)
    if _ve_una_parte(current_user):
        return await _datos_recortados(db, current_user, mundo, rev)
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
    return {"rev": actual, **await _armar_datos(db, mundo, None, None)}


async def _armar_datos(db: AsyncSession, mundo: str, v: alcance.Ventana | None, externo: User | None) -> dict:
    """El calendario de un mundo: las acciones que tocan la ventana `v` (sin
    ventana, todas) con sus piezas, avisos, tareas, pedidos de fotos y
    entregas; las posiciones de Retail Media de esos meses y las plantillas.

    Con `externo` (una cuenta externa, ver app/core/externos.py): de cada
    acción solo SUS tareas, sin avisos (son internos), sin plantillas y sin el
    pedido de fotos de colocación."""
    en_la_ventana = (CalendarioBarra.mundo == mundo, alcance.condicion(CalendarioBarra, v))
    barras = (await db.execute(
        select(CalendarioBarra).where(*en_la_ventana).order_by(CalendarioBarra.desde, CalendarioBarra.id)
    )).scalars().all()
    visibles = select(CalendarioBarra.id).where(*en_la_ventana)
    piezas: dict[str, list[CalendarioPieza]] = {}
    avisos: dict[str, list[CalendarioAviso]] = {}
    tareas: dict[str, list[CalendarioTarea]] = {}
    fotos: dict[str, dict] = {}
    if barras:
        for p in (await db.execute(
            select(CalendarioPieza).where(CalendarioPieza.barra_id.in_(visibles))
            .order_by(CalendarioPieza.orden, CalendarioPieza.id)
        )).scalars():
            piezas.setdefault(p.barra_id, []).append(p)
        consulta_tareas = select(CalendarioTarea).where(CalendarioTarea.barra_id.in_(visibles))
        if externo is not None:
            consulta_tareas = consulta_tareas.where(externos.condicion_tarea_propia(CalendarioTarea, externo))
        for t in (await db.execute(
            consulta_tareas.order_by(CalendarioTarea.orden, CalendarioTarea.created_at, CalendarioTarea.id)
        )).scalars():
            tareas.setdefault(t.barra_id, []).append(t)
        if externo is None:
            for a in (await db.execute(
                select(CalendarioAviso).where(CalendarioAviso.barra_id.in_(visibles))
                .order_by(CalendarioAviso.dias_antes.desc(), CalendarioAviso.id)
            )).scalars():
                avisos.setdefault(a.barra_id, []).append(a)
            fotos = {
                barra_id: {"pedido": pedido_id, "locales": n, "limite": limite.isoformat()}
                for barra_id, pedido_id, limite, n in (await db.execute(
                    select(
                        ColocacionPedido.barra_id, ColocacionPedido.id, ColocacionPedido.limite,
                        func.count(ColocacionLocal.id),
                    )
                    .join(ColocacionLocal, ColocacionLocal.pedido_id == ColocacionPedido.id, isouter=True)
                    .where(ColocacionPedido.barra_id.in_(visibles))
                    .group_by(ColocacionPedido.id)
                )).all()
            }
    ids_tareas = [t.id for ts in tareas.values() for t in ts]
    # Las entregas, con la misma consulta de las tareas como subconsulta (ya
    # lleva el filtro de la cuenta externa) y no con la lista de ids: con
    # años de tareas en un mundo, la lista armaba un IN de miles de valores,
    # y el driver corta en 32.767 (revisión del 16/11/2026).
    entregas = await resumenes_de_entregas(
        db, consulta_tareas.with_only_columns(CalendarioTarea.id),
    ) if ids_tareas else {}
    # Cuántos archivos tiene cada pedido, con la misma subconsulta: un número
    # por tarea, sin los archivos (que se piden al abrir la tarjeta).
    archivos: dict[str, int] = {
        tarea_id: n for tarea_id, n in (await db.execute(
            select(CalendarioAdjunto.tarea_id, func.count(CalendarioAdjunto.id))
            .where(CalendarioAdjunto.tarea_id.in_(consulta_tareas.with_only_columns(CalendarioTarea.id)))
            .group_by(CalendarioAdjunto.tarea_id)
        )).all()
    } if ids_tareas else {}
    # Retail Media es de la web de Tienda Inglesa: los otros mundos no tienen
    # esa parte del calendario y no tienen por qué bajar sus posiciones. Con
    # ventana, solo los meses que toca.
    posiciones: dict = {}
    if mundo == MUNDO_POR_DEFECTO:
        meses = alcance.meses_de(v)
        consulta_rm = select(CalendarioPosicionesRM)
        if meses is not None:
            consulta_rm = consulta_rm.where(CalendarioPosicionesRM.clave.in_(meses))
        posiciones = {p.clave: list(p.posiciones) for p in (await db.execute(consulta_rm)).scalars()}
    plantillas = [] if externo is not None else (await db.execute(
        select(CalendarioPlantilla).where(CalendarioPlantilla.mundo == mundo)
        .order_by(CalendarioPlantilla.nombre, CalendarioPlantilla.id)
    )).scalars().all()

    propias = set(ids_tareas)

    def barra_json(b: CalendarioBarra) -> dict:
        out = _barra_json(
            b, piezas.get(b.id, []), avisos.get(b.id, []), tareas.get(b.id, []), fotos.get(b.id), entregas, archivos,
        )
        if externo is not None:
            # Una tarea suya que cuelga de otra que no es suya (la madre la
            # tiene alguien del equipo) se muestra suelta: la madre no viaja.
            for t in out.get("tareas", []):
                if t["parentId"] is not None and t["parentId"] not in propias:
                    t["parentId"] = None
        return out

    return {
        "mundo": mundo,
        "barras": [barra_json(b) for b in barras],
        "posicionesRM": posiciones,
        "plantillas": [_plantilla_json(p) for p in plantillas],
    }


async def _datos_recortados(db: AsyncSession, usuario: User, mundo: str, rev: int | None) -> dict:
    """/datos para quien ve una parte: las acciones que tocan su ventana (su
    alcance, app/core/alcance.py) y, si es una cuenta externa, solo lo suyo
    (ver `_armar_datos`).

    La revisión es la huella de esto mismo (`externos.huella`), no el contador
    de todo el calendario: si lo que ve no cambió, "sin cambios", aunque
    afuera de lo que ve se haya movido todo. `opaca` le dice al front que no
    la compare como un contador (una huella nueva puede ser menor)."""
    datos = await _armar_datos(
        db, mundo, alcance.ventana_de(usuario), usuario if externos.es_externo(usuario) else None,
    )
    huella = externos.huella(datos)
    if rev is not None and rev == huella:
        return {"rev": huella, "sinCambios": True, "opaca": True}
    return {"rev": huella, "opaca": True, **datos}


async def ids_de_aprobadores_de(db: AsyncSession, usuario: User, mundo: str | None = None) -> set[int]:
    """Quiénes aprueban (o decidieron, o marcaron) las entregas de las tareas
    de una cuenta externa: son las personas del equipo con las que trabaja, y
    las únicas de afuera de su empresa que ve con nombre.

    Sin mirar la ventana: solo las tareas con entregas cuentan (`propias` se
    cruza con las entregas), y esas son sus tarjetas, que ve siempre (0070)."""
    propias = (
        select(CalendarioTarea.id)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .where(externos.condicion_tarea_propia(CalendarioTarea, usuario))
    )
    if mundo is not None:
        propias = propias.where(CalendarioBarra.mundo == mundo)
    ids: set[int] = set()
    for aprobadores, turno in (await db.execute(
        select(CalendarioEntrega.aprobadores, CalendarioEntrega.aprobador_de_turno_id)
        .where(CalendarioEntrega.tarea_id.in_(propias))
    )).all():
        ids.update(a for a in (aprobadores or []) if isinstance(a, int))
        if turno is not None:
            ids.add(turno)
    for (uid,) in (await db.execute(
        select(CalendarioDecision.decidido_por_id)
        .join(CalendarioVersion, CalendarioVersion.id == CalendarioDecision.version_id)
        .where(CalendarioVersion.tarea_id.in_(propias))
    )).all():
        if uid is not None:
            ids.add(uid)
    for (uid,) in (await db.execute(
        select(CalendarioMarca.autor_id).where(CalendarioMarca.tarea_id.in_(propias))
    )).all():
        if uid is not None:
            ids.add(uid)
    return ids


def nombre_sin_mail(u: User) -> str:
    """A una cuenta externa no le viaja el mail de nadie: si alguien no tiene
    nombre cargado, se lo nombra genérico."""
    return (u.full_name or "").strip() or externos.ALGUIEN_DEL_EQUIPO


def ve_el_nombre(externo: User, u: User, aprobadores: set[int]) -> bool:
    """Si una cuenta externa ve con nombre a `u`: es ella, es de su empresa o
    aprueba sus entregas."""
    return (
        u.id == externo.id or u.id in aprobadores
        or (externos.es_externo(u) and externos.misma_empresa(u.empresa, externo.empresa))
    )


async def nombres_para_externo(db: AsyncSession, usuario: User, ids, aprobadores: set[int]) -> dict[int, str]:
    """De esos ids, los nombres que una cuenta externa puede ver. Sin mail."""
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {
        u.id: nombre_sin_mail(u)
        for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()
        if ve_el_nombre(usuario, u, aprobadores)
    }


def _persona_json(u: User) -> dict:
    out = {"id": u.id, "nombre": u.full_name or u.email}
    # Para quien arma las tareas: que se vea que es de afuera y de qué empresa
    # (y el front no lo ofrece para avisos ni para aprobar).
    if externos.es_externo(u):
        out["externo"] = True
        out["empresa"] = u.empresa
    return out


@router.get("/personas")
async def listar_personas(
    mundo: str = MUNDO_POR_DEFECTO,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Quiénes pueden recibir un aviso o una tarea: los que pueden abrir el
    calendario de ese mundo. Solo id y nombre (y si es una cuenta externa, de
    qué empresa).

    A una cuenta externa le vuelven solo los de su empresa y quienes aprueban
    sus entregas, sin mail: no tiene por qué saber quién más trabaja acá.
    Quien no ve el calendario (0070) no la necesita: es para armar tareas y
    avisos desde la ficha de una acción... salvo quien gestiona las tareas:
    aunque no vea el calendario, abre sus tarjetas en el tablero y ahí elige
    los aprobadores de «Configurar» (revisión del 16/11/2026)."""
    exigir_mundo(current_user, mundo)
    if not _puede_gestionar_tareas(current_user):
        alcance.exigir_calendario(current_user)
    usuarios = (await db.execute(
        select(User).where(User.is_active == True).order_by(User.full_name)  # noqa: E712
    )).scalars().all()
    if externos.es_externo(current_user):
        aprobadores = await ids_de_aprobadores_de(db, current_user, mundo)
        return [
            {"id": u.id, "nombre": nombre_sin_mail(u)}
            for u in usuarios
            if _puede_ver_el_mundo(u, mundo) and ve_el_nombre(current_user, u, aprobadores)
        ]
    return [_persona_json(u) for u in usuarios if _puede_ver_el_mundo(u, mundo)]


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
    _exigir_en_su_alcance(current_user, payload.desde, payload.hasta)
    existente = (await db.execute(
        select(CalendarioBarra.id).where(CalendarioBarra.id == payload.id)
    )).scalar_one_or_none()
    if existente is not None:
        # El id lo genera el front: si ya está, es un reintento del mismo alta.
        # `yaExistia` le dice al front que esta revisión NO es la suya.
        return {"id": payload.id, "rev": _rev_para(current_user, await _revision_actual(db)), "yaExistia": True}
    barra = CalendarioBarra(
        **payload.model_dump(),
        creado_por_id=current_user.id,
        actualizado_por_id=current_user.id,
    )
    db.add(barra)
    await db.flush()
    # Redexpres: nace con su tarea Lanzar y sus avisos (0077).
    controles = await controles_redexpres.agregar(db, barra, current_user.id, alcance.hoy_en_uruguay())
    rev = await _nueva_revision(db, payload.mundo)
    await db.commit()
    if controles:
        # Cargada con menos de 60 días: el aviso de Lanzar sale ya.
        await _avisar_sin_romper(db, payload.id)
    out = {"id": payload.id, "rev": _rev_para(current_user, rev)}
    if controles:
        # La pantalla tiene la acción, pero no las tareas que se le crearon
        # acá: que se traiga todo.
        out["recargar"] = True
    return out


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
    if cambio_la_fecha or cambio_el_fin:
        _exigir_en_su_alcance(current_user, cambios.get("desde", barra.desde), cambios.get("hasta", barra.hasta))
    nombre_anterior = barra.nombre
    for campo, valor in cambios.items():
        setattr(barra, campo, valor)
    barra.actualizado_por_id = current_user.id
    if barra.nombre != nombre_anterior:
        # Las tarjetas se llaman "<Acción> - <Tipo>": si a la acción se le
        # corrige el nombre, sus tarjetas lo siguen (las que conservan el
        # nombre automático; una renombrada a mano se respeta).
        for tarea in (await db.execute(
            select(CalendarioTarea).where(
                CalendarioTarea.barra_id == barra_id, CalendarioTarea.tipo.is_not(None),
            ).with_for_update()
        )).scalars():
            if tarea.titulo == tipos_de_tarea.nombre_de_tarjeta(nombre_anterior, tarea.tipo):
                tarea.titulo = tipos_de_tarea.nombre_de_tarjeta(barra.nombre, tarea.tipo)
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
    # Pasada a una fila que lleva Lanzar (de "BOMBAS" a "ESPECIAL -
    # CM", por ejemplo): se le suman (0077).
    controles = 0
    if "banda" in cambios:
        controles = await controles_redexpres.agregar(db, barra, current_user.id, alcance.hoy_en_uruguay())
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    if cambio_la_fecha or controles:
        # Un aviso que con la fecha nueva ya tendría que haber salido, sale ya.
        await _avisar_sin_romper(db, barra_id)
    out = {"id": barra_id, "rev": _rev_para(current_user, rev), "tareasMovidas": movidas}
    if controles:
        out["recargar"] = True
    return out


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
    # Lo que no se ve tampoco se borra: con un id viejo (un link, una respuesta
    # de Don Tino, Outlook) alguien con alcance de 1 mes podía borrar una
    # acción de dentro de tres. Se contesta como si no existiera, igual que al
    # editarla o copiarla ("No lo ve" tiene la ventana vacía: tampoco pasa).
    if not alcance.toca(barra.desde, barra.hasta, alcance.ventana_de(current_user)):
        raise HTTPException(status_code=404, detail=_YA_NO_EXISTE)
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
    # Con la acción se va su pedido de fotos (la base lo borra en cascada). El
    # "te pidieron una foto" que tienen los locales en la campanita ya no
    # llevaría a nada: se va también.
    locales = (await db.execute(
        select(ColocacionLocal.id)
        .join(ColocacionPedido, ColocacionPedido.id == ColocacionLocal.pedido_id)
        .where(ColocacionPedido.barra_id == barra_id)
    )).scalars().all()
    if locales:
        await db.execute(delete(Notificacion).where(
            Notificacion.origen_tipo.in_(ORIGENES_DEL_LOCAL),
            Notificacion.origen_ref.in_([f"{barra_id}:{i}" for i in locales]),
        ))
    await db.delete(barra)
    rev = await _nueva_revision(db, mundo)
    await db.commit()
    return {"id": barra_id, "borrada": True, "rev": _rev_para(current_user, rev)}


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
        return {"id": igual.id, "rev": _rev_para(current_user, await _revision_actual(db)), "yaExistia": True}
    db.add(CalendarioPieza(
        id=payload.id, barra_id=barra_id, area=payload.area, formato=payload.formato,
        estado=payload.estado, desde=payload.desde, hasta=payload.hasta, hora=payload.hora,
        orden=max((p.orden for p in piezas), default=-1) + 1,
    ))
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": payload.id, "rev": _rev_para(current_user, rev)}


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
    barra_id = pieza.barra_id
    await db.commit()
    if "desde" in campos:
        # Un aviso contado desde este envío (0084) se mueve con él: si con la
        # fecha nueva ya toca, sale ahora.
        await _avisar_sin_romper(db, barra_id)
    return {"id": pieza_id, "rev": _rev_para(current_user, rev)}


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
    return {"id": pieza_id, "borrada": True, "rev": _rev_para(current_user, rev)}


# ---------------------------------------------------------------------------
# Avisos
# ---------------------------------------------------------------------------

class AvisoNuevo(BaseModel):
    id: str = Field(..., pattern=_ID)
    diasAntes: int = Field(..., ge=1, le=365)
    destinatarios: list[int] = Field(..., min_length=1, max_length=200)
    # Contar los días desde que sale este envío y no desde que arranca la
    # acción (0084, 20/11/2026). Una pieza de envío de la misma acción.
    piezaId: str | None = Field(None, pattern=_ID)


_AREAS_DE_ENVIO = frozenset({"email", "whatsapp", "push"})


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
    if any(externos.es_externo(u) for u in usuarios):
        # Los avisos son del equipo: dicen qué arranca y cuándo, también de lo
        # que está fuera de la ventana de la agencia.
        raise HTTPException(
            status_code=422,
            detail="Los avisos son internos: una cuenta externa (agencia) no los recibe. Sacala de la lista.",
        )
    validos = {u.id for u in usuarios if _puede_ver_el_mundo(u, barra.mundo)}
    faltan = [uid for uid in pedidos if uid not in validos]
    if faltan:
        raise HTTPException(
            status_code=422,
            detail="Hay personas elegidas que no pueden abrir el calendario: no les llegaría el aviso",
        )

    if payload.piezaId is not None:
        pieza = await db.get(CalendarioPieza, payload.piezaId)
        if pieza is None or pieza.barra_id != barra_id:
            raise HTTPException(status_code=404, detail="Ese envío ya no está en la acción: lo sacaron.")
        if pieza.area not in _AREAS_DE_ENVIO:
            raise HTTPException(status_code=422, detail="Los avisos se cuentan desde un envío: un email, un WhatsApp o una push")

    existente = (await db.execute(
        select(CalendarioAviso.id).where(CalendarioAviso.id == payload.id)
    )).scalar_one_or_none()
    if existente is None:
        db.add(CalendarioAviso(
            id=payload.id, barra_id=barra_id, dias_antes=payload.diasAntes,
            destinatarios=pedidos, creado_por_id=current_user.id, pieza_id=payload.piezaId,
        ))
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    # Si la fecha del aviso ya pasó (10 días antes de algo que arranca en 5),
    # sale ahora y no en la próxima vuelta del loop.
    enviados = await _avisar_sin_romper(db, barra_id)
    return {"id": payload.id, "rev": _rev_para(current_user, rev), "enviadosAhora": enviados}


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
    return {"id": aviso_id, "borrado": True, "rev": _rev_para(current_user, rev)}


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
    # Un mes fuera de lo que la persona ve del calendario (0070) no existe para ella.
    alcance.exigir_calendario(current_user)
    meses = alcance.meses_de(alcance.ventana_de(current_user))
    if meses is not None and clave not in meses:
        raise HTTPException(status_code=404, detail="Ese mes queda fuera de lo que ves del calendario")
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
    return {"clave": clave, "avisados": len(destinatarios), "rev": _rev_para(current_user, rev)}


# ---------------------------------------------------------------------------
# Tareas
# ---------------------------------------------------------------------------
# Pedido de Ivan (12/11/2026): quien lidera abre una acción, le crea tareas y
# subtareas y se las asigna a cada persona, que se entera por la campanita.
#
# Crear, editar, asignar y borrar pide `calendario.tareas`. Mover el ESTADO de
# una tarea lo puede hacer además la persona que la tiene asignada, aunque no
# tenga ese permiso ni `calendario.edit`: es su tarea.
#
# Una PIEZA (0070: una tarea con tipo —Banners, Cenefas...— o que hace una
# agencia) la puede pedir además quien tiene `calendario.pedidos`. Ivan
# (16/11/2026): "todo el equipo (Lucía, Nao…) tiene que poder crear tareas
# para agencia". Repartir tareas comunes entre la gente de Tienda, editar y
# borrar tareas sigue siendo de quien lidera (`calendario.tareas`).
#
# Hasta el 17/11/2026 pedir piezas venía con `calendario.edit`. Ivan: "debería
# de ser un permiso específico el poder hacer peticiones de materiales". La
# acción la arma quien lidera; las tareas de la acción y los materiales de
# cada tarea los crea el equipo de analistas. Separado, se puede dar uno sin
# el otro. La 0071 se lo dio a todos los que tenían `calendario.edit`: nadie
# pierde lo que hacía. Editar, reasignar y borrar tareas sigue siendo de
# quien lidera (`calendario.tareas`).

PERMISO_PEDIDOS = "calendario.pedidos"

TIPO_TAREA = "calendario_tarea"


def _puede_gestionar_tareas(usuario: User) -> bool:
    # Con el freno de las cuentas externas (externos.puede_tener): una agencia
    # nunca arma ni reparte tareas, aunque el permiso apareciera en su lista.
    return externos.puede_tener(usuario, PERMISO_TAREAS)


def puede_pedir_piezas(usuario: User) -> bool:
    """Quién pide piezas y materiales: quien tiene `calendario.pedidos`, o
    quien lidera (`calendario.tareas`), que puede crear cualquier tarea. Una
    cuenta externa nunca pide (externos.puede_tener). Pura."""
    return _puede_gestionar_tareas(usuario) or externos.puede_tener(usuario, PERMISO_PEDIDOS)


def puede_crear_tarea(usuario: User, pieza: bool) -> bool:
    """Quién crea una tarea, común o pieza: quien lidera, y quien tiene
    `calendario.pedidos`. Ivan (17/11/2026): "el inicio debería ser crear
    tarea y punto... crear tarea y debajo de eso poder asignar los materiales
    de esa tarea creada"; la acción la arma quien lidera, y las tareas y sus
    materiales, el equipo de analistas. `pieza` queda por las llamadas de
    antes: hoy la regla es la misma para las dos. Pura."""
    return _puede_gestionar_tareas(usuario) or puede_pedir_piezas(usuario)


async def _cuentas_de_la_agencia(db: AsyncSession, empresa: str | None, mundo: str) -> list[User]:
    """Las cuentas activas de esa agencia que entran a este mundo. La empresa
    se compara sin tildes ni mayúsculas: una cuenta guardada con
    «Disenadores» es de Diseñadores (19/11/2026)."""
    clave = externos.clave_de_empresa(empresa)
    if not clave:
        return []
    usuarios = (await db.execute(
        select(User).where(
            User.es_externo.is_(True), User.is_active.is_(True), externos.empresa_en_sql(User.empresa) == clave,
        )
    )).scalars().all()
    return [u for u in usuarios if _puede_ver_el_mundo(u, mundo)]


async def _agencia_o_422(db: AsyncSession, empresa: str | None, mundo: str) -> str:
    """El nombre de la agencia si tiene alguna cuenta que entra a este mundo:
    si no, nadie vería la tarjeta. Los tres tableros (Publicis, Another
    Monday y Diseñadores, ver app/core/tableros.py) valen aunque todavía no
    tengan cuentas: la tarjeta espera en su tablero.

    El nombre vuelve como ya está escrito (app/services/agencias.py): el del
    tablero, o el de la primera cuenta de esa agencia. Así se ve igual en
    todos lados, aunque se haya pedido «disenadores»."""
    limpia = externos.limpiar_empresa(empresa)
    if not limpia:
        raise HTTPException(status_code=422, detail="Elegí para qué agencia es")
    cuentas = await _cuentas_de_la_agencia(db, limpia, mundo)
    if not cuentas and not tablero_de(limpia):
        raise HTTPException(
            status_code=422,
            detail=f"«{limpia}» no tiene ninguna cuenta que entre a {MUNDOS.get(mundo, mundo)}: no vería la tarjeta",
        )
    return await agencias.como_ya_esta(db, limpia) or limpia


async def _nacer_tarjetas(
    db: AsyncSession, usuario: User, barra: CalendarioBarra, tareas: list[CalendarioTarea],
) -> int:
    """Lo que pasa cuando nace una pieza (0070: una tarea con tipo, o para una
    agencia): le nacen sus entregas por defecto (una fase "Entrega", la
    aprueba quien la creó), o sea su tarjeta en el tablero, y a quien la hace
    (la agencia entera, o la persona asignada) le llega UN aviso por persona
    con todas sus tarjetas nuevas: "Iván te pidió: Ciberlunes - Banners
    (Header, Slider)". Devuelve a cuántas personas se avisó.

    Las tareas tienen que estar ya en la sesión; se manda todo junto (flush)
    porque las entregas apuntan a la tarea."""
    piezas = [t for t in tareas if es_pieza(t)]
    if not piezas:
        return 0
    await db.flush()
    por_persona: dict[int, list[CalendarioTarea]] = {}
    for t in piezas:
        if await db.get(CalendarioEntrega, t.id) is None:
            # Una pieza de Tienda que alguien se pide a sí mismo no puede
            # tenerlo de único aprobador (nadie decide sobre lo que subió):
            # nace sin cadena y la aprueba quien tiene calendario.tareas.
            # Vale igual para lo que nace de una plantilla o de una copia.
            se_la_hace_solo = t.para == "tienda" and t.asignado_a_id == usuario.id
            await reglas_entregas.crear_entregas_por_defecto(
                db, t, usuario.id, aprobadores=[] if se_la_hace_solo else None,
            )
        for uid in await reglas_entregas.destinatarios_de_la_tarjeta(db, t, barra.mundo):
            if uid != usuario.id:
                por_persona.setdefault(uid, []).append(t)
    avisados = 0
    for uid, suyas in por_persona.items():
        if await reglas_entregas.avisar(
            db, uid,
            reglas_entregas.mensaje_de_tarjetas_nuevas(
                usuario.full_name, [(t.titulo, list(t.opciones or []), t.vence) for t in suyas],
            ),
            reglas_entregas.referencia(barra.id, suyas[0].id, "tarjeta", "nueva"),
        ):
            avisados += 1
    return avisados


def es_pieza(tarea) -> bool:
    """Si una tarea es una pieza con su tarjeta en el tablero: tiene tipo
    (Banners, Cenefas...) o la hace una agencia (de la plataforma o de
    afuera). Las demás son tareas comunes del equipo. Pura."""
    return bool(getattr(tarea, "tipo", None)) or getattr(tarea, "para", "tienda") in ("agencia", "fuera")


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


def mensaje_de_tareas_copiadas(quien: str, titulos: list[str], accion: str, vence: date | None) -> str:
    """El aviso de quien recibe tareas al copiarse una acción: UNO por persona
    aunque le toquen varias, que veinte avisos juntos de la misma acción son
    ruido. Con una sola tarea es el aviso de siempre. `vence` es la primera
    que vence."""
    if len(titulos) == 1:
        return mensaje_de_asignacion(quien, titulos[0], accion, vence)
    primeras = titulos[:3]
    resto = len(titulos) - len(primeras)
    lista = (
        f"{', '.join(primeras)} y {resto} más" if resto
        else f"{', '.join(primeras[:-1])} y {primeras[-1]}"
    )
    cuando = f" La primera vence el {vence.strftime('%d/%m')}." if vence else ""
    return f"{quien} te asignó {len(titulos)} tareas en {accion or 'una acción'}: {lista}.{cuando}"


def mensaje_de_responsable(quien: str, titulo: str, accion: str, agencia: str | None, vence: date | None) -> str:
    """El aviso a quien queda de responsable de Tienda de una tarea que hace
    una agencia (0090). No la hace: la sigue."""
    hace = f" (la hace {agencia})" if agencia else ""
    cuando = f" Vence el {vence.strftime('%d/%m')}." if vence else ""
    return f"{quien} te dejó de responsable de «{titulo}» en {accion or 'una acción'}{hace}.{cuando}"


def repartir_orden(ordenes: dict[str, int], ids: list[str]) -> dict[str, int]:
    """El `orden` nuevo de unas tareas hermanas que se arrastraron (Ivan,
    20/11/2026: "ordenar las tareas arrastrando"). Reusan los mismos lugares
    que ya tenían, en el orden nuevo: así no se mueve ninguna otra tarea de la
    acción. Si había lugares repetidos (tareas que nacieron juntas), pasan a
    ser seguidos desde el menor. Pura."""
    lugares = sorted(ordenes[i] for i in ids)
    if len(set(lugares)) < len(lugares):
        lugares = list(range(lugares[0], lugares[0] + len(lugares)))
    return dict(zip(ids, lugares))


# --- Vencimientos anclados a la acción (0065) ---------------------------------
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


async def _responsable_o_422(db: AsyncSession, user_id: int, mundo: str) -> User:
    """El responsable de Tienda de una tarea que hace una agencia (0090):
    alguien del equipo que abre este mundo. Una cuenta de una agencia no."""
    usuario = await _asignable_o_422(db, user_id, mundo)
    if externos.es_externo(usuario):
        raise HTTPException(status_code=422, detail="El responsable es alguien de Tienda Inglesa, no de una agencia")
    return usuario


class TareaNueva(BaseModel):
    id: str = Field(..., pattern=_ID)
    # Desde la 0090 no hay tareas adentro de otra: si viene, se rechaza
    # (_UN_SOLO_NIVEL). Queda para decirle eso a una pantalla vieja.
    parentId: str | None = Field(None, pattern=_ID)
    # Con `tipo` y sin título, el título lo arma el servidor ("<Acción> -
    # <Tipo>"). Con título, va ese: el nombre se puede cambiar al crearla (0090).
    titulo: str = Field("", max_length=500)
    descripcion: str | None = Field(None, max_length=5000)
    asignadoA: int | None = None
    vence: Fecha | None = None
    # Quién la hace (0070): 'tienda', 'agencia' (de la plataforma: cuál, en
    # `agencia`) o 'fuera' (una agencia que no usa la plataforma: su nombre en
    # `agencia`, y `asignadoA` es quien del equipo carga sus entregas).
    para: ParaQuien = "tienda"
    agencia: str | None = Field(None, max_length=120)
    # Quién la lleva por Tienda si la hace una agencia (0090): alguien del
    # equipo. En una tarea de Tienda no va (la lleva quien la tiene asignada).
    responsable: int | None = None
    # El tipo de tarea (app/services/tipos_de_tarea.py) y lo que se tildó.
    # Con tipo, es una pieza: le nace su tarjeta.
    tipo: str | None = Field(None, max_length=20)
    opciones: list[str] | None = Field(None, max_length=60)
    # Los datos de más del tipo (el CTA, los bloques del mailing).
    detalles: dict | None = None
    # El vencimiento contado desde la acción ("3 días antes del inicio"), en
    # vez de una fecha fija: se mueve si la acción se mueve (como el de una
    # plantilla). Si viene, manda sobre `vence`.
    ancla: Ancla | None = None
    anclaDias: int | None = Field(None, ge=-_DIAS_DE_ANCLA, le=_DIAS_DE_ANCLA)

    @field_validator("titulo")
    @classmethod
    def _sin_espacios(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _titulo_o_tipo(self):
        if self.tipo is not None:
            self.opciones = tipos_de_tarea.opciones_validas(self.tipo, self.opciones)
            self.detalles = tipos_de_tarea.detalles_validos(self.tipo, self.detalles, self.opciones) or None
        elif not self.titulo:
            raise ValueError("La tarea necesita un título")
        else:
            self.opciones = None
            self.detalles = None
        return self


class TareaCambios(BaseModel):
    """Solo viaja lo que cambió. `asignadoA`, `responsable`, `vence` y
    `descripcion` pueden venir en null a propósito: es sacarle la persona, el
    responsable, la fecha o el detalle."""
    titulo: str | None = Field(None, min_length=1, max_length=500)
    descripcion: str | None = Field(None, max_length=5000)
    estado: EstadoTarea | None = None
    asignadoA: int | None = None
    responsable: int | None = None
    vence: Fecha | None = None


class OrdenDeTareas(BaseModel):
    """Las tareas de una acción, en el orden nuevo."""
    ids: list[str] = Field(..., min_length=1, max_length=500)


@router.get("/tipos-de-tarea")
async def listar_tipos_de_tarea(
    current_user: User = Depends(require_permission("calendario.view")),
):
    """El catálogo de tipos de tarea con sus opciones. Está en UN solo lugar
    (app/services/tipos_de_tarea.py): la pantalla lo pide acá y no guarda una
    copia, así cambiar una medida de banner es cambiarla allá."""
    return tipos_de_tarea.para_la_pantalla()


@router.get("/tableros")
async def listar_tableros(
    mundo: str = MUNDO_POR_DEFECTO,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Los tres tableros a los que va una pieza (17/11/2026), con cuántas
    cuentas tiene cada uno en este mundo (cero = todavía no entra nadie: la
    pieza espera ahí igual). A una cuenta externa, solo el suyo."""
    exigir_mundo(current_user, mundo)
    out = []
    for nombre in TABLEROS:
        if externos.es_externo(current_user) and not externos.misma_empresa(nombre, current_user.empresa):
            continue
        out.append({"nombre": nombre, "cuentas": len(await _cuentas_de_la_agencia(db, nombre, mundo))})
    return out


@router.post("/barras/{barra_id}/tareas", status_code=201)
async def crear_tarea(
    barra_id: str,
    payload: TareaNueva,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Una tarea de una acción: un pedido (0090, "una tarea = un pedido"),
    siempre en el primer nivel. Si es una pieza (0070: tiene tipo, o la hace
    una agencia), le nace su tarjeta en el tablero, con el nombre "<Acción> -
    <Tipo>" (o el que se escribió), sus entregas por defecto y el aviso a
    quien la hace (ver `_nacer_tarjetas`); si la hace una agencia, puede
    llevar su responsable de Tienda, que también se entera."""
    pieza = es_pieza(payload)
    if not puede_crear_tarea(current_user, pieza):
        raise HTTPException(status_code=403, detail=f"Permiso requerido: {PERMISO_PEDIDOS}")
    if payload.parentId is not None:
        raise HTTPException(status_code=422, detail=_UN_SOLO_NIVEL)
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
        return {"id": payload.id, "rev": _rev_para(current_user, await _revision_actual(db)), "yaExistia": True}
    # El id lo genera el front; si ya lo usa una tarea de OTRA acción, la
    # clave primaria lo frenaría con un 500 sin explicación.
    if await db.get(CalendarioTarea, payload.id) is not None:
        raise HTTPException(status_code=409, detail="Esa tarea ya existe en otra acción")
    if payload.tipo and not tipos_de_tarea.vale_en(payload.tipo, barra.mundo):
        # Imprenta, Video monitores... son de Redexpres (18/11/2026).
        raise HTTPException(status_code=422, detail="Ese tipo de pieza no se pide en este mundo")
    asignado = await _asignable_o_422(db, payload.asignadoA, barra.mundo) if payload.asignadoA is not None else None
    para, agencia = await _para_quien(db, payload.para, payload.agencia, asignado, barra.mundo)
    if not es_pieza(SimpleNamespace(tipo=payload.tipo, para=para)) and not puede_crear_tarea(current_user, pieza=False):
        # Una tarea común: quien lidera, o quien crea tareas y pide sus
        # materiales (calendario.pedidos, 17/11/2026).
        raise HTTPException(status_code=403, detail=f"Permiso requerido: {PERMISO_PEDIDOS}")
    # El responsable de Tienda, solo si la hace una agencia: en una de Tienda
    # la lleva quien la tiene asignada.
    responsable = None
    if payload.responsable is not None and para in ("agencia", "fuera"):
        responsable = await _responsable_o_422(db, payload.responsable, barra.mundo)

    if payload.ancla is not None:
        dias = payload.anclaDias or 0
        vence = vence_anclado(payload.ancla, dias, barra.desde, barra.hasta)
        try:
            _fecha_razonable(vence)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        ancla, ancla_dias = payload.ancla, dias
    else:
        vence, ancla, ancla_dias = payload.vence, None, None

    # Con tipo y sin nombre escrito, el nombre se arma solo: "Ciberlunes -
    # Banners" (así se encuentra escribiendo el nombre de la acción, un guión
    # y lo que se busca). Si se escribió otro al crearla, va ese (0090).
    titulo = payload.titulo or (tipos_de_tarea.nombre_de_tarjeta(barra.nombre, payload.tipo) if payload.tipo else "")
    tarea = CalendarioTarea(
        id=payload.id, barra_id=barra_id, parent_id=None, titulo=titulo,
        descripcion=(payload.descripcion or "").strip() or None,
        asignado_a_id=payload.asignadoA, vence=vence, ancla=ancla, ancla_dias=ancla_dias,
        para=para, agencia=agencia, responsable_id=responsable.id if responsable else None,
        tipo=payload.tipo, opciones=payload.opciones, detalles=payload.detalles,
        orden=max((t.orden for t in existentes), default=-1) + 1,
        creado_por_id=current_user.id,
    )
    db.add(tarea)
    avisados = 0
    entrega = None
    if es_pieza(tarea):
        # A quien la hace le llega "Iván te pidió: …" (lleva al tablero), no
        # el aviso de tarea asignada: uno solo, no dos por lo mismo.
        avisados = await _nacer_tarjetas(db, current_user, barra, [tarea])
        await db.flush()
        entrega = (await resumenes_de_entregas(db, [tarea.id])).get(tarea.id)
        if responsable is not None and responsable.id != current_user.id:
            _avisar(db, responsable.id, mensaje_de_responsable(
                current_user.full_name, titulo, barra.nombre, agencia, vence,
            ), barra_id, payload.id)
            avisados += 1
    elif payload.asignadoA is not None and payload.asignadoA != current_user.id:
        _avisar(db, payload.asignadoA, mensaje_de_asignacion(
            current_user.full_name, titulo, barra.nombre, vence,
        ), barra_id, payload.id)
        avisados = 1
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {
        "id": payload.id, "rev": _rev_para(current_user, rev), "avisados": avisados,
        "titulo": titulo, "para": para, "agencia": agencia, "vence": vence.isoformat() if vence else None,
        "responsable": tarea.responsable_id, "entrega": entrega,
    }


@router.put("/barras/{barra_id}/tareas/orden")
async def ordenar_tareas(
    barra_id: str,
    payload: OrdenDeTareas,
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Ordenar las tareas arrastrándolas (Ivan, 20/11/2026). Llegan las
    hermanas en el orden nuevo y cada una toma uno de los lugares que ya
    tenían (`repartir_orden`). Si mientras tanto alguien agregó otra, esa
    queda donde estaba. Lo puede hacer quien gestiona las tareas."""
    if not _puede_gestionar_tareas(current_user):
        raise HTTPException(status_code=403, detail="Solo quien gestiona las tareas puede ordenarlas")
    if len(set(payload.ids)) != len(payload.ids):
        raise HTTPException(status_code=422, detail="Una tarea vino dos veces")
    barra = await _barra_o_404(db, barra_id, current_user, bloquear=True)
    tareas = {t.id: t for t in (await db.execute(
        select(CalendarioTarea).where(CalendarioTarea.barra_id == barra_id)
    )).scalars()}
    if any(i not in tareas for i in payload.ids):
        raise HTTPException(status_code=404, detail="Una de esas tareas ya no existe: la borró otra persona.")
    if len({tareas[i].parent_id for i in payload.ids}) > 1:
        raise HTTPException(status_code=422, detail="Se ordenan las tareas de un mismo nivel")
    for tarea_id, orden in repartir_orden({i: tareas[i].orden for i in payload.ids}, payload.ids).items():
        tareas[tarea_id].orden = orden
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"rev": _rev_para(current_user, rev)}


_QUIEN_CARGA_LO_DE_AFUERA = "Quien carga lo de una agencia de afuera es alguien del equipo"


def _no_es_de_tienda(persona: User) -> str:
    """Por qué no se puede: eligieron a alguien de una agencia (una cuenta
    externa) para llevar una tarea de Tienda Inglesa. Publicis, Another
    Monday y Diseñadores son agencias externas: a ellas se les pide con una
    pieza, eligiendo su tablero (19/11/2026)."""
    nombre = (persona.full_name or "").strip() or "Esa persona"
    empresa = externos.limpiar_empresa(persona.empresa) or "una agencia"
    return (
        f"{nombre} es de {empresa}, una agencia externa: quien se encarga de una tarea por Tienda Inglesa "
        "tiene que ser alguien de Tienda. Para pedirle algo a la agencia, agregá una pieza y elegí su tablero."
    )


async def _para_quien(
    db: AsyncSession, para: str, agencia: str | None, asignado: User | None, mundo: str,
) -> tuple[str, str | None]:
    """Quién la hace: ('tienda', None), ('agencia', empresa) o ('fuera', nombre).

    - Una tarea de Tienda la lleva alguien de Tienda: una cuenta externa como
      responsable se rechaza, y la tarea no cambia (19/11/2026: elegir a
      «Fer (Diseñadores)» en «Responsable de Tienda Inglesa» convertía la
      tarea interna en una pieza de la agencia). A la agencia se le pide con
      una pieza (`para` = 'agencia').
    - Para una agencia de la plataforma, la persona asignada, si hay, tiene
      que ser de esa agencia: la tarjeta es de ella.
    - Una agencia de afuera no entra a la plataforma: hace falta alguien del
      equipo asignado, que carga sus entregas en su nombre."""
    if asignado is not None and externos.es_externo(asignado):
        if para == "tienda":
            raise HTTPException(status_code=422, detail=_no_es_de_tienda(asignado))
        if para == "agencia" and agencia and not externos.misma_empresa(agencia, asignado.empresa):
            raise HTTPException(status_code=422, detail="Esa persona es de otra agencia")
        if para == "fuera":
            raise HTTPException(status_code=422, detail=_QUIEN_CARGA_LO_DE_AFUERA)
        return "agencia", await agencias.como_ya_esta(db, asignado.empresa)
    if para == "agencia":
        if asignado is not None:
            raise HTTPException(
                status_code=422,
                detail="Una tarea para la agencia la entrega la agencia: elegí a alguien de ella o dejala sin asignar",
            )
        return "agencia", await _agencia_o_422(db, agencia, mundo)
    if para == "fuera":
        nombre = externos.limpiar_empresa(agencia)
        if not nombre:
            raise HTTPException(status_code=422, detail="Escribí el nombre de la agencia de afuera")
        if asignado is None:
            raise HTTPException(
                status_code=422,
                detail="Elegí quién del equipo carga lo que manda esa agencia (no usa la plataforma)",
            )
        return "fuera", nombre
    return "tienda", None


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
    campos = payload.model_fields_set
    solo_estado = campos <= {"estado"}
    es_suya = tarea.asignado_a_id == current_user.id
    if solo_estado and es_suya and not externos.es_externo(current_user):
        # Alguien del equipo tilda SU tarea aunque la acción quede fuera de lo
        # que ve del calendario: la tiene en Mis tareas (ver mis_tareas) y
        # tiene que poder avanzarla. Se mira el mundo, no el alcance.
        barra = await db.get(CalendarioBarra, tarea.barra_id)
        if barra is None:
            raise HTTPException(status_code=404, detail=_YA_NO_EXISTE)
        exigir_mundo(current_user, barra.mundo)
    else:
        barra = await _barra_o_404(db, tarea.barra_id, current_user)

    if not _puede_gestionar_tareas(current_user) and not (solo_estado and es_suya):
        raise HTTPException(
            status_code=403,
            detail="Solo podés cambiar el estado de las tareas que tenés asignadas",
        )
    # Una tarea con entregas por fases (0067) se termina cuando se aprueba su
    # última fase, no con un tilde: si no, quien entrega se la daría por
    # aprobada. Quien lidera sí puede moverla a mano (cerrar una que se
    # abandonó, por ejemplo).
    if (
        "estado" in campos and payload.estado is not None and payload.estado != tarea.estado
        and not _puede_gestionar_tareas(current_user)
        and await db.get(CalendarioEntrega, tarea.id) is not None
    ):
        raise HTTPException(
            status_code=403,
            detail="Esta tarea lleva entregas: queda hecha sola cuando se aprueba la última fase",
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
        nuevo = await _asignable_o_422(db, payload.asignadoA, barra.mundo) if payload.asignadoA is not None else None
        era_de_la_agencia = tarea.para == "agencia"
        if nuevo is not None and externos.es_externo(nuevo) and not era_de_la_agencia:
            # Una tarea de Tienda (o lo de una agencia de afuera, que carga
            # alguien del equipo) no pasa a ser de la agencia por elegir a una
            # de sus cuentas: se rechaza y queda como estaba (19/11/2026).
            raise HTTPException(
                status_code=422,
                detail=_QUIEN_CARGA_LO_DE_AFUERA if tarea.para == "fuera" else _no_es_de_tienda(nuevo),
            )
        if nuevo is not None and externos.es_externo(nuevo):
            # Una pieza de una agencia, a alguien de una agencia: es de su
            # agencia (0070), con el nombre como ya está escrito.
            tarea.para, tarea.agencia = "agencia", await agencias.como_ya_esta(db, nuevo.empresa)
        elif nuevo is not None and era_de_la_agencia:
            # A alguien de Tienda: deja de ser de la agencia (sus entregas
            # quedan, las entrega esta persona). La lleva quien la hace: ya no
            # hay responsable aparte (0090).
            tarea.para, tarea.agencia = "tienda", None
            tarea.responsable_id = None
        tarea.asignado_a_id = payload.asignadoA
        if tarea.para == "agencia" and (not era_de_la_agencia or nuevo is not None):
            # Le nace la tarjeta si no la tenía, y el aviso va como "tarjeta
            # nueva" (al tablero), no como tarea asignada: uno solo.
            avisados += await _nacer_tarjetas(db, current_user, barra, [tarea])
        elif nuevo is not None and nuevo.id != current_user.id:
            if await db.get(CalendarioEntrega, tarea.id) is not None:
                # Una pieza (con su tarjeta) que pasa a otra persona del
                # equipo: el aviso es el de la tarjeta («te pidió», lleva al
                # tablero), como cuando nace, y no el de una tarea común
                # (revisión del 16/11/2026). Uno por persona y tarjeta.
                if await reglas_entregas.avisar(
                    db, nuevo.id,
                    reglas_entregas.mensaje_de_tarjeta_nueva(
                        current_user.full_name, tarea.titulo, list(tarea.opciones or []), tarea.vence,
                    ),
                    reglas_entregas.referencia(barra.id, tarea.id, "tarjeta", "nueva"),
                ):
                    avisados += 1
            else:
                _avisar(db, nuevo.id, mensaje_de_asignacion(
                    current_user.full_name, tarea.titulo, barra.nombre, tarea.vence,
                ), barra.id, tarea.id)
                avisados += 1
    if "responsable" in campos and payload.responsable != tarea.responsable_id:
        # El responsable de Tienda (0090): solo en lo que hace una agencia.
        if payload.responsable is not None and tarea.para not in ("agencia", "fuera"):
            raise HTTPException(
                status_code=422,
                detail="Solo una tarea que hace una agencia lleva responsable de Tienda: esta la lleva quien la tiene asignada",
            )
        nuevo_resp = await _responsable_o_422(db, payload.responsable, barra.mundo) if payload.responsable is not None else None
        tarea.responsable_id = payload.responsable
        if nuevo_resp is not None and nuevo_resp.id != current_user.id:
            _avisar(db, nuevo_resp.id, mensaje_de_responsable(
                current_user.full_name, tarea.titulo, barra.nombre, tarea.agencia, tarea.vence,
            ), barra.id, tarea.id)
            avisados += 1
    if "estado" in campos and payload.estado is not None and payload.estado != tarea.estado:
        era = tarea.estado
        if tarea.estado == "hecha" and "vence" not in campos:
            # Hecha no se movía con la acción; si se reabre, vuelve a su fecha
            # contada desde la acción como está hoy (ver vence_al_reabrir).
            tarea.vence = vence_al_reabrir(tarea, barra.desde, barra.hasta)
        tarea.estado = payload.estado
        # Una pieza sin terminar que quien lidera cierra a mano (la pieza se
        # canceló, o se hizo fuera de la plataforma): su tarjeta pasa a
        # Archivado. Antes quedaba para siempre en Ingresado o En proceso, y
        # la agencia la seguía viendo para entregar. Si se reabre, la tarjeta
        # vuelve sola a su columna (revisión del 16/11/2026). La entrega se
        # bloquea después de la tarea, como en todos lados.
        entrega = (await db.execute(
            select(CalendarioEntrega).where(CalendarioEntrega.tarea_id == tarea.id).with_for_update()
        )).scalar_one_or_none()
        if entrega is not None and entrega.momento != "aprobada":
            ahora = datetime.now(timezone.utc)
            if payload.estado == "hecha" and entrega.archivada_at is None:
                entrega.archivada_at = ahora
                entrega.archivada_por_id = current_user.id
            elif era == "hecha" and entrega.archivada_at is not None:
                entrega.archivada_at = None
                entrega.archivada_por_id = None
                entrega.desarchivada_at = ahora
        # A quien la creó le interesa saber que se terminó, salvo que la haya
        # terminado esa misma persona.
        if payload.estado == "hecha" and tarea.creado_por_id and tarea.creado_por_id != current_user.id:
            _avisar(db, tarea.creado_por_id, mensaje_de_tarea_hecha(
                current_user.full_name, tarea.titulo, barra.nombre,
            ), barra.id, tarea.id)
            avisados += 1
    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {"id": tarea_id, "rev": _rev_para(current_user, rev), "avisados": avisados}


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
    return {"id": tarea_id, "borrada": True, "rev": _rev_para(current_user, rev)}


DIAS_DE_HECHAS_EN_MIS_TAREAS = 30


@router.get("/mis-tareas")
async def mis_tareas(
    current_user: User = Depends(require_permission("calendario.view")),
    db: AsyncSession = Depends(get_db),
):
    """Lo que la persona tiene asignado, en todos los mundos que puede abrir,
    con la acción de cada tarea. Es lo que muestra el inicio. También lo que
    hace una agencia y ella lleva por Tienda (`responsable_id`, 0090): antes
    lo tenía como la tarea de afuera de esas piezas.

    Las abiertas, todas; las hechas, solo las de los últimos
    DIAS_DE_HECHAS_EN_MIS_TAREAS días. Antes venía todo lo de siempre: con el
    uso se iba a cientos de tareas viejas (medido: 269 KB con 668) que nadie
    mira y que se bajaban cada vez que se abría la pantalla.

    A alguien del EQUIPO sus tareas abiertas le llegan siempre, vea lo que vea
    del calendario: si a un diseñador se le deja el calendario en "1 mes" o
    "No lo ve" y le asignan algo de una acción lejana, tiene que enterarse (si
    no, vence sin que la vea nunca). De esa acción ve el nombre y las fechas,
    que es lo que ya decía el aviso. Las hechas, solo las de su alcance.

    A una cuenta EXTERNA no: su trabajo son las tarjetas del tablero
    (/calendario/entregas), que ve siempre; esta lista es calendario, así que
    sin calendario recibe 403 y con uno limitado, solo lo de su alcance."""
    externo = externos.es_externo(current_user)
    if externo:
        alcance.exigir_calendario(current_user)
    mundos = mundos_de(current_user)
    if not mundos:
        return []
    desde = datetime.now(timezone.utc) - timedelta(days=DIAS_DE_HECHAS_EN_MIS_TAREAS)
    consulta = (
        select(CalendarioTarea, CalendarioBarra)
        .join(CalendarioBarra, CalendarioBarra.id == CalendarioTarea.barra_id)
        .where(
            or_(CalendarioTarea.asignado_a_id == current_user.id, CalendarioTarea.responsable_id == current_user.id),
            CalendarioBarra.mundo.in_(mundos),
            or_(
                CalendarioTarea.estado != "hecha",
                # Se tildó (o se tocó por última vez) hace menos de eso.
                func.coalesce(CalendarioTarea.updated_at, CalendarioTarea.created_at) >= desde,
            ),
        )
    )
    ventana = alcance.ventana_de(current_user)
    # Lo de su alcance y, aunque quede afuera, lo que le llega siempre (sus
    # abiertas, si es del equipo): la misma regla que usa Don Tino.
    consulta = consulta.where(or_(
        alcance.condicion(CalendarioBarra, ventana), alcance.condicion_le_llega_siempre(CalendarioTarea, current_user),
    ))
    filas = (await db.execute(
        consulta.order_by(CalendarioTarea.vence.asc().nulls_last(), CalendarioBarra.desde, CalendarioTarea.id)
    )).all()
    entregas = await resumenes_de_entregas(db, [t.id for t, _ in filas]) if filas else {}
    propias = {t.id for t, _ in filas}
    return [
        {
            **_tarea_json(t, entregas.get(t.id)),
            # Como en /datos: a un externo no le viaja el id de una tarea madre
            # que no es suya.
            **({"parentId": None} if externo and t.parent_id not in propias else {}),
            "accion": {
                **({} if alcance.toca(b.desde, b.hasta, ventana) else {"fueraDeAlcance": True}),
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
    campanita para abrir su ficha aunque se esté mirando otro mundo. Para una
    cuenta externa, una acción fuera de su ventana da 404 (`_barra_o_404`)."""
    barra = await _barra_o_404(db, barra_id, current_user)
    return {"id": barra.id, "mundo": barra.mundo, "desde": barra.desde.isoformat()}


# ---------------------------------------------------------------------------
# Plantillas de tareas (0065)
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

_TAREAS_POR_PLANTILLA = 60


class TareaDePlantilla(BaseModel):
    """Una tarea de la plantilla. Van todas en un solo nivel, como las de una
    acción (0090): `parentId` queda solo para rechazar una pantalla vieja."""
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
    # Para quién es (0070): si es para la agencia, al aplicar la plantilla le
    # nace sola su tarjeta.
    para: ParaQuien = "tienda"
    agencia: str | None = Field(None, max_length=120)
    # Quién la lleva por Tienda si la hace una agencia (0090).
    responsable: int | None = None
    # El tipo de tarea (Banners, Cenefas...), lo tildado y los datos de más:
    # con tipo, la tarea nace como pieza, con su tarjeta y el nombre
    # "<Acción> - <Tipo>" de la acción donde se aplica.
    tipo: str | None = Field(None, max_length=20)
    opciones: list[str] | None = Field(None, max_length=60)
    detalles: dict | None = None

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
        if self.para in ("agencia", "fuera"):
            self.agencia = externos.limpiar_empresa(self.agencia)
            if not self.agencia:
                raise ValueError(f"Elegí qué agencia hace «{self.titulo}»")
        else:
            self.agencia = None
            self.responsable = None
        if self.para == "fuera" and self.asignadoA is None:
            raise ValueError(f"«{self.titulo}» la hace una agencia de afuera: elegí quién del equipo carga sus entregas")
        if self.tipo is not None:
            self.opciones = tipos_de_tarea.opciones_validas(self.tipo, self.opciones)
            self.detalles = tipos_de_tarea.detalles_validos(self.tipo, self.detalles, self.opciones) or None
        else:
            self.opciones = None
            self.detalles = None
        return self


def revisar_estructura(tareas: list[TareaDePlantilla]) -> None:
    """Que la plantilla se pueda aplicar tal cual: ids sin repetir y todas en
    el primer nivel (0090: ya no hay subtareas). Pura; un ValueError trae el
    mensaje para la persona."""
    ids = [t.id for t in tareas]
    if len(set(ids)) != len(ids):
        raise ValueError("Hay dos tareas con el mismo id en la plantilla")
    if any(t.parentId is not None for t in tareas):
        raise ValueError("En una plantilla las tareas van todas en el primer nivel: ya no hay subtareas. Recargá la página.")


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


def tareas_de_plantilla(
    tareas: list[dict], ids: dict[str, str], desde: date, hasta: date, accion: str = "",
) -> list[dict]:
    """Las tareas que crea una plantilla en una acción que va de `desde` a
    `hasta`, con el vencimiento calculado y anclado, en el orden de la
    plantilla y todas en el primer nivel (0090: una plantilla guardada antes
    se aplanó en esa migración; si igual trae `parentId`, no se usa). Pura.

    Si `ids` no trae exactamente las tareas de la plantilla, lo que vio el
    front ya no es lo guardado: PlantillaCambio, y que vuelva a mirar."""
    if set(ids) != {t["id"] for t in tareas}:
        raise PlantillaCambio("La plantilla cambió")
    out = []
    for t in tareas:
        ancla = t.get("ancla") or None
        dias = int(t.get("dias") or 0)
        de_agencia = t.get("para") in ("agencia", "fuera") and bool(t.get("agencia"))
        out.append({
            "id": ids[t["id"]],
            "parent_id": None,
            "titulo": t["titulo"],
            "descripcion": t.get("descripcion") or None,
            "asignado_a_id": t.get("asignadoA"),
            "vence": vence_anclado(ancla, dias, desde, hasta) if ancla else None,
            "ancla": ancla,
            "ancla_dias": dias if ancla else None,
            # Una plantilla guardada antes de la 0070 no dice quién la hace: Tienda.
            "para": t["para"] if de_agencia else "tienda",
            "agencia": t.get("agencia") if de_agencia else None,
            "responsable_id": t.get("responsable") if de_agencia else None,
            "tipo": t.get("tipo") or None,
            "opciones": list(t.get("opciones") or []) if t.get("tipo") else None,
            "detalles": dict(t.get("detalles") or {}) or None if t.get("tipo") else None,
        })
        if t.get("tipo"):
            # Una pieza se llama como la acción donde se aplica: "Ciberlunes - Banners".
            out[-1]["titulo"] = tipos_de_tarea.nombre_de_tarjeta(accion, t["tipo"])
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
    alcance.exigir_calendario(current_user)
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
    # Cada agencia nombrada tiene que tener quien vea sus tarjetas en este
    # mundo (0070), y se guarda con el nombre como ya está escrito
    # (19/11/2026: «disenadores» es Diseñadores); la persona fija de una
    # tarea para la agencia tiene que ser de ella.
    como_estan = {
        agencia: await _agencia_o_422(db, agencia, payload.mundo)
        for agencia in sorted({t.agencia for t in payload.tareas if t.para == "agencia" and t.agencia})
    }
    for t in payload.tareas:
        if t.para == "agencia" and t.agencia in como_estan:
            t.agencia = como_estan[t.agencia]
    con_persona = [t for t in payload.tareas if t.asignadoA is not None]
    if con_persona:
        personas = {u.id: u for u in (await db.execute(
            select(User).where(User.id.in_({t.asignadoA for t in con_persona}))
        )).scalars()}
        for t in con_persona:
            u = personas.get(t.asignadoA)
            if t.para == "agencia" and (u is None or not externos.es_externo(u)
                                         or not externos.misma_empresa(u.empresa, t.agencia)):
                raise HTTPException(
                    status_code=422,
                    detail=f"«{t.titulo}» es para {t.agencia}: la persona fija tiene que ser de esa agencia, o ninguna",
                )
            if t.para == "tienda" and u is not None and externos.es_externo(u):
                # Como al crearla a mano: una tarea de Tienda la lleva alguien
                # de Tienda, y no pasa a ser de la agencia (19/11/2026).
                raise HTTPException(status_code=422, detail=f"«{t.titulo}»: {_no_es_de_tienda(u)}")
            if t.para == "fuera" and u is not None and externos.es_externo(u):
                raise HTTPException(
                    status_code=422,
                    detail=f"«{t.titulo}» la hace una agencia de afuera: la carga alguien del equipo",
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
    return {"id": plantilla_id, "rev": _rev_para(current_user, rev)}


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
    alcance.exigir_calendario(current_user)
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
    return {"id": plantilla_id, "borrada": True, "rev": _rev_para(current_user, rev)}


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
            return {"id": barra_id, "rev": _rev_para(current_user, await _revision_actual(db)), "yaExistia": True}
        raise HTTPException(status_code=409, detail="Esa tarea ya existe en otra acción")
    try:
        plan = tareas_de_plantilla(list(plantilla.tareas or []), payload.ids, barra.desde, barra.hasta, barra.nombre)
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
    # Una tarea de Tienda (o lo de una agencia de afuera) con alguien de una
    # agencia fijo (una plantilla vieja, o alguien que después pasó a ser de
    # una agencia): no pasa a ser de la agencia, como tampoco al crearla a
    # mano (19/11/2026). Se crea sin asignar, y la respuesta lo cuenta.
    externas = set((await db.execute(
        select(User.id).where(User.id.in_(validos), User.es_externo.is_(True))
    )).scalars()) if validos else set()
    for t in plan:
        if t["asignado_a_id"] in externas and t["para"] != "agencia":
            t["asignado_a_id"] = None
            sin_asignar += 1
    # El responsable de Tienda de lo que hace una agencia (0090): alguien del
    # equipo que abre este mundo. Si ya no, la tarea se crea sin responsable.
    responsables = {t["responsable_id"] for t in plan if t["responsable_id"] is not None}
    del_equipo = set()
    if responsables:
        del_equipo = set((await db.execute(
            select(User.id).where(User.id.in_(list(await _asignables(db, responsables, barra.mundo))),
                                  User.es_externo.is_(False))
        )).scalars())
    for t in plan:
        if t["responsable_id"] is not None and t["responsable_id"] not in del_equipo:
            t["responsable_id"] = None
    # La agencia de cada pieza, como ya está escrita: una plantilla guardada
    # antes con «disenadores» crea las tarjetas de Diseñadores.
    como_estan: dict[str, str] = {}
    for t in plan:
        if t["para"] == "agencia" and t["agencia"]:
            if t["agencia"] not in como_estan:
                como_estan[t["agencia"]] = await agencias.como_ya_esta(db, t["agencia"]) or t["agencia"]
            t["agencia"] = como_estan[t["agencia"]]

    ultimo = (await db.execute(
        select(func.max(CalendarioTarea.orden)).where(CalendarioTarea.barra_id == barra_id)
    )).scalar_one_or_none()
    base = (ultimo if ultimo is not None else -1) + 1
    nuevas = [
        CalendarioTarea(**t, barra_id=barra_id, orden=base + i, plantilla_id=plantilla.id,
                        creado_por_id=current_user.id)
        for i, t in enumerate(plan)
    ]
    db.add_all(nuevas)
    await db.flush()

    # Las que son para la agencia (0070): les nace su tarjeta, y a la agencia
    # le llega UN aviso por persona con todas sus tarjetas nuevas. Una agencia
    # que dejó de tener cuentas en este mundo igual queda nombrada: la tarjeta
    # se ve en el tablero del equipo... pero esa agencia no la ve ni se
    # entera, así que la respuesta lo dice (`agenciasSinCuentas`) y la
    # pantalla lo avisa. Pasaba, por ejemplo, con una plantilla guardada con
    # el nombre viejo de una agencia que después se corrigió (revisión del
    # 16/11/2026; corregir el nombre ahora también corrige las plantillas).
    sin_cuentas = []
    for agencia in sorted({t["agencia"] for t in plan if t["para"] == "agencia" and t["agencia"]}):
        if not await _cuentas_de_la_agencia(db, agencia, barra.mundo):
            sin_cuentas.append(agencia)
    tarjetas_avisadas = await _nacer_tarjetas(db, current_user, barra, nuevas)

    # Un aviso por persona, con todas sus tareas (no a quien la aplicó: se
    # las asignó él mismo). Lleva a la ficha de la acción, como el de siempre.
    # Las de la agencia ya tuvieron el suyo ("tarjetas nuevas"): no dos.
    por_persona: dict[int, list[dict]] = {}
    for t in plan:
        if es_pieza(SimpleNamespace(tipo=t["tipo"], para=t["para"])):
            continue
        if t["asignado_a_id"] is not None and t["asignado_a_id"] != current_user.id:
            por_persona.setdefault(t["asignado_a_id"], []).append(t)
    for user_id, suyas in por_persona.items():
        _avisar(db, user_id, mensaje_de_asignaciones(
            current_user.full_name, [(t["titulo"], t["vence"]) for t in suyas], barra.nombre,
        ), barra_id, suyas[0]["id"])
    # Y a cada responsable de Tienda, uno con lo que lleva (0090).
    lleva: dict[int, list[dict]] = {}
    for t in plan:
        if t["responsable_id"] is not None and t["responsable_id"] != current_user.id:
            lleva.setdefault(t["responsable_id"], []).append(t)
    for user_id, suyas in lleva.items():
        _avisar(db, user_id, mensaje_de_responsable(
            current_user.full_name, ", ".join(t["titulo"] for t in suyas), barra.nombre,
            suyas[0]["agencia"] if len({t["agencia"] for t in suyas}) == 1 else None,
            min((t["vence"] for t in suyas if t["vence"]), default=None),
        ), barra_id, suyas[0]["id"])

    rev = await _nueva_revision(db, barra.mundo)
    await db.commit()
    return {
        "id": barra_id, "rev": _rev_para(current_user, rev), "creadas": len(plan),
        "avisados": len(por_persona) + len(lleva) + tarjetas_avisadas, "sinAsignar": sin_asignar,
        "tarjetas": sum(1 for t in plan if es_pieza(SimpleNamespace(tipo=t["tipo"], para=t["para"]))),
        # Las agencias nombradas que no tienen ninguna cuenta que entre a este
        # mundo: sus tarjetas nacieron, pero nadie de ellas las ve.
        "agenciasSinCuentas": sin_cuentas,
    }


# ---------------------------------------------------------------------------
# Copiar una acción a otra fecha
# ---------------------------------------------------------------------------
# Pedido de Ivan (15/11/2026): las acciones se repiten cada año y el
# Ciberlunes 2026 tiene que nacer del 2025 con todo lo que tenía. Qué lleva
# cada fila nueva está en app/services/calendario_copia.py; acá se busca,
# se decide quién sigue pudiendo ver el mundo y se guarda todo junto.

class CopiaDeBarra(BaseModel):
    # Lo genera el front, como al crear una acción: un reintento de la misma
    # copia (se cortó la conexión y la pantalla vuelve a mandarla) no la
    # duplica.
    id: str = Field(..., pattern=_ID)
    # Dónde arranca la copia. Dura lo mismo que la original.
    desde: Fecha
    # Si no viene, el de la original con el año corrido (nombre_para_la_copia).
    nombre: str | None = Field(None, min_length=1, max_length=1000)
    # El renglón libre en las fechas nuevas, que lo calcula el front con lo
    # que tiene en pantalla. Si no viene, el de la original.
    carril: int | None = Field(None, ge=0, le=500)

    @field_validator("nombre")
    @classmethod
    def _sin_espacios(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede quedar vacío")
        return v


_FECHA_IRREAL = "Con ese corrimiento {} quedaría en un año que no parece real: revisá la fecha"


@router.post("/barras/{barra_id}/copiar", status_code=201)
async def copiar_barra(
    barra_id: str,
    payload: CopiaDeBarra,
    request: Request,
    current_user: User = Depends(require_permission("calendario.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Una acción nueva, en el MISMO mundo y a partir de `desde`, con todo lo
    de la original: sus campos, sus piezas, sus tareas y
    sus avisos. Lo hecho vuelve a pendiente y lo que tenía fecha se corre lo
    mismo que la acción.

    - Las tareas se copian solo si la persona puede cargar tareas
      (`calendario.tareas`), como al crearlas a mano. Si no, se copia el resto
      y la respuesta lo dice (`tareasSinPermiso`).
    - Un responsable o un destinatario que ya no puede abrir ese mundo se saca.
    - Una tarea de Tienda cuyo responsable ahora es de una agencia sale sin
      responsable (19/11/2026), como al aplicar una plantilla.
    - Una cuenta de una agencia sale de los avisos (21/11/2026): son
      internos. Se cuenta en `destinatariosQuitados`.
    - A cada responsable le llega UN aviso con todas sus tareas.

    Todo en una transacción y con una sola revisión: quien mira el calendario
    ve aparecer la acción entera, nunca a medio copiar."""
    if await db.get(CalendarioBarra, payload.id) is not None:
        # Es un reintento de esta misma copia: ya está hecha.
        return {"id": payload.id, "rev": _rev_para(current_user, await _revision_actual(db)), "yaExistia": True}

    # Bloquear la original ordena la copia con quien le está agregando una
    # pieza o una tarea en ese momento: entra entera o no entra.
    origen = await _barra_o_404(db, barra_id, current_user, bloquear=True)
    corrimiento = payload.desde - origen.desde
    hasta = origen.hasta + corrimiento
    try:
        _fecha_razonable(hasta)
    except ValueError:
        raise HTTPException(status_code=422, detail=_FECHA_IRREAL.format("el fin de la acción"))
    _validar_rango(payload.desde, hasta)
    _exigir_en_su_alcance(current_user, payload.desde, hasta)

    piezas = (await db.execute(
        select(CalendarioPieza).where(CalendarioPieza.barra_id == barra_id)
        .order_by(CalendarioPieza.orden, CalendarioPieza.id)
    )).scalars().all()
    avisos = (await db.execute(
        select(CalendarioAviso).where(CalendarioAviso.barra_id == barra_id)
        .order_by(CalendarioAviso.dias_antes.desc(), CalendarioAviso.id)
    )).scalars().all()
    tareas = (await db.execute(
        select(CalendarioTarea).where(CalendarioTarea.barra_id == barra_id)
        .order_by(CalendarioTarea.orden, CalendarioTarea.created_at, CalendarioTarea.id)
    )).scalars().all()
    copia_tareas = _puede_gestionar_tareas(current_user)

    # Quién sigue pudiendo ver ese mundo, de una sola consulta.
    pedidos = {t.asignado_a_id for t in tareas if t.asignado_a_id is not None} if copia_tareas else set()
    if copia_tareas:
        pedidos.update(t.responsable_id for t in tareas if t.responsable_id is not None)
    for a in avisos:
        pedidos.update(ids_de_personas(a.destinatarios))
    personas = (await db.execute(select(User).where(User.id.in_(pedidos)))).scalars().all() if pedidos else []
    validos = {u.id for u in personas if _puede_ver_el_mundo(u, origen.mundo)}
    # Y quiénes son de una agencia (cuentas externas): una tarea de Tienda no
    # se copia a su nombre (ver copiar_tareas), y ningún aviso la lleva
    # (ver copiar_avisos).
    de_agencias = {u.id for u in personas if externos.es_externo(u)}

    nombre = payload.nombre or nombre_para_la_copia(origen.nombre, origen.desde, origen.hasta, payload.desde)
    barra = CalendarioBarra(**copiar_la_accion(
        origen, payload.id, corrimiento, nombre,
        origen.carril if payload.carril is None else payload.carril, current_user.id,
    ))
    filas_piezas = copiar_piezas(piezas, payload.id, corrimiento)
    copiadas_tareas = copiar_tareas(
        tareas if copia_tareas else [], payload.id, corrimiento, validos, current_user.id,
        de_agencias=de_agencias,
    )
    # El nombre de una tarjeta lleva el de su acción ("Ciberlunes 2025 -
    # Banners"): en la copia tiene que decir el de la acción nueva, también
    # en el aviso que le llega a la agencia. Uno escrito a mano no coincide
    # con el automático y se respeta.
    for f in copiadas_tareas.filas:
        if f.get("tipo") and f.get("titulo") == tipos_de_tarea.nombre_de_tarjeta(origen.nombre, f["tipo"]):
            f["titulo"] = tipos_de_tarea.nombre_de_tarjeta(nombre, f["tipo"])
    # Los avisos de Lanzar no se copian: la copia trae los suyos (0077).
    copiados_avisos = copiar_avisos(
        [a for a in avisos if not a.control], payload.id, corrimiento, validos, current_user.id,
        # Un aviso de un envío (0084) se cuenta desde el envío de la copia.
        piezas_copiadas={p.id: f["id"] for p, f in zip(piezas, filas_piezas)},
        # Los avisos son internos: quien ahora es de una agencia sale.
        de_agencias=de_agencias,
    )

    # Una pieza o una tarea con su propia fecha puede irse de rango aunque la
    # acción no (una pieza de diciembre de 2099 corrida un año).
    for filas, modelo, que in (
        (filas_piezas, CalendarioPieza, "una pieza"),
        (copiadas_tareas.filas, CalendarioTarea, "el vencimiento de una tarea"),
    ):
        for f in filas:
            for d in fechas_corridas(f, modelo):
                try:
                    _fecha_razonable(d)
                except ValueError:
                    raise HTTPException(status_code=422, detail=_FECHA_IRREAL.format(que))

    db.add(barra)
    try:
        # La acción primero: piezas, tareas y avisos apuntan a ella.
        await db.flush()
    except IntegrityError:
        # Dos envíos de la misma copia a la vez (el reintento salió antes de
        # que contestara el primero): el segundo esperó en el bloqueo de la
        # original y llega acá cuando el primero ya la guardó. Es la misma.
        await db.rollback()
        if await db.get(CalendarioBarra, payload.id) is not None:
            return {"id": payload.id, "rev": _rev_para(current_user, await _revision_actual(db)), "yaExistia": True}
        raise
    nuevas_piezas = [CalendarioPieza(**f) for f in filas_piezas]
    nuevas_tareas = [CalendarioTarea(**f) for f in copiadas_tareas.filas]
    nuevos_avisos = [CalendarioAviso(**f) for f in copiados_avisos.filas]
    db.add_all(nuevas_piezas)
    db.add_all(nuevas_tareas)
    db.add_all(nuevos_avisos)
    # Copiada a Redexpres: con su Lanzar, el de su fecha nueva.
    # Las tareas copiadas que ya se llaman así cuentan como que ya están.
    await db.flush()
    controles = await controles_redexpres.agregar(db, barra, current_user.id, alcance.hoy_en_uruguay())

    # Las tareas para la agencia (0070) se copian como tales y les nace su
    # tarjeta nueva (en Ingresado, sin la historia de la original), con UN
    # aviso por persona de la agencia.
    avisados = await _nacer_tarjetas(db, current_user, barra, nuevas_tareas)

    # UN aviso a cada responsable, con todas sus tareas. Lleva a la ficha de
    # la acción nueva, como el de una tarea creada a mano. Las piezas (las de
    # la agencia, y también las de Tienda con tipo y las de una agencia de
    # afuera) ya tuvieron el suyo de tarjeta: antes a quien hacía una pieza
    # de Tienda le llegaban dos avisos por lo mismo (revisión del 16/11/2026).
    # Es la misma regla que al aplicar una plantilla.
    for uid, suyas in tareas_por_responsable(
        [f for f in copiadas_tareas.filas
         if not es_pieza(SimpleNamespace(tipo=f.get("tipo"), para=f.get("para")))],
        current_user.id,
    ).items():
        vencimientos = [t["vence"] for t in suyas if t.get("vence")]
        _avisar(db, uid, mensaje_de_tareas_copiadas(
            current_user.full_name, [t["titulo"] for t in suyas], nombre,
            min(vencimientos) if vencimientos else None,
        ), payload.id, suyas[0]["id"])
        avisados += 1

    # Queda de dónde salió: "¿esto es copia de cuál?" es lo primero que se
    # pregunta cuando aparecen dos parecidas.
    db.add(AuditLog(
        user_id=current_user.id, action="calendario.copiar", resource="calendario_barra",
        resource_id=payload.id, ip_address=_client_ip(request),
        details={
            "origen": barra_id, "mundo": origen.mundo, "nombre": nombre,
            "desde": payload.desde.isoformat(), "hasta": hasta.isoformat(),
            "piezas": len(nuevas_piezas), "tareas": len(nuevas_tareas), "avisos": len(nuevos_avisos),
        },
    ))
    rev = await _nueva_revision(db, origen.mundo)
    await db.flush()
    # Lo que se devuelve es la acción como la trae /datos, en el mismo orden:
    # el front la pone en pantalla sin bajarse todo de nuevo, y cuando sí lo
    # baje no se le reacomoda nada.
    respuesta = {
        "id": payload.id,
        "rev": _rev_para(current_user, rev),
        "barra": _barra_json(
            barra,
            sorted(nuevas_piezas, key=lambda p: (p.orden, p.id)),
            sorted(nuevos_avisos, key=lambda a: (-a.dias_antes, a.id)),
            # Todas se crean en la misma transacción (mismo created_at).
            sorted(nuevas_tareas, key=lambda t: (t.orden, t.id)),
            entregas=(await resumenes_de_entregas(db, [t.id for t in nuevas_tareas])) if nuevas_tareas else {},
        ),
        "copiadas": {"piezas": len(nuevas_piezas), "tareas": len(nuevas_tareas), "avisos": len(nuevos_avisos)},
        "tareasSinPermiso": 0 if copia_tareas else len(tareas),
        "sinResponsable": copiadas_tareas.sin_responsable,
        "destinatariosQuitados": copiados_avisos.destinatarios_quitados,
        "avisosSinNadie": copiados_avisos.sin_nadie,
        "avisados": avisados,
    }
    if controles:
        # Lo que se le sumó acá no está en `barra`: que la pantalla traiga todo.
        respuesta["recargar"] = True
    await db.commit()
    # Un aviso que con la fecha nueva ya tendría que haber salido, sale ya.
    respuesta["enviadosAhora"] = await _avisar_sin_romper(db, payload.id) if nuevos_avisos or controles else 0
    return respuesta
