"""clientes_vip.py — el tablero de Clientes VIP (0091).

  GET  /clientes-vip/tablero               — todo lo de la pantalla de una vez
  GET  /clientes-vip/clientes              — la lista (segmento, búsqueda, orden, página)
  GET  /clientes-vip/clientes/{id}         — un cliente, mes a mes
  GET  /clientes-vip/informes              — los informes de Sofía y Valentina
  POST /clientes-vip/informes              — rehacer el del último mes (si salió mal); `mandar` lo manda por mail
  POST /clientes-vip/cargas                — empezar una carga (los meses que trae el archivo)
  POST /clientes-vip/cargas/{id}/filas     — una tanda del resumen (hasta 5.000 filas)
  POST /clientes-vip/cargas/{id}/terminar  — los totales del mes; rehace la foto y dispara el informe

Ver app/services/clientes_vip.py. Ver: `clientes_vip.view`. Cargar:
`clientes_vip.cargar` (y ver). Los datos son confidenciales: ninguna ruta
devuelve nada a quien no tiene el permiso, ni a las cuentas externas.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.externos import puede_tener
from app.models.clientes_vip import VipCarga, VipCliente, VipClienteMes, VipInforme, VipMesDimension
from app.models.user import User
from app.services import clientes_vip as vip
from app.services.espacio import hay_lugar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clientes-vip", tags=["clientes-vip"])

# Lo que ocupa en la base cada fila por cliente y mes, con su índice (para el
# freno de espacio antes de empezar).
_BYTES_POR_FILA = 200
_ORDENES = {
    "riesgo": (VipCliente.riesgo.desc(), VipCliente.venta_3m_antes.desc()),
    "venta": (VipCliente.venta_12m.desc(),),
    "esperada": (VipCliente.venta_esperada.desc(),),
    "caida": ((VipCliente.venta_3m_antes - VipCliente.venta_3m).desc(),),
    "cliente": (VipCliente.id_cliente,),
}


async def puede_cargar(user: User = Depends(require_permission(vip.PERMISO_CARGAR))) -> User:
    if not puede_tener(user, vip.PERMISO_VER):
        raise HTTPException(403, f"Permiso requerido: {vip.PERMISO_VER}")
    return user


# ---------------------------------------------------------------------------
# Ver
# ---------------------------------------------------------------------------

@router.get("/tablero")
async def tablero(db: AsyncSession = Depends(get_db), _: User = Depends(require_permission(vip.PERMISO_VER))):
    return await vip.tablero(db)


def _fila_cliente(c: VipCliente) -> dict:
    return {
        "id_cliente": c.id_cliente, "segmento": c.segmento, "riesgo": c.riesgo, "venta_esperada": c.venta_esperada,
        "venta_12m": c.venta_12m, "venta_3m": c.venta_3m, "venta_3m_antes": c.venta_3m_antes,
        "margen_12m": c.margen_12m, "tickets_12m": c.tickets_12m, "meses_con_compra": c.meses_con_compra,
        "ultimo_mes": c.ultimo_mes.strftime("%Y-%m") if c.ultimo_mes else None, "sucursal": c.sucursal,
        "categoria": c.categoria, "parte_ecommerce": c.parte_ecommerce,
    }


@router.get("/clientes")
async def clientes(
    segmento: str | None = None,
    q: str | None = Query(None, max_length=40),
    orden: str = "riesgo",
    pagina: int = Query(1, ge=1, le=10_000),
    por_pagina: int = Query(50, ge=10, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(vip.PERMISO_VER)),
):
    filtro = []
    if segmento:
        if segmento not in vip.SEGMENTOS:
            raise HTTPException(400, "Ese segmento no existe")
        filtro.append(VipCliente.segmento == segmento)
    if q and q.strip():
        texto = q.strip()
        condiciones = [VipCliente.sucursal.ilike(f"%{texto}%"), VipCliente.categoria.ilike(f"%{texto}%")]
        if texto.isdigit():
            condiciones.append(VipCliente.id_cliente == int(texto))
        filtro.append(or_(*condiciones))
    total = await db.scalar(select(func.count()).select_from(VipCliente).where(*filtro))
    filas = await db.execute(
        select(VipCliente).where(*filtro).order_by(*_ORDENES.get(orden, _ORDENES["riesgo"]))
        .offset((pagina - 1) * por_pagina).limit(por_pagina)
    )
    return {"total": total or 0, "pagina": pagina, "por_pagina": por_pagina,
            "filas": [_fila_cliente(c) for c in filas.scalars()]}


@router.get("/clientes/{id_cliente}")
async def cliente(id_cliente: int, db: AsyncSession = Depends(get_db),
                  _: User = Depends(require_permission(vip.PERMISO_VER))):
    c = await db.get(VipCliente, id_cliente)
    meses = (await db.execute(
        select(VipClienteMes).where(VipClienteMes.id_cliente == id_cliente).order_by(VipClienteMes.mes)
    )).scalars().all()
    if not c and not meses:
        raise HTTPException(404, "Ese cliente no está en los datos cargados")
    return {
        "cliente": _fila_cliente(c) if c else None,
        "meses": [
            {"mes": m.mes.strftime("%Y-%m"), "venta": m.venta, "margen": m.margen, "unidades": m.unidades,
             "tickets": m.tickets, "dias": m.dias, "venta_ecommerce": m.venta_ecommerce,
             "venta_smart": m.venta_smart, "venta_marca_propia": m.venta_marca_propia, "sucursal": m.sucursal,
             "categorias": [
                 {"nombre": n, "venta": vip.entero(v)}
                 for n, _, v in (p.rpartition("=") for p in (m.categorias or "").split(";") if p)
             ]}
            for m in meses
        ],
    }


@router.get("/informes")
async def informes(db: AsyncSession = Depends(get_db), _: User = Depends(require_permission(vip.PERMISO_VER))):
    filas = await db.execute(select(VipInforme).order_by(VipInforme.id.desc()).limit(24))
    return [vip.fila_informe(i) for i in filas.scalars()]


class Rehacer(BaseModel):
    mandar: bool = False


@router.post("/informes")
async def rehacer_informe(body: Rehacer, db: AsyncSession = Depends(get_db), user: User = Depends(puede_cargar)):
    """Vuelve a escribir el informe del último mes (por ejemplo, si la IA falló
    o salió cortado). Por defecto no manda mail; con `mandar`, como al cargar."""
    informe = await vip.armar_informe(db, None, user.id, mandar=body.mandar)
    if not informe:
        raise HTTPException(404, "Todavía no hay datos cargados")
    return vip.fila_informe(informe)


# ---------------------------------------------------------------------------
# Cargar
# ---------------------------------------------------------------------------

class CargaNueva(BaseModel):
    archivo: str = Field(..., min_length=1, max_length=255)
    meses: list[str] = Field(..., min_length=1, max_length=36)
    filas_archivo: int = Field(0, ge=0)
    filas: int = Field(..., ge=1, le=2_000_000)


@router.post("/cargas")
async def empezar_carga(body: CargaNueva, db: AsyncSession = Depends(get_db), user: User = Depends(puede_cargar)):
    try:
        meses = sorted({vip.mes_de(m) for m in body.meses})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not await hay_lugar(db, body.filas * _BYTES_POR_FILA):
        raise HTTPException(
            507, "La base está casi llena y este archivo no entra: avisale a quien administra Core Tienda. No se cargó nada.",
        )
    carga = VipCarga(archivo=body.archivo.strip(), meses=[m.strftime("%Y-%m") for m in meses],
                     filas_archivo=body.filas_archivo, subido_por_id=user.id)
    db.add(carga)
    await db.commit()
    return {"id": carga.id, "meses": carga.meses}


class Tanda(BaseModel):
    # [id_cliente, "AAAA-MM", venta, margen, unidades, tickets, dias,
    #  venta_ecommerce, venta_smart, venta_marca_propia, sucursal, categorias]
    filas: list[list[int | float | str | None]] = Field(..., min_length=1, max_length=vip.FILAS_POR_TANDA)


async def _carga_abierta(db: AsyncSession, carga_id: int) -> VipCarga:
    carga = await db.get(VipCarga, carga_id)
    if not carga:
        raise HTTPException(404, "Esa carga no existe")
    if carga.estado != "cargando":
        raise HTTPException(409, "Esa carga ya terminó: empezá una nueva")
    return carga


def _fila(f: list, meses: dict[str, object], carga_id: int) -> dict:
    if len(f) != 12:
        raise ValueError("cada fila tiene 12 datos")
    id_cliente = int(f[0])
    if id_cliente <= 0:
        raise ValueError("número de cliente inválido")
    mes = meses.get(str(f[1]))
    if mes is None:
        raise ValueError(f"el mes {f[1]} no es de esta carga")
    e = vip.entero
    return {
        "id_cliente": id_cliente, "mes": mes, "venta": e(f[2]), "margen": e(f[3]), "unidades": e(f[4]),
        "tickets": e(f[5], 0), "dias": e(f[6], 0, 31), "venta_ecommerce": e(f[7]), "venta_smart": e(f[8]),
        "venta_marca_propia": e(f[9]), "sucursal": (str(f[10])[:80] if f[10] else None),
        "categorias": (str(f[11])[:240] if f[11] else None), "carga_id": carga_id,
    }


@router.post("/cargas/{carga_id}/filas")
async def subir_tanda(carga_id: int, body: Tanda, db: AsyncSession = Depends(get_db), _: User = Depends(puede_cargar)):
    carga = await _carga_abierta(db, carga_id)
    meses = {m: vip.mes_de(m) for m in carga.meses}
    try:
        filas = [_fila(f, meses, carga.id) for f in body.filas]
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"Una fila no se pudo leer: {exc}") from exc
    tabla = VipClienteMes.__table__
    stmt = pg_insert(tabla)
    stmt = stmt.on_conflict_do_update(
        index_elements=[tabla.c.id_cliente, tabla.c.mes],
        set_={c.name: stmt.excluded[c.name] for c in tabla.columns if c.name not in ("id_cliente", "mes")},
    )
    await db.execute(stmt, filas)
    carga.filas += len(filas)
    await db.commit()
    return {"filas": carga.filas}


class Dimension(BaseModel):
    mes: str
    dimension: str
    valor: str = Field(..., min_length=1, max_length=120)
    venta: float
    margen: float
    unidades: float
    tickets: int = Field(..., ge=0)
    clientes: int = Field(..., ge=0)


class Cierre(BaseModel):
    dimensiones: list[Dimension] = Field(default_factory=list, max_length=20_000)
    clientes: int = Field(0, ge=0)
    venta: float = 0


@router.post("/cargas/{carga_id}/terminar")
async def terminar_carga(carga_id: int, body: Cierre, db: AsyncSession = Depends(get_db),
                         user: User = Depends(puede_cargar)):
    carga = await _carga_abierta(db, carga_id)
    meses = {m: vip.mes_de(m) for m in carga.meses}
    dims = []
    for d in body.dimensiones:
        if d.mes not in meses or d.dimension not in vip.DIMENSIONES:
            raise HTTPException(400, f"Un total no es de esta carga: {d.mes} / {d.dimension}")
        dims.append({"mes": meses[d.mes], "dimension": d.dimension, "valor": d.valor.strip()[:120],
                     "venta": round(d.venta), "margen": round(d.margen), "unidades": round(d.unidades),
                     "tickets": d.tickets, "clientes": d.clientes})
    # Lo de estos meses que no vino en esta carga (de una carga anterior) se va.
    await db.execute(delete(VipClienteMes).where(VipClienteMes.mes.in_(list(meses.values())),
                                                 VipClienteMes.carga_id != carga.id))
    await db.execute(delete(VipMesDimension).where(VipMesDimension.mes.in_(list(meses.values()))))
    if dims:
        tabla = VipMesDimension.__table__
        stmt = pg_insert(tabla)
        stmt = stmt.on_conflict_do_update(
            index_elements=[tabla.c.mes, tabla.c.dimension, tabla.c.valor],
            set_={c: stmt.excluded[c] for c in ("venta", "margen", "unidades", "tickets", "clientes")},
        )
        await db.execute(stmt, dims)
    clientes = await vip.recalcular(db)
    carga.estado = "lista"
    carga.clientes = body.clientes or clientes
    carga.venta = round(body.venta)
    carga.terminada_at = vip.ahora()
    await db.commit()
    vip.informe_en_segundo_plano(carga.id, user.id)
    return {"id": carga.id, "clientes": clientes, "filas": carga.filas, "segmentos": await vip.segmentos(db)}
