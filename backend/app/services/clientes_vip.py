"""Clientes VIP: el tablero y lo que necesita Valentina, la economista del Escuadrón Lechuza.

Ivan (25/11/2026): "vamos a hacer nosotros el dashboard… voy a pasarte un
montón de excels que vamos a ir actualizando todos los meses… un agente que
analice… prever el comportamiento futuro de los clientes VIP… un agente de
nuestro equipo se dedique a también mandar estos correos… y debemos crear a
un agente de predicción". Y: "la idea es que esto lo pueda tener en línea todo
el mundo" (quien tenga el permiso), sin subir archivos de 500 MB.

Cómo anda:

1. **Carga** (frontend: lib/clientes-vip/lector.worker.ts). El navegador de
   quien carga lee el CSV (o el zip) de a pedazos y arma una fila por cliente
   y por mes; sube eso en tandas (`/clientes-vip/cargas`). El archivo nunca
   sale de la PC. Cargar de nuevo un mes lo reemplaza.
2. **Foto de cada cliente** (`recalcular`): con los últimos 15 meses, a cada
   cliente se le calcula el segmento, el riesgo de dejar de comprar (0 a 100)
   y lo que se espera que compre el mes que viene (`perfil`). Es estadística
   simple y explicable, sin IA: los números tienen que dar siempre lo mismo.
3. **Informe**: lo escribe Valentina, la economista y estadística del
   Escuadrón Lechuza, que corre en la nube (no acá). Baja los datos con su
   cuenta (`/clientes-vip/datos`, `/numeros`), investiga, modela, publica el
   informe (`POST /clientes-vip/informes`), guarda lo que aprende en su
   memoria (`/clientes-vip/memoria`) y manda el mail. La plataforma no escribe
   informes ni manda mails de Clientes VIP. `prediccion_global` queda como el
   cálculo rápido que se ve hasta que ella publica el suyo.

Los datos son confidenciales: viven acá, los ve quien tiene el permiso y
nunca van al repo.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clientes_vip import VipCarga, VipCliente, VipClienteMes, VipInforme, VipMesDimension
from app.models.user import User

logger = logging.getLogger(__name__)

PERMISO_VER = "clientes_vip.view"
PERMISO_CARGAR = "clientes_vip.cargar"

# El orden en que se muestran.
SEGMENTOS = ["Creciendo", "Estable", "Nuevo", "Bajando", "En riesgo", "Perdido"]
DIMENSIONES = ("categoria", "sucursal", "canal", "marca_propia")
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
            "octubre", "noviembre", "diciembre"]

# Lo que se trae para la foto de cada cliente: 12 meses + 3 para ver hace
# cuánto que no compra quien dejó.
VENTANA_MESES = 15
FILAS_POR_TANDA = 5000
_INT32 = 2_147_483_647


# ---------------------------------------------------------------------------
# Meses
# ---------------------------------------------------------------------------

def sumar_meses(d: date, n: int) -> date:
    i = d.year * 12 + (d.month - 1) + n
    return date(i // 12, i % 12 + 1, 1)


def meses_entre(desde: date, hasta: date) -> int:
    return (hasta.year - desde.year) * 12 + hasta.month - desde.month


def mes_de(texto: str) -> date:
    """'2026-03' → date(2026, 3, 1). ValueError si no es un mes."""
    if not re.fullmatch(r"\d{4}-\d{2}", texto or ""):
        raise ValueError(f"Mes inválido: {texto!r}")
    a, m = int(texto[:4]), int(texto[5:])
    if not (2000 <= a <= 2100 and 1 <= m <= 12):
        raise ValueError(f"Mes inválido: {texto!r}")
    return date(a, m, 1)


def meses_de_carga(textos: list[str], hoy: date) -> list[date]:
    """Los meses que trae un archivo, ordenados. Pura.

    Un mes que todavía no llegó es un error de tipeo en el archivo (un año
    2062): si entrara, pasaría a ser «el último mes» y cambiaría el segmento
    de todos los clientes (H-088, 26/11/2026). El navegador ya deja afuera
    esas filas y dice cuáles son (`problemaDelMes` en
    frontend/lib/clientes-vip/resumen.ts); esto frena lo que llegue igual.
    """
    meses = sorted({mes_de(t) for t in textos})
    if meses and meses[-1] > hoy.replace(day=1):
        raise ValueError(f"El archivo trae compras de {nombre_mes(meses[-1])}, un mes que todavía no llegó: "
                         "revisá las fechas del archivo. No se cargó nada.")
    return meses


def nombre_mes(d: date, con_anio: bool = True) -> str:
    return f"{MESES_ES[d.month - 1]} {d.year}" if con_anio else MESES_ES[d.month - 1]


def entero(valor, minimo: int = -_INT32, maximo: int = _INT32) -> int:
    try:
        n = int(round(float(valor)))
    except (TypeError, ValueError):
        return 0
    return max(minimo, min(maximo, n))


# ---------------------------------------------------------------------------
# La foto de cada cliente (puro)
# ---------------------------------------------------------------------------

def factor_estacional(serie: dict[date, int], ultimo: date) -> float:
    """Cuánto cambia el mes que viene respecto de los últimos tres, según lo
    que pasó el año anterior. 1.0 si no hay un año de historia. Con tope, para
    que un mes raro no dispare todo."""
    objetivo = serie.get(sumar_meses(ultimo, -11))
    base = [serie.get(sumar_meses(ultimo, -12 - k)) for k in range(3)]
    if not objetivo or any(not b for b in base):
        return 1.0
    ponderado = 0.5 * base[0] + 0.3 * base[1] + 0.2 * base[2]
    return max(0.7, min(1.4, objetivo / ponderado)) if ponderado > 0 else 1.0


def perfil(historial: dict[date, tuple[int, int]], ultimo: date, primer_mes_datos: date,
           estacional: float = 1.0) -> dict:
    """Segmento, riesgo (0-100) y venta esperada del mes que viene de UN
    cliente. `historial`: mes → (venta, tickets). Pura.

    - Perdido: no compra hace 3 meses o más.
    - Nuevo: su primera compra es de los últimos 3 meses y hay al menos 3
      meses de datos antes (si no, no se puede saber si es nuevo).
    - En riesgo: no compró el último mes (o los dos últimos), o sus últimos 3
      meses cayeron más de 40% contra los 3 de antes.
    - Bajando: cayeron entre 10% y 40%. Creciendo: subieron más de 10%.
      Estable: el resto.
    """
    def venta(k: int) -> int:
        return historial.get(sumar_meses(ultimo, -k), (0, 0))[0]

    def tickets(k: int) -> int:
        return historial.get(sumar_meses(ultimo, -k), (0, 0))[1]

    con_compra = sorted(m for m, (v, _) in historial.items() if v > 0 and m <= ultimo)
    if not con_compra:
        return {"segmento": "Perdido", "riesgo": 100, "venta_esperada": 0}
    recencia = meses_entre(con_compra[-1], ultimo)
    v3, v3a = sum(venta(k) for k in range(3)), sum(venta(k) for k in range(3, 6))
    t3, t3a = sum(tickets(k) for k in range(3)), sum(tickets(k) for k in range(3, 6))
    razon = v3 / v3a if v3a > 0 else (2.0 if v3 > 0 else 1.0)
    nuevo = con_compra[0] >= sumar_meses(ultimo, -2) and meses_entre(primer_mes_datos, con_compra[0]) >= 3

    if recencia >= 3:
        segmento = "Perdido"
    elif nuevo:
        segmento = "Nuevo"
    elif recencia >= 1 or (v3a > 0 and razon < 0.6):
        segmento = "En riesgo"
    elif razon < 0.9:
        segmento = "Bajando"
    elif razon > 1.1:
        segmento = "Creciendo"
    else:
        segmento = "Estable"

    if recencia >= 3:
        riesgo = 100
    else:
        caida = max(0.0, min(1.0, 1 - razon))
        caida_frecuencia = max(0.0, min(1.0, 1 - t3 / t3a)) if t3a > 0 else 0.0
        riesgo = round(100 * (0.45 * min(recencia, 3) / 3 + 0.35 * caida + 0.20 * caida_frecuencia))

    base = 0.5 * venta(0) + 0.3 * venta(1) + 0.2 * venta(2)
    return {"segmento": segmento, "riesgo": int(riesgo), "venta_esperada": max(0, round(base * estacional))}


def _sumar_categorias(textos: list[str | None]) -> dict[str, int]:
    total: dict[str, int] = defaultdict(int)
    for t in textos:
        for parte in (t or "").split(";"):
            nombre, _, monto = parte.rpartition("=")
            if nombre:
                total[nombre] += entero(monto)
    return total


def ficha(id_cliente: int, filas: list[tuple], ultimo: date, primer_mes_datos: date, estacional: float) -> dict:
    """La fila de vip_clientes de un cliente. `filas`: (mes, venta, margen,
    tickets, venta_ecommerce, sucursal, categorias) de sus últimos meses."""
    desde12 = sumar_meses(ultimo, -11)
    historial = {f[0]: (f[1], f[3]) for f in filas}
    ult12 = [f for f in filas if f[0] >= desde12]
    venta_12m = sum(f[1] for f in ult12)
    por_sucursal: dict[str, int] = defaultdict(int)
    for f in ult12:
        if f[5]:
            por_sucursal[f[5]] += f[1]
    categorias = _sumar_categorias([f[6] for f in ult12])
    con_compra = [f[0] for f in filas if f[1] > 0]
    p = perfil(historial, ultimo, primer_mes_datos, estacional)
    return {
        "id_cliente": id_cliente,
        **p,
        "venta_12m": venta_12m,
        "venta_3m": entero(sum(historial.get(sumar_meses(ultimo, -k), (0, 0))[0] for k in range(3))),
        "venta_3m_antes": entero(sum(historial.get(sumar_meses(ultimo, -k), (0, 0))[0] for k in range(3, 6))),
        "margen_12m": sum(f[2] for f in ult12),
        "tickets_12m": entero(sum(f[3] for f in ult12)),
        "meses_con_compra": sum(1 for f in ult12 if f[1] > 0),
        "ultimo_mes": max(con_compra) if con_compra else None,
        "sucursal": max(por_sucursal, key=por_sucursal.get) if por_sucursal else None,
        "categoria": max(categorias, key=categorias.get)[:120] if categorias else None,
        "parte_ecommerce": entero(100 * sum(f[4] for f in ult12) / venta_12m, 0, 100) if venta_12m > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Valentina: la venta del mes que viene (puro)
# ---------------------------------------------------------------------------

def _por_anio_anterior(serie: dict[date, int], objetivo: date) -> float | None:
    """La venta del mismo mes del año anterior, con la tendencia de los
    últimos 3 meses contra los mismos 3 del año anterior."""
    anterior = serie.get(sumar_meses(objetivo, -12))
    ahora = [serie.get(sumar_meses(objetivo, -k)) for k in (1, 2, 3)]
    antes = [serie.get(sumar_meses(objetivo, -12 - k)) for k in (1, 2, 3)]
    if not anterior or any(not x for x in ahora + antes):
        return None
    return anterior * sum(ahora) / sum(antes)


def prediccion_global(serie: dict[date, int], ultimo: date, suma_esperadas: int) -> dict:
    """Lo que Valentina espera que se venda el mes que viene a los clientes
    VIP, con su margen de error. Dos caminos: el mismo mes del año anterior
    con la tendencia de hoy, y la suma de lo que se espera de cada cliente.
    Si están los dos, el promedio. El margen sale de probar el primer camino
    con los meses que ya pasaron (si no hay con qué, 10%). Pura."""
    objetivo = sumar_meses(ultimo, 1)
    anio = _por_anio_anterior(serie, objetivo)
    caminos = [c for c in (anio, float(suma_esperadas) if suma_esperadas > 0 else None) if c]
    venta = round(sum(caminos) / len(caminos)) if caminos else 0

    errores = []
    for mes, real in serie.items():
        estimado = _por_anio_anterior(serie, mes)
        if estimado and real > 0 and mes <= ultimo:
            errores.append(abs(estimado - real) / real)
    margen = sum(errores) / len(errores) if len(errores) >= 2 else 0.10
    margen = max(0.03, min(0.30, margen))
    actual = serie.get(ultimo, 0)
    anterior = serie.get(sumar_meses(objetivo, -12))
    return {
        "mes": objetivo.strftime("%Y-%m"),
        "venta": venta,
        "desde": round(venta * (1 - margen)),
        "hasta": round(venta * (1 + margen)),
        "margen_error": round(margen * 100, 1),
        "contra_este_mes": round(100 * (venta / actual - 1), 1) if actual else None,
        "contra_anio_anterior": round(100 * (venta / anterior - 1), 1) if anterior else None,
        "como": ("el mismo mes del año pasado con la tendencia de hoy, y lo que se espera de cada cliente"
                 if anio and suma_esperadas > 0 else
                 "el mismo mes del año pasado con la tendencia de hoy" if anio else
                 "lo que se espera de cada cliente según sus últimos meses"),
    }


# ---------------------------------------------------------------------------
# Base: carga, foto, tablero
# ---------------------------------------------------------------------------

async def serie_mensual(db: AsyncSession) -> dict[date, int]:
    filas = await db.execute(select(VipClienteMes.mes, func.sum(VipClienteMes.venta)).group_by(VipClienteMes.mes))
    return {m: int(v or 0) for m, v in filas.all()}


async def recalcular(db: AsyncSession) -> int:
    """Rehace vip_clientes con los últimos meses cargados. Devuelve cuántos
    clientes quedaron. No commitea."""
    ultimo = await db.scalar(select(func.max(VipClienteMes.mes)))
    await db.execute(delete(VipCliente))
    if not ultimo:
        return 0
    primero = await db.scalar(select(func.min(VipClienteMes.mes)))
    estacional = factor_estacional(await serie_mensual(db), ultimo)
    filas = await db.execute(
        select(VipClienteMes.id_cliente, VipClienteMes.mes, VipClienteMes.venta, VipClienteMes.margen,
               VipClienteMes.tickets, VipClienteMes.venta_ecommerce, VipClienteMes.sucursal,
               VipClienteMes.categorias)
        .where(VipClienteMes.mes >= sumar_meses(ultimo, -(VENTANA_MESES - 1)))
        .order_by(VipClienteMes.id_cliente, VipClienteMes.mes)
    )
    por_cliente: dict[int, list[tuple]] = defaultdict(list)
    for f in filas.all():
        por_cliente[f[0]].append(tuple(f[1:]))
    fichas = [ficha(c, fs, ultimo, primero, estacional) for c, fs in por_cliente.items()]
    for i in range(0, len(fichas), FILAS_POR_TANDA):
        await db.execute(VipCliente.__table__.insert(), fichas[i:i + FILAS_POR_TANDA])
    return len(fichas)


def _variacion(ahora: float, antes: float) -> float | None:
    return round(100 * (ahora / antes - 1), 1) if antes else None


async def kpis_por_mes(db: AsyncSession) -> list[dict]:
    m = VipClienteMes
    filas = await db.execute(
        select(m.mes, func.sum(m.venta), func.sum(m.margen), func.count().filter(m.venta > 0), func.sum(m.tickets),
               func.sum(m.unidades), func.sum(m.venta_ecommerce), func.sum(m.venta_smart),
               func.sum(m.venta_marca_propia))
        .group_by(m.mes).order_by(m.mes)
    )
    salida = []
    for mes, venta, margen, clientes, tickets, unidades, ecom, smart, mp in filas.all():
        venta, tickets, clientes = int(venta or 0), int(tickets or 0), int(clientes or 0)
        salida.append({
            "mes": mes.strftime("%Y-%m"), "venta": venta, "margen": int(margen or 0), "clientes": clientes,
            "tickets": tickets, "unidades": int(unidades or 0), "venta_ecommerce": int(ecom or 0),
            "venta_smart": int(smart or 0), "venta_marca_propia": int(mp or 0),
            "ticket_promedio": round(venta / tickets) if tickets else 0,
            "frecuencia": round(tickets / clientes, 2) if clientes else 0,
        })
    return salida


async def dimensiones(db: AsyncSession, ultimo: date) -> dict[str, list[dict]]:
    """Por categoría, sucursal, canal y marca propia: la venta del último mes y
    de los últimos 3, cómo cambió contra los 3 de antes y contra el año
    anterior, y el margen."""
    desde = sumar_meses(ultimo, -14)
    filas = await db.execute(select(VipMesDimension).where(VipMesDimension.mes >= desde))
    acum: dict[tuple[str, str], dict] = {}
    for d in filas.scalars():
        a = acum.setdefault((d.dimension, d.valor), defaultdict(int))
        k = meses_entre(d.mes, ultimo)
        if k == 0:
            a["venta_mes"] += d.venta
            a["clientes_mes"] += d.clientes
        if 0 <= k <= 2:
            a["venta_3m"] += d.venta
            a["margen_3m"] += d.margen
        elif 3 <= k <= 5:
            a["venta_3m_antes"] += d.venta
        elif 12 <= k <= 14:
            a["venta_3m_anio_anterior"] += d.venta
    salida: dict[str, list[dict]] = {dim: [] for dim in DIMENSIONES}
    for (dim, valor), a in acum.items():
        if dim not in salida or not (a["venta_3m"] or a["venta_3m_antes"]):
            continue
        salida[dim].append({
            "valor": valor, "venta_mes": a["venta_mes"], "clientes_mes": a["clientes_mes"],
            "venta_3m": a["venta_3m"], "venta_3m_antes": a["venta_3m_antes"],
            "margen_3m": round(100 * a["margen_3m"] / a["venta_3m"], 1) if a["venta_3m"] else None,
            "contra_3m_antes": _variacion(a["venta_3m"], a["venta_3m_antes"]),
            "contra_anio_anterior": _variacion(a["venta_3m"], a["venta_3m_anio_anterior"]),
        })
    for lista in salida.values():
        lista.sort(key=lambda x: -x["venta_3m"])
    return salida


async def segmentos(db: AsyncSession) -> list[dict]:
    c = VipCliente
    filas = await db.execute(
        select(c.segmento, func.count(), func.sum(c.venta_3m), func.sum(c.venta_3m_antes), func.sum(c.venta_esperada))
        .group_by(c.segmento)
    )
    por = {s: (n, int(v3 or 0), int(v3a or 0), int(e or 0)) for s, n, v3, v3a, e in filas.all()}
    return [
        {"segmento": s, "clientes": por[s][0], "venta_3m": por[s][1], "venta_3m_antes": por[s][2],
         "venta_esperada": por[s][3]}
        for s in SEGMENTOS if s in por
    ]


def fila_carga(c: VipCarga, nombre: str | None) -> dict:
    return {
        "id": c.id, "archivo": c.archivo, "meses": c.meses, "filas_archivo": c.filas_archivo, "filas": c.filas,
        "clientes": c.clientes, "venta": c.venta, "estado": c.estado, "subido_por": nombre,
        "fecha": c.created_at.isoformat() if c.created_at else None,
    }


def fila_informe(i: VipInforme | None) -> dict | None:
    if not i:
        return None
    return {"id": i.id, "mes": i.mes.strftime("%Y-%m"), "analisis": i.analisis, "prediccion": i.prediccion,
            "con_ia": i.con_ia, "enviado_a": i.enviado_a, "autor": i.autor,
            "fecha": i.created_at.isoformat() if i.created_at else None}


async def tablero(db: AsyncSession) -> dict:
    """Todo lo que muestra la pantalla de una vez."""
    ultimo = await db.scalar(select(func.max(VipClienteMes.mes)))
    cargas = await db.execute(
        select(VipCarga, User.full_name).outerjoin(User, User.id == VipCarga.subido_por_id)
        .order_by(VipCarga.id.desc()).limit(12)
    )
    lista_cargas = [fila_carga(c, n) for c, n in cargas.all()]
    if not ultimo:
        return {"ultimo_mes": None, "meses": [], "dimensiones": {d: [] for d in DIMENSIONES}, "segmentos": [],
                "prediccion": None, "prediccion_valentina": None, "informe": None, "cargas": lista_cargas,
                "clientes": 0, "memoria": 0}
    segs = await segmentos(db)
    serie = await serie_mensual(db)
    informe = await db.scalar(select(VipInforme).order_by(VipInforme.id.desc()).limit(1))
    # La predicción de Valentina, si ya analizó el último mes cargado.
    suya = informe.prediccion if informe and informe.mes == ultimo and (informe.prediccion or {}).get("venta") else None
    return {
        "ultimo_mes": ultimo.strftime("%Y-%m"),
        "meses": await kpis_por_mes(db),
        "dimensiones": await dimensiones(db, ultimo),
        "segmentos": segs,
        "prediccion": prediccion_global(serie, ultimo, sum(s["venta_esperada"] for s in segs)),
        "prediccion_valentina": suya,
        "memoria": sum(1 for m in await memoria(db) if not m["tema"].startswith("_")),
        "informe": fila_informe(informe),
        "cargas": lista_cargas,
        "clientes": sum(s["clientes"] for s in segs),
    }


# ---------------------------------------------------------------------------
# El informe del mes: lo escribe Valentina (análisis y predicción)
# ---------------------------------------------------------------------------

def _kpi(meses: dict[str, dict], clave: date) -> dict | None:
    k = meses.get(clave.strftime("%Y-%m"))
    if not k:
        return None
    venta = k["venta"]
    return {
        "venta": venta, "margen_pct": round(100 * k["margen"] / venta, 1) if venta else None,
        "clientes_que_compraron": k["clientes"], "tickets": k["tickets"], "ticket_promedio": k["ticket_promedio"],
        "compras_por_cliente": k["frecuencia"],
        "parte_ecommerce_pct": round(100 * k["venta_ecommerce"] / venta, 1) if venta else None,
        "parte_marca_propia_pct": round(100 * k["venta_marca_propia"] / venta, 1) if venta else None,
    }


async def numeros_del_informe(db: AsyncSession) -> dict | None:
    """Los números que lee Valentina. Solo agregados y hasta 10
    números de cliente (sin nombres: la base no los tiene)."""
    datos = await tablero(db)
    if not datos["ultimo_mes"]:
        return None
    ultimo = mes_de(datos["ultimo_mes"])
    meses = {k["mes"]: k for k in datos["meses"]}
    dims = datos["dimensiones"]

    def movimientos(lista: list[dict], n: int) -> dict:
        # Solo lo que pesa (1% de la venta o más): una categoría de $ 5.000 que
        # cae 99% no es noticia (pasó con AUTOLIQUIDABLES, 25/11/2026).
        total = sum(x["venta_3m"] for x in lista) or 1
        con = [x for x in lista if x["contra_3m_antes"] is not None and x["venta_3m"] > 0
               and max(x["venta_3m"], x["venta_3m_antes"]) >= 0.01 * total]
        con.sort(key=lambda x: x["contra_3m_antes"])
        return {"los_que_mas_bajan": con[:n], "los_que_mas_suben": list(reversed(con[-n:]))}

    c = VipCliente
    mirar = await db.execute(
        select(c.id_cliente, c.segmento, c.riesgo, c.venta_3m, c.venta_3m_antes, c.categoria, c.sucursal)
        .where(c.segmento.in_(["En riesgo", "Bajando"]))
        .order_by((c.venta_3m_antes - c.venta_3m).desc()).limit(10)
    )
    return {
        "ultimo_mes": nombre_mes(ultimo),
        "meses_cargados": f"{nombre_mes(mes_de(datos['meses'][0]['mes']))} a {nombre_mes(ultimo)}",
        "clientes_vip": datos["clientes"],
        "el_mes": _kpi(meses, ultimo),
        "el_mes_anterior": _kpi(meses, sumar_meses(ultimo, -1)),
        "el_mismo_mes_del_anio_anterior": _kpi(meses, sumar_meses(ultimo, -12)),
        "venta_por_mes": {k["mes"]: k["venta"] for k in datos["meses"][-13:]},
        "categorias_ultimos_3_meses": dims["categoria"][:10],
        "categorias_movimientos": movimientos(dims["categoria"], 3),
        "sucursales_movimientos": movimientos(dims["sucursal"], 3),
        "canales": dims["canal"],
        "segmentos": datos["segmentos"],
        "clientes_a_mirar": [
            {"cliente": f[0], "segmento": f[1], "riesgo": f[2], "venta_ultimos_3_meses": f[3],
             "venta_3_meses_antes": f[4], "compra_mas": f[5], "sucursal": f[6]}
            for f in mirar.all()
        ],
        "prediccion_de_valentina": datos["prediccion"],
    }


# ---------------------------------------------------------------------------
# Lo que necesita Valentina, que trabaja desde la nube del Escuadrón Lechuza
# ---------------------------------------------------------------------------
#
# Ivan (25/11/2026): "los agentes no deben de estar alojados dentro de nuestra
# plataforma… necesito que sean agentes reales… que cuestionen nuestras
# decisiones… que investiguen". La plataforma no escribe informes ni manda
# mails: guarda los datos, se los da a Valentina (con su propia cuenta y el
# permiso de Clientes VIP), guarda lo que ella aprende (su memoria: datos de
# clientes y del negocio, por eso acá y no en el repo público) y muestra lo
# que publica. Ella: .claude/agents/valentina-economista.md.

AGENTE_VIP = "valentina"
AMBITO_VIP = "clientes_vip"


def fila_memoria(m) -> dict:
    return {"id": m.id, "tema": m.tema, "texto": m.texto, "fuente": m.fuente, "activo": m.activo,
            "fecha": m.created_at.isoformat() if m.created_at else None,
            "actualizado": m.updated_at.isoformat() if m.updated_at else None}


async def memoria(db: AsyncSession, incluir_retiradas: bool = False) -> list[dict]:
    from app.models.agente_memoria import AgenteMemoria

    q = select(AgenteMemoria).where(AgenteMemoria.ambito == AMBITO_VIP)
    if not incluir_retiradas:
        q = q.where(AgenteMemoria.activo.is_(True))
    filas = await db.execute(q.order_by(AgenteMemoria.tema, AgenteMemoria.id))
    return [fila_memoria(m) for m in filas.scalars()]


async def publicar_informe(db: AsyncSession, mes: date, analisis: str, prediccion: dict, autor: str) -> VipInforme:
    """Guarda el informe que escribió Valentina (o quien sea del Escuadrón). Commitea."""
    informe = VipInforme(mes=mes, analisis=analisis, prediccion=prediccion or {}, con_ia=True, autor=autor)
    db.add(informe)
    await db.commit()
    await db.refresh(informe)
    return informe


COLUMNAS_CLIENTES_MES = ("id_cliente", "mes", "venta", "margen", "unidades", "tickets", "dias", "venta_ecommerce",
                         "venta_smart", "venta_marca_propia", "sucursal", "categorias")
COLUMNAS_DIMENSIONES = ("mes", "dimension", "valor", "venta", "margen", "unidades", "tickets", "clientes")
COLUMNAS_CLIENTES = ("id_cliente", "segmento", "riesgo", "venta_esperada", "venta_12m", "venta_3m", "venta_3m_antes",
                     "margen_12m", "tickets_12m", "meses_con_compra", "ultimo_mes", "sucursal", "categoria",
                     "parte_ecommerce")
TABLAS_CSV = {
    "clientes_mes": (VipClienteMes, COLUMNAS_CLIENTES_MES, (VipClienteMes.mes, VipClienteMes.id_cliente)),
    "dimensiones": (VipMesDimension, COLUMNAS_DIMENSIONES, (VipMesDimension.mes, VipMesDimension.dimension)),
    "clientes": (VipCliente, COLUMNAS_CLIENTES, (VipCliente.id_cliente,)),
}


def _celda(v) -> str:
    if v is None:
        return ""
    if isinstance(v, date):
        return v.strftime("%Y-%m") if v.day == 1 else v.isoformat()
    t = str(v)
    return '"' + t.replace('"', '""') + '"' if any(c in t for c in (";", '"', "\n")) else t


async def csv_de(db: AsyncSession, tabla: str):
    """Una tabla entera en CSV (separado por ;), de a pedazos para no llenar la memoria."""
    modelo, columnas, orden = TABLAS_CSV[tabla]
    salto = "\n"
    yield ";".join(columnas) + salto
    cols = [getattr(modelo, c) for c in columnas]
    resultado = await db.stream(select(*cols).order_by(*orden).execution_options(yield_per=5000))
    lote = []
    async for fila in resultado:
        lote.append(";".join(_celda(v) for v in fila))
        if len(lote) >= 5000:
            yield salto.join(lote) + salto
            lote = []
    if lote:
        yield salto.join(lote) + salto


def ahora() -> datetime:
    return datetime.now(timezone.utc)
