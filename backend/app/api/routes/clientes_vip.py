"""clientes_vip.py — el tablero de Clientes VIP (0091).

  GET  /clientes-vip/tablero               — todo lo de la pantalla de una vez
  GET  /clientes-vip/clientes              — la lista (segmento, búsqueda, orden, página)
  GET  /clientes-vip/clientes/{id}         — un cliente, mes a mes
  GET  /clientes-vip/informes              — los informes de Valentina
  POST /clientes-vip/informes              — Valentina publica su informe (con su predicción)
  GET  /clientes-vip/numeros               — el resumen del último mes para arrancar a analizar
  GET  /clientes-vip/datos?tabla=…         — una tabla entera en CSV (clientes_mes, dimensiones, clientes)
  GET  /clientes-vip/memoria               — lo que aprendió Valentina
  POST /clientes-vip/memoria               — anotar algo nuevo
  PATCH /clientes-vip/memoria/{id}         — corregir o retirar una nota
  POST /clientes-vip/cargas                — empezar una carga (los meses que trae el archivo)
  POST /clientes-vip/cargas/{id}/filas     — una tanda del resumen (hasta 5.000 filas)
  POST /clientes-vip/cargas/{id}/terminar  — los totales del mes; rehace la foto de cada cliente
  POST /clientes-vip/cargas/{id}/detalle   — una parte (gzip) del detalle para Valentina
  GET  /clientes-vip/detalle               — qué detalle hay (por carga y tabla)
  GET  /clientes-vip/detalle/{carga}/{tabla} — bajarlo (gzip)
  POST /clientes-vip/valentina/clientes    — lo que Valentina predice de cada cliente (tandas)

Ver app/services/clientes_vip.py. Ver: `clientes_vip.view`. Cargar, publicar
y escribir la memoria: `clientes_vip.cargar` (y ver). Valentina (la
economista del Escuadrón Lechuza, que corre en la nube) entra con su propia
cuenta con esos dos permisos. Los datos son confidenciales: ninguna ruta
devuelve nada a quien no tiene el permiso, ni a las cuentas externas.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alcance import hoy_en_uruguay
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.externos import puede_tener
from app.models.clientes_vip import (
    VipCarga, VipCliente, VipClienteMes, VipClienteValentina, VipDetalle, VipInforme, VipMesDimension,
)
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


def _fila_valentina(v: VipClienteValentina) -> dict:
    return {
        "mes": v.mes.strftime("%Y-%m"), "riesgo_abandono": v.riesgo_abandono, "proxima_categoria": v.proxima_categoria,
        "probabilidad_proxima": v.probabilidad_proxima, "potencial_mensual": v.potencial_mensual,
        "descubrio": v.descubrio, "dejo": v.dejo, "frecuencia": v.frecuencia, "mix": v.mix, "accion": v.accion,
    }


@router.get("/clientes/{id_cliente}")
async def cliente(id_cliente: int, db: AsyncSession = Depends(get_db),
                  _: User = Depends(require_permission(vip.PERMISO_VER))):
    c = await db.get(VipCliente, id_cliente)
    meses = (await db.execute(
        select(VipClienteMes).where(VipClienteMes.id_cliente == id_cliente).order_by(VipClienteMes.mes)
    )).scalars().all()
    if not c and not meses:
        raise HTTPException(404, "Ese cliente no está en los datos cargados")
    suya = await db.get(VipClienteValentina, id_cliente)
    return {
        "cliente": _fila_cliente(c) if c else None,
        "valentina": _fila_valentina(suya) if suya else None,
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


class Publicar(BaseModel):
    mes: str  # el último mes que analizó, AAAA-MM
    analisis: str = Field(..., min_length=50, max_length=40_000)  # Markdown
    prediccion: dict = Field(default_factory=dict)  # mes, venta, desde, hasta, margen_error, como…
    autor: str = Field("Valentina", min_length=1, max_length=60)


@router.post("/informes")
async def publicar_informe(body: Publicar, db: AsyncSession = Depends(get_db), _: User = Depends(puede_cargar)):
    """Valentina publica su informe: aparece en el tablero (y su predicción en
    «Lo que viene»). El mail lo manda ella desde la nube."""
    try:
        mes = vip.mes_de(body.mes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    informe = await vip.publicar_informe(db, mes, body.analisis.strip(), body.prediccion, body.autor.strip())
    return vip.fila_informe(informe)


@router.get("/numeros")
async def numeros(db: AsyncSession = Depends(get_db), _: User = Depends(require_permission(vip.PERMISO_VER))):
    datos = await vip.numeros_del_informe(db)
    if not datos:
        raise HTTPException(404, "Todavía no hay datos cargados")
    return datos


@router.get("/datos")
async def datos(tabla: str = Query("clientes_mes"), db: AsyncSession = Depends(get_db),
                _: User = Depends(require_permission(vip.PERMISO_VER))):
    if tabla not in vip.TABLAS_CSV:
        raise HTTPException(400, f"Tabla desconocida. Hay: {', '.join(vip.TABLAS_CSV)}")
    return StreamingResponse(vip.csv_de(db, tabla), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="vip_{tabla}.csv"',
                                      "Cache-Control": "no-store"})


@router.get("/memoria")
async def leer_memoria(retiradas: bool = False, db: AsyncSession = Depends(get_db),
                       _: User = Depends(require_permission(vip.PERMISO_VER))):
    return await vip.memoria(db, incluir_retiradas=retiradas)


class Nota(BaseModel):
    tema: str = Field(..., min_length=2, max_length=120)
    texto: str = Field(..., min_length=5, max_length=4000)
    fuente: str = Field("", max_length=240)


@router.post("/memoria")
async def anotar(body: Nota, db: AsyncSession = Depends(get_db), _: User = Depends(puede_cargar)):
    from app.models.agente_memoria import AgenteMemoria

    m = AgenteMemoria(agente=vip.AGENTE_VIP, ambito=vip.AMBITO_VIP, tema=body.tema.strip(),
                      texto=body.texto.strip(), fuente=body.fuente.strip())
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return vip.fila_memoria(m)


# ---------------------------------------------------------------------------
# El detalle comprimido de cada carga (para Valentina)
# ---------------------------------------------------------------------------

NOMBRES_DETALLE = ("cliente_mes_categoria", "cliente_subcategoria", "producto_mes", "productos")
_MAX_PARTE = 8 * 1024 * 1024
_GZIP = bytes([0x1F, 0x8B])


@router.post("/cargas/{carga_id}/detalle")
async def subir_detalle(carga_id: int, request: Request, nombre: str = Query(...), parte: int = Query(..., ge=0, le=999),
                        filas: int = Query(0, ge=0), db: AsyncSession = Depends(get_db), _: User = Depends(puede_cargar)):
    """Una parte (un gzip completo) de una de las tablas de detalle."""
    if nombre not in NOMBRES_DETALLE:
        raise HTTPException(400, f"Detalle desconocido. Hay: {', '.join(NOMBRES_DETALLE)}")
    carga = await _carga_abierta(db, carga_id)
    datos = await request.body()
    if not datos or len(datos) > _MAX_PARTE:
        raise HTTPException(400, "Cada parte tiene que pesar entre 1 byte y 8 MB")
    if datos[:2] != _GZIP:
        raise HTTPException(400, "La parte tiene que venir comprimida (gzip)")
    if not await hay_lugar(db, len(datos)):
        raise HTTPException(507, "La base está casi llena: el detalle no se guardó. Avisale a quien administra Core Tienda.")
    await db.execute(delete(VipDetalle).where(VipDetalle.carga_id == carga.id, VipDetalle.nombre == nombre,
                                              VipDetalle.parte == parte))
    db.add(VipDetalle(carga_id=carga.id, nombre=nombre, parte=parte, filas=filas, datos=datos))
    await db.commit()
    return {"nombre": nombre, "parte": parte, "bytes": len(datos)}


@router.get("/detalle")
async def indice_detalle(db: AsyncSession = Depends(get_db), _: User = Depends(require_permission(vip.PERMISO_VER))):
    """Qué detalle hay: por carga terminada, cada tabla con sus partes, filas y peso."""
    filas = (await db.execute(
        select(VipDetalle.carga_id, VipDetalle.nombre, func.count(), func.sum(VipDetalle.filas),
               func.sum(func.length(VipDetalle.datos)))
        .group_by(VipDetalle.carga_id, VipDetalle.nombre)
        .order_by(VipDetalle.carga_id, VipDetalle.nombre)
    )).all()
    cargas = {c.id: c for c in (await db.execute(
        select(VipCarga).where(VipCarga.id.in_({f[0] for f in filas}), VipCarga.estado == "lista")
    )).scalars()}
    return [
        {"carga_id": i, "archivo": cargas[i].archivo, "meses": cargas[i].meses,
         "fecha": cargas[i].created_at.isoformat() if cargas[i].created_at else None, "nombre": n,
         "partes": p, "filas": int(fi or 0), "bytes": int(b or 0)}
        for i, n, p, fi, b in filas if i in cargas
    ]


@router.get("/detalle/{carga_id}/{nombre}")
async def bajar_detalle(carga_id: int, nombre: str, db: AsyncSession = Depends(get_db),
                        _: User = Depends(require_permission(vip.PERMISO_VER))):
    """La tabla entera: las partes pegadas en orden (un gzip de varios miembros: se lee normal)."""
    ids = (await db.execute(
        select(VipDetalle.id).where(VipDetalle.carga_id == carga_id, VipDetalle.nombre == nombre)
        .order_by(VipDetalle.parte)
    )).scalars().all()
    if not ids:
        raise HTTPException(404, "No hay ese detalle para esa carga")

    async def partes():
        for i in ids:
            yield (await db.execute(select(VipDetalle.datos).where(VipDetalle.id == i))).scalar_one()

    return StreamingResponse(partes(), media_type="application/gzip",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}_{carga_id}.csv.gz"',
                                      "Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Lo que Valentina publica de cada cliente
# ---------------------------------------------------------------------------

class ClienteDeValentina(BaseModel):
    id_cliente: int = Field(..., gt=0)
    riesgo_abandono: float | None = Field(None, ge=0, le=1)
    proxima_categoria: str | None = Field(None, max_length=120)
    probabilidad_proxima: float | None = Field(None, ge=0, le=1)
    potencial_mensual: int | None = Field(None, ge=0, le=2_000_000_000)
    descubrio: str | None = Field(None, max_length=400)
    dejo: str | None = Field(None, max_length=400)
    frecuencia: str | None = Field(None, max_length=240)
    mix: str | None = Field(None, max_length=400)
    accion: str | None = Field(None, max_length=400)


class TandaDeValentina(BaseModel):
    mes: str
    filas: list[ClienteDeValentina] = Field(..., min_length=1, max_length=vip.FILAS_POR_TANDA)


@router.post("/valentina/clientes")
async def publicar_clientes(body: TandaDeValentina, db: AsyncSession = Depends(get_db), _: User = Depends(puede_cargar)):
    try:
        mes = vip.mes_de(body.mes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    filas = [{**f.model_dump(), "mes": mes, "actualizado": vip.ahora()} for f in body.filas]
    tabla = VipClienteValentina.__table__
    stmt = pg_insert(tabla)
    stmt = stmt.on_conflict_do_update(
        index_elements=[tabla.c.id_cliente],
        set_={c.name: stmt.excluded[c.name] for c in tabla.columns if c.name != "id_cliente"},
    )
    await db.execute(stmt, filas)
    await db.commit()
    return {"clientes": len(filas)}


class Correccion(BaseModel):
    texto: str | None = Field(None, min_length=5, max_length=4000)
    activo: bool | None = None


@router.patch("/memoria/{nota_id}")
async def corregir(nota_id: int, body: Correccion, db: AsyncSession = Depends(get_db),
                   _: User = Depends(puede_cargar)):
    from app.models.agente_memoria import AgenteMemoria

    m = await db.get(AgenteMemoria, nota_id)
    if not m or m.ambito != vip.AMBITO_VIP:
        raise HTTPException(404, "Esa nota no existe")
    if body.texto is not None:
        m.texto = body.texto.strip()
    if body.activo is not None:
        m.activo = body.activo
    await db.commit()
    await db.refresh(m)
    return vip.fila_memoria(m)


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
        meses = vip.meses_de_carga(body.meses, hoy_en_uruguay())
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
    # El detalle de las cargas anteriores cuyos meses están todos en esta se va
    # (ocupa lugar y ya no vale): el de esta carga los reemplaza.
    viejas = (await db.execute(select(VipCarga.id, VipCarga.meses).where(VipCarga.id != carga.id))).all()
    tapadas = [i for i, ms in viejas if ms and set(ms) <= set(carga.meses)]
    if tapadas:
        await db.execute(delete(VipDetalle).where(VipDetalle.carga_id.in_(tapadas)))
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
    # El informe lo escribe Valentina desde la nube: en su próxima vuelta ve la carga nueva.
    return {"id": carga.id, "clientes": clientes, "filas": carga.filas, "segmentos": await vip.segmentos(db)}
