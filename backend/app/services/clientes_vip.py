"""Clientes VIP: el tablero, el análisis de Sofía y la predicción de Valentina.

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
3. **Informe** (`armar_informe`, en segundo plano después de cada carga):
   Valentina proyecta la venta del mes que viene (`prediccion_global`) y Sofía
   lee los números del mes y escribe qué pasó, qué mirar y qué haría
   (Claude, solo con los números agregados; sin IA, un texto con reglas). Se
   guarda y se manda por mail a quien tiene `clientes_vip.view`.

Los datos son confidenciales: en el mail van totales y hasta 10 números de
cliente, nunca el detalle.
"""
from __future__ import annotations

import asyncio
import html as _html
import json
import logging
import re
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
            "con_ia": i.con_ia, "enviado_a": i.enviado_a,
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
                "prediccion": None, "informe": None, "cargas": lista_cargas, "clientes": 0}
    segs = await segmentos(db)
    serie = await serie_mensual(db)
    informe = await db.scalar(select(VipInforme).order_by(VipInforme.id.desc()).limit(1))
    return {
        "ultimo_mes": ultimo.strftime("%Y-%m"),
        "meses": await kpis_por_mes(db),
        "dimensiones": await dimensiones(db, ultimo),
        "segmentos": segs,
        "prediccion": prediccion_global(serie, ultimo, sum(s["venta_esperada"] for s in segs)),
        "informe": fila_informe(informe),
        "cargas": lista_cargas,
        "clientes": sum(s["clientes"] for s in segs),
    }


# ---------------------------------------------------------------------------
# El informe: Sofía (análisis) y Valentina (predicción)
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
    """Los números que leen Sofía y Valentina. Solo agregados y hasta 10
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


SISTEMA = """Sos Sofía, analista del equipo de Core Tienda (Tienda Inglesa, Uruguay), y escribís junto con Valentina, que hace las predicciones. Te pasan los números de las compras de los clientes VIP (montos en pesos uruguayos sin IVA) y escribís el informe del mes para el equipo comercial.

Reglas:
- Castellano rioplatense, claro, como se lo contarías a un compañero. Frases cortas.
- Usá SOLO los números que te pasan; no inventes ni estimes otros. Montos redondeados ($ 280 millones, $ 1,2 millones, $ 45.000) y variaciones con un decimal.
- Nada de jerga estadística. "Segmento" se puede decir; explicá qué significa si hace falta.
- Formato Markdown, exactamente estas partes y en este orden:
### 📊 Cómo cerró <mes>
(3 a 5 viñetas: venta, margen, cuántos compraron, ticket promedio y frecuencia, contra el mes anterior y contra el mismo mes del año anterior si está)
### 🔎 Lo que hay que mirar
(3 a 5 viñetas: categorías, sucursales o canales que se movieron fuerte, y los clientes en riesgo con la plata que representan; podés nombrar hasta 3 números de cliente de "clientes_a_mirar")
### 🔮 Lo que viene, por Valentina
(2 o 3 frases: la venta esperada del mes que viene con su rango, contra qué se compara, y cuántos clientes podrían dejar de comprar)
### ✅ Qué haríamos
(2 o 3 acciones concretas para el equipo comercial, que salgan de los números)
- Hasta 2.200 caracteres en total. Sin tablas."""


def informe_con_reglas(n: dict) -> str:
    """El informe sin IA (no hay clave o la IA falló): los mismos números,
    con frases armadas."""
    def plata(v: float | None) -> str:
        if v is None:
            return "—"
        if abs(v) >= 1_000_000:
            return f"$ {v / 1_000_000:,.1f} millones".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"$ {v:,.0f}".replace(",", ".")

    def var(a: float | None, b: float | None) -> str:
        if not a or not b:
            return ""
        x = 100 * (a / b - 1)
        return f" ({'+' if x >= 0 else ''}{x:.1f}%)".replace(".", ",")

    m, ma, ly = n["el_mes"] or {}, n["el_mes_anterior"] or {}, n["el_mismo_mes_del_anio_anterior"] or {}
    lineas = [f"### 📊 Cómo cerró {n['ultimo_mes']}",
              f"- Venta: {plata(m.get('venta'))}{var(m.get('venta'), ma.get('venta'))} contra el mes anterior"
              + (f"; {var(m.get('venta'), ly.get('venta')).strip()} contra el año pasado." if ly else "."),
              f"- Margen: {str(m.get('margen_pct', '—')).replace('.', ',')}%.",
              f"- Compraron {m.get('clientes_que_compraron', 0):,} de {n['clientes_vip']:,} clientes VIP".replace(",", ".")
              + f", con un ticket promedio de {plata(m.get('ticket_promedio'))}.",
              "### 🔎 Lo que hay que mirar"]
    for cat in n["categorias_movimientos"]["los_que_mas_bajan"][:2]:
        lineas.append(f"- {cat['valor']}: {str(cat['contra_3m_antes']).replace('.', ',')}% en los últimos 3 meses.")
    riesgo = next((s for s in n["segmentos"] if s["segmento"] == "En riesgo"), None)
    if riesgo:
        lineas.append(f"- {riesgo['clientes']} clientes en riesgo: compraban {plata(riesgo['venta_3m_antes'])} "
                      f"en 3 meses y ahora {plata(riesgo['venta_3m'])}.")
    p = n["prediccion_de_valentina"] or {}
    if p.get("venta"):
        lineas += ["### 🔮 Lo que viene, por Valentina",
                   f"Para {nombre_mes(mes_de(p['mes']))} esperamos {plata(p['venta'])} "
                   f"(entre {plata(p['desde'])} y {plata(p['hasta'])}), según {p['como']}."]
    lineas += ["### ✅ Qué haríamos", "- Llamar o escribirles primero a los clientes en riesgo que más compraban."]
    return "\n".join(lineas)


MAX_TOKENS_INFORME = 16_000


async def escribir_analisis(numeros: dict) -> tuple[str, bool, object | None]:
    """El texto de Sofía y Valentina: (markdown, con_ia, usage)."""
    if not settings.ANTHROPIC_API_KEY:
        return informe_con_reglas(numeros), False, None
    from app.core.llm_retry import llm_call_with_retry
    from app.services.ia_cliente import cliente_anthropic

    try:
        cliente = cliente_anthropic()
        respuesta = await llm_call_with_retry(
            lambda: cliente.messages.create(
                model=settings.MODELO_IA,
                # Los modelos 5 piensan antes de escribir y ese razonamiento
                # cuenta dentro de max_tokens: con 2.000 el informe de octubre
                # 2026 salió cortado a la mitad (25/11/2026). Lugar de sobra y
                # esfuerzo medio: es redactar con números ya hechos.
                max_tokens=MAX_TOKENS_INFORME,
                output_config={"effort": "medium"},
                system=SISTEMA,
                messages=[{"role": "user", "content": json.dumps(numeros, ensure_ascii=False, default=str)}],
            ),
            label="clientes_vip_informe",
        )
        texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text").strip()
        # Cortado o rechazado no se guarda ni se manda: va el de reglas, entero.
        if respuesta.stop_reason != "end_turn" or not texto:
            raise ValueError(f"la respuesta no terminó bien ({respuesta.stop_reason})")
        return texto, True, respuesta.usage
    except Exception as exc:  # la IA no frena el informe
        logger.warning("clientes_vip: el informe va sin IA (%s)", exc)
        return informe_con_reglas(numeros), False, None


# ---------------------------------------------------------------------------
# El mail
# ---------------------------------------------------------------------------

def _en_linea(t: str) -> str:
    t = _html.escape(t, quote=False)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)


def markdown_a_html(md: str) -> str:
    partes, en_lista = [], False
    for linea in md.splitlines():
        s = linea.strip()
        if s.startswith(("- ", "* ")):
            if not en_lista:
                partes.append('<ul style="padding-left:20px;margin:6px 0 12px">')
                en_lista = True
            partes.append(f'<li style="margin:4px 0;line-height:1.5">{_en_linea(s[2:])}</li>')
            continue
        if en_lista:
            partes.append("</ul>")
            en_lista = False
        if s.startswith("#"):
            partes.append(f'<h3 style="font-size:17px;margin:22px 0 6px;color:#0f172a">{_en_linea(s.lstrip("#").strip())}</h3>')
        elif s:
            partes.append(f'<p style="margin:8px 0;line-height:1.5">{_en_linea(s)}</p>')
    if en_lista:
        partes.append("</ul>")
    return "\n".join(partes)


def armar_mail(informe: VipInforme, url: str) -> tuple[str, str, str]:
    """(asunto, html, texto) del informe del mes."""
    mes = nombre_mes(informe.mes)
    asunto = f"⭐ Clientes VIP · {mes}"
    cuerpo = markdown_a_html(informe.analisis)
    html = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f8fafc">'
        '<div style="max-width:620px;margin:0 auto;padding:24px 16px;font-family:-apple-system,Segoe UI,Roboto,'
        'Helvetica,Arial,sans-serif;font-size:15px;color:#1e293b">'
        f'<p style="margin:0 0 4px;font-size:13px;color:#64748b">Clientes VIP · {_html.escape(mes)}</p>'
        f"{cuerpo}"
        f'<p style="margin:24px 0 0"><a href="{_html.escape(url, quote=True)}" style="display:inline-block;'
        'background:#0f172a;color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:8px;font-size:14px">'
        "Ver el tablero</a></p>"
        '<p style="margin-top:28px;font-size:12px;color:#64748b;border-top:1px solid #e2e8f0;padding-top:10px">'
        "Sofía y Valentina, del Escuadrón Lechuza de Core Tienda. Te llega porque tenés acceso a Clientes VIP. "
        "La información es confidencial: no la reenvíes fuera de Tienda Inglesa.</p>"
        "</div></body></html>"
    )
    texto = f"{asunto}\n\n{informe.analisis}\n\nVer el tablero: {url}\n"
    return asunto, html, texto


def destinatario_real(email: str | None) -> bool:
    """Las cuentas internas y las de prueba no reciben mails."""
    e = (email or "").lower()
    return "@" in e and not e.endswith((".marketingtienda", "@example.com", ".invalid", ".local", ".test"))


async def destinatarios(db: AsyncSession) -> list[User]:
    from app.core.externos import puede_tener

    usuarios = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    return [u for u in usuarios if puede_tener(u, PERMISO_VER) and destinatario_real(u.email)]


def es_reciente(ultimo: date | None, hoy: date) -> bool:
    """Si los datos llegan hasta hace 3 meses o menos: solo entonces el informe
    sale por mail. Cargar un año viejo (2025, el 25/11/2026) rehace el informe
    pero no le manda a nadie un mail sobre diciembre del año pasado."""
    return bool(ultimo) and meses_entre(ultimo, date(hoy.year, hoy.month, 1)) <= 3


async def armar_informe(db: AsyncSession, carga_id: int | None, user_id: int | None, mandar: bool = True) -> VipInforme | None:
    """Escribe el informe del último mes, lo guarda y lo manda. Commitea."""
    from app.services import email_service
    from app.services.ai_usage_service import log_ai_usage

    numeros = await numeros_del_informe(db)
    if not numeros:
        return None
    texto, con_ia, usage = await escribir_analisis(numeros)
    if usage is not None:
        await log_ai_usage(db, user_id, "clientes_vip_informe", "anthropic", settings.MODELO_IA,
                           getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0)
    ultimo = await db.scalar(select(func.max(VipClienteMes.mes)))
    informe = VipInforme(carga_id=carga_id, mes=ultimo, analisis=texto,
                         prediccion=numeros["prediccion_de_valentina"] or {}, con_ia=con_ia)
    db.add(informe)
    await db.commit()

    if mandar and es_reciente(ultimo, ahora().date()) and email_service.email_configurado():
        url = f"{(settings.FRONTEND_URL or '').rstrip('/')}/clientes-vip"
        asunto, html, plano = armar_mail(informe, url)
        de = email_service.remitente_con_nombre("Sofía y Valentina")
        enviados = 0
        for u in await destinatarios(db):
            try:
                await email_service.send_email(u.email, asunto, html, plano, de=de)
                enviados += 1
            except Exception as exc:
                logger.warning("clientes_vip: no salió el mail a %s (%s)", u.id, exc)
            await asyncio.sleep(0.6)  # Resend gratis: 2 por segundo
        informe.enviado_a = enviados
        await db.commit()
    return informe


_TAREAS: set[asyncio.Task] = set()


def informe_en_segundo_plano(carga_id: int, user_id: int | None) -> None:
    """Después de una carga: el informe y los mails, sin hacer esperar a quien
    cargó (la IA tarda medio minuto)."""
    from app.core.database import AsyncSessionLocal

    async def correr() -> None:
        try:
            async with AsyncSessionLocal() as db:
                await armar_informe(db, carga_id, user_id)
        except Exception:
            logger.exception("clientes_vip: falló el informe de la carga %s", carga_id)

    tarea = asyncio.create_task(correr())
    _TAREAS.add(tarea)
    tarea.add_done_callback(_TAREAS.discard)


def ahora() -> datetime:
    return datetime.now(timezone.utc)
