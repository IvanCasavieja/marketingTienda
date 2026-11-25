"""Lo que Don Tino consulta además del calendario: el tablero de entregas y los
pedidos de Redexpres (25/11/2026).

Pedido de Ivan: "fijarse que Don Tino pueda manejar toda la app". Hasta acá
sabía del calendario (acciones, piezas, tareas, carga y avisos), pero no del
tablero, que es donde vive el trabajo con las agencias, ni de los pedidos de
los locales. Las dos son de SOLO LECTURA y con los permisos de quien pregunta:

- `tablero`: las mismas tarjetas que esa persona ve en su tablero (las mismas
  consultas de la pantalla, app/api/routes/entregas.py: `_filas_del_tablero`
  y `_tarjetas`), con en qué columna está cada una y a quién le toca. Sirve
  para "¿qué me toca revisar?", "¿cómo vienen los banners de Publicis?" o
  "¿qué está atrasado?".
- `pedidos_redexpres`: el estado de los pedidos del mes. Quien tiene la
  Planilla (redexpres.view) ve todos los locales; un local, solo el suyo.

Nada de esto cambia datos: crear, mover, aprobar o confirmar se hace en la
pantalla (Don Tino explica dónde).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select

from app.core import alcance, externos
from app.core.mundos import MUNDOS
from app.services import calendario_consultas as cc
from app.services import entregas as reglas
from app.services import sin_accion

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre",
         "noviembre", "diciembre")
PARA_MI = ("todas", "revisar", "entregar")


def _le_toca(e, tarjeta: dict) -> str:
    """En qué está, en una frase, como lo dice la pantalla."""
    hace = (tarjeta.get("hace") or {}).get("nombre") or "quien la hace"
    if tarjeta.get("cancelada"):
        return "cancelada (archivada sin terminar)"
    if e.momento == "aprobada":
        return "aprobada: no le toca a nadie"
    if e.momento == "revision":
        return f"revisar la ronda {e.ronda}: le toca a {tarjeta.get('turno') or 'alguien del equipo'}"
    if e.momento == "cambios":
        return f"corregir lo que se pidió en la ronda {e.ronda}: le toca a {hace}"
    if reglas.con_ok(e.momento, e.ronda):
        return f"entregar lo que falta (le dieron el OK a la ronda {e.ronda}): le toca a {hace}"
    return f"entregar: le toca a {hace}"


async def tablero(usuario, args: dict, db, hoy: date | None = None) -> str:
    from app.api.routes import entregas as rutas

    hoy = hoy or alcance.hoy_en_uruguay()
    try:
        mundos = cc.mundos_a_mirar(usuario, args.get("mundo"))
    except cc.ConsultaInvalida as exc:
        return cc._dump({"error": str(exc)})
    para_mi = args.get("para_mi") or "todas"
    if para_mi not in PARA_MI:
        return cc._dump({"error": f"para_mi tiene que ser una de: {', '.join(PARA_MI)}"})
    columna = args.get("columna")
    if columna and columna not in reglas.COLUMNAS:
        return cc._dump({"error": f"La columna tiene que ser una de: {', '.join(reglas.COLUMNAS)}"})
    con_archivadas = bool(args.get("incluir_archivadas")) or columna == "archivado"
    texto = (args.get("texto") or "").strip()
    quien = (args.get("la_hace") or "").strip()

    elegidas: list[dict] = []
    por_columna: dict[str, int] = {}
    for m in mundos:
        filas = await rutas._filas_del_tablero(db, usuario, m)
        tarjetas = await rutas._tarjetas(db, filas, usuario, hoy)
        for (e, t, b), tj in zip(filas, tarjetas):
            col = tj["columna"]
            if col == "archivado" and not con_archivadas:
                continue
            if columna and col != columna:
                continue
            if para_mi == "revisar" and not (e.momento == "revision" and e.aprobador_de_turno_id == usuario.id):
                continue
            if para_mi == "entregar" and not (tj.get("puedo") or {}).get("entregar"):
                continue
            hace = (tj.get("hace") or {}).get("nombre") or ""
            nombre_accion = sin_accion.NOMBRE if sin_accion.es_sin_accion(b.id) else b.nombre
            if quien and not cc.coincide(quien, hace):
                continue
            if texto and not cc.coincide(texto, t.titulo, nombre_accion):
                continue
            por_columna[col] = por_columna.get(col, 0) + 1
            vencida = (t.vence is not None and t.vence < hoy and col not in ("finalizado", "archivado"))
            item: dict[str, Any] = {
                "titulo": cc.corto(t.titulo, 160),
                "accion": cc.corto(nombre_accion, 120),
                "mundo": MUNDOS.get(b.mundo, b.mundo),
                "columna": reglas.NOMBRES_DE_COLUMNA.get(col, col),
                "la_hace": hace or None,
                "le_toca": _le_toca(e, tj),
                "ronda": e.ronda or None,
                "vence": cc._iso(t.vence),
                "vencida": True if vencida else None,
                "link": f"/entregas?tarea={t.id}",
            }
            elegidas.append({k: v for k, v in item.items() if v is not None})

    elegidas.sort(key=lambda x: (x.get("vence") or "9999-12-31", x["titulo"]))
    datos: dict[str, Any] = {
        "mundos": [MUNDOS.get(m, m) for m in mundos],
        "hoy": hoy.isoformat(),
        "total": len(elegidas),
        "por_columna": {reglas.NOMBRES_DE_COLUMNA.get(k, k): v for k, v in por_columna.items()},
    }
    if not con_archivadas:
        datos["sin_archivadas"] = "No incluye lo archivado (pedilo con incluir_archivadas)."
    if externos.es_externo(usuario):
        datos["solo_las_suyas"] = "Una agencia ve solo sus tarjetas."
    cc.con_tope(datos, "tarjetas", elegidas)
    return cc.a_json(datos, ("tarjetas",))


def _mes_pedido(args: dict, hoy: date) -> tuple[int, int] | str:
    anio = args.get("anio") or hoy.year
    mes = args.get("mes") or hoy.month
    try:
        anio, mes = int(anio), int(mes)
    except (TypeError, ValueError):
        return "El año y el mes van como números (mes del 1 al 12)."
    if not (1 <= mes <= 12) or not (2020 <= anio <= 2100):
        return "El año y el mes van como números (mes del 1 al 12)."
    return anio, mes


def puede_ver_la_planilla(usuario) -> bool:
    return bool(getattr(usuario, "is_superuser", False)) or bool(
        {"redexpres.view", "redexpres.manage"} & set(getattr(usuario, "permissions", None) or [])
    )


async def pedidos_redexpres(usuario, args: dict, db, hoy: date | None = None) -> str:
    from app.api.routes.redexpres import LOCALES
    from app.models.local_asignacion import LocalAsignacion
    from app.models.planilla_pedido import PlanillaPedido

    hoy = hoy or alcance.hoy_en_uruguay()
    pedido = _mes_pedido(args, hoy)
    if isinstance(pedido, str):
        return cc._dump({"error": pedido})
    anio, mes = pedido
    nombre_mes = f"{MESES[mes - 1]} {anio}"

    toda_la_planilla = puede_ver_la_planilla(usuario)
    if toda_la_planilla:
        locales = list(LOCALES)
    else:
        locales = list((await db.execute(
            select(LocalAsignacion.local_nombre).where(LocalAsignacion.user_id == usuario.id)
        )).scalars())
        if not locales:
            return cc._dump({"error": "Esta persona no tiene la Planilla de pedidos ni un local de Redexpres "
                                      "asignado: no le cuentes nada de los pedidos."})

    filas = {f.local_nombre: f for f in (await db.execute(
        select(PlanillaPedido).where(PlanillaPedido.year == anio, PlanillaPedido.month == mes,
                                     PlanillaPedido.local_nombre.in_(locales))
    )).scalars()}
    if not filas:
        return cc._dump({"mes": nombre_mes, "abierto": False,
                         "mensaje": f"El pedido de {nombre_mes} todavía no está abierto: lo abre marketing desde "
                                    "la Planilla de pedidos."})

    texto = (args.get("local") or "").strip()
    elegidos = [loc for loc in locales if loc in filas and (not texto or cc.coincide(texto, loc))]
    confirmados = [loc for loc in elegidos if filas[loc].confirmado]
    sin_confirmar = [loc for loc in elegidos if not filas[loc].confirmado]
    datos: dict[str, Any] = {
        "mes": nombre_mes, "abierto": True,
        "locales": len(elegidos), "confirmados": len(confirmados), "sin_confirmar": len(sin_confirmar),
        "link": "/redexpres/planilla" if toda_la_planilla else "/redexpres/mi-pedido",
    }
    if not toda_la_planilla:
        datos["solo_el_suyo"] = "Es un local: ve solo su pedido."
    cc.con_tope(datos, "locales_sin_confirmar", sin_confirmar, 80)
    if len(elegidos) <= 10:
        datos["detalle"] = [
            {"local": loc, "confirmado": bool(filas[loc].confirmado),
             **({"confirmado_el": filas[loc].confirmed_at.date().isoformat()}
                if filas[loc].confirmado and filas[loc].confirmed_at else {})}
            for loc in elegidos
        ]
    return cc.a_json(datos, ("locales_sin_confirmar", "detalle"))


HERRAMIENTAS = {
    "tablero_tarjetas": tablero,
    "redexpres_pedidos": pedidos_redexpres,
}


async def ejecutar(nombre: str, args: dict, usuario, db) -> str:
    funcion = HERRAMIENTAS.get(nombre)
    if funcion is None:
        return cc._dump({"error": f"Herramienta desconocida: {nombre}"})
    return await funcion(usuario, args or {}, db)
