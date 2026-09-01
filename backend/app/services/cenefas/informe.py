"""Informe de produccion de cenefas.

Responde una pregunta concreta: cuantas cenefas se hicieron, cuantas salieron
correctas, y cuanto vale eso. Cada cenefa disenada tiene un costo (49 pesos
por defecto, configurable desde la pantalla) y ese es el criterio con el que
se valoriza el trabajo.

Cada corrida cuenta por separado, aunque sea el mismo listado reprocesado: es
trabajo pedido a la herramienta y se paga igual.

Solo entran los jobs CONFIRMADOS (status "done"). Un job en "preview" es una
previsualizacion que nadie confirmo, y uno en "error" no produjo nada.

De donde salen los numeros
--------------------------
Del `validation_report.summary` que el propio motor dejo al validar, no de un
recuento hecho ahora: es lo que se vio en pantalla en su momento, y eso es lo
que hay que poder demostrar.

    total            cenefas de esa corrida
    correct          las que no tienen ningun problema
    with_warnings    salieron, pero con algo para revisar (ej. descripcion larga)
    critical_errors  no se pudieron armar (ej. sin precio)

Los jobs viejos que no tienen summary caen a row_count / error_count, que son
columnas propias de la tabla y existen desde el principio.

Que se valoriza y que no
------------------------
No todo lo que paso por el motor es trabajo facturable, asi que el informe
separa en tres y solo el primero lleva plata:

    cobrable        mundos marcados `cobrable` (Rompe Precios, Parrilla y
                    Vinos, Mega Rompe Precios).
    sin costo       mundos con `cobrable=false`: Redexpres y el mundo de
                    pruebas. Se muestran con su volumen, valorizados en 0.
    sin clasificar  corridas sin `categoria` -- las de junio al 23/08, de antes
                    de que el job guardara el mundo. NO se valorizan: no se
                    sabe cuales fueron trabajo real y cuales pruebas o
                    reproceso, y valorizarlas es lo que inflaba el total.

Aparte va la produccion DECLARADA (`cenefa_destinos.cenefas_previas`): lo que
se hizo antes de que hubiera registro y solo se puede afirmar, no demostrar.
Suma al total cobrable pero viaja en su propio renglon y etiquetada, para que
se vea de un lado lo respaldado corrida por corrida y del otro lo declarado.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Integer, func, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cenefa_destino import CenefaDestino
from app.models.cenefa_job import CenefaJob

# Costo por cenefa disenada, en pesos. Es solo el valor por defecto: la
# pantalla lo deja cambiar y el numero viaja en cada consulta, para que
# actualizarlo no dependa de un deploy.
COSTO_POR_CENEFA = 49.0


def _num(campo: str):
    """Un entero del summary del reporte, o NULL si ese job no lo tiene."""
    return (
        CenefaJob.validation_report[("summary", campo)]
        .astext.cast(Integer)
    )


def _metricas():
    """Las cuatro cifras de un job, con respaldo para los jobs viejos.

    Los primeros jobs no guardaban `validation_report.summary`; para esos se
    usan row_count y error_count, que son columnas de la tabla y estan desde
    el principio. Sin este respaldo, junio y julio aparecerian en cero.
    """
    total = func.coalesce(_num("total"), CenefaJob.row_count, 0)
    criticos = func.coalesce(_num("critical_errors"), CenefaJob.error_count, 0)
    correctas = func.coalesce(_num("correct"), CenefaJob.row_count - CenefaJob.error_count, 0)
    avisos = func.coalesce(_num("with_warnings"), 0)
    return total, correctas, avisos, criticos


def _filtros(desde: date | None, hasta: date | None, template: str | None):
    cond = [CenefaJob.status == "done"]
    if desde:
        cond.append(CenefaJob.created_at >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        cond.append(CenefaJob.created_at < datetime.combine(hasta, datetime.max.time()))
    if template:
        cond.append(CenefaJob.template_nombre == template)
    return cond


async def _reales_por_categoria(db: AsyncSession, cond: list) -> dict[str, int]:
    """Cenefas reales por mundo: filas del listado x formatos distintos pedidos,
    sin contar de nuevo el reproceso.

    La corrida no es la unidad de trabajo -- el listado si. Un mismo Excel se
    reprocesa hasta que sale bien (Carniceria necesito 4 salidas y tuvo 25
    intentos en agosto), y el informe bruto paga cada intento por separado.
    Aca se agrupa por listado -- `excel_nombre` + `row_count`, NO solo el
    nombre: "convertidor_cenefas.xlsx" es el nombre generico que deja el
    Convertidor y se repite para listados distintos, lo unico que los separa
    es cuantas filas trae cada uno -- y dentro de cada listado se cuentan las
    plantillas (=formatos) distintas que efectivamente se generaron.
    Confirmado con Ivan el 2026-08-31 sobre Mega Rompe Precios.

    No usa la agrupacion de `agrupar_intentos` (excel + plantilla) porque esa
    clave puede juntar dos listados reales distintos que por casualidad usaron
    el mismo nombre generico Y la misma plantilla en fechas distintas, y se
    quedaria solo con el ultimo, perdiendo el otro. Por eso `row_count` entra
    en la clave.

    Solo cubre corridas con `excel_nombre` guardado (desde el 23/08/2026): las
    anteriores ya quedan afuera de lo cobrable por "sin clasificar", asi que
    no hace falta un respaldo para esas.
    """
    sub = (
        select(
            CenefaJob.categoria,
            CenefaJob.excel_nombre,
            CenefaJob.row_count,
            func.count(func.distinct(CenefaJob.template_nombre)).label("n_formatos"),
        )
        .where(*cond, CenefaJob.excel_nombre.isnot(None), CenefaJob.row_count.isnot(None))
        .group_by(CenefaJob.categoria, CenefaJob.excel_nombre, CenefaJob.row_count)
    ).subquery()

    filas = (await db.execute(
        select(
            sub.c.categoria,
            func.coalesce(func.sum(sub.c.row_count * sub.c.n_formatos), 0).label("reales"),
        ).group_by(sub.c.categoria)
    )).all()
    return {(r.categoria or ""): int(r.reales) for r in filas}


async def resumen(
    db: AsyncSession,
    desde: date | None = None,
    hasta: date | None = None,
    template: str | None = None,
    costo: float = COSTO_POR_CENEFA,
) -> dict[str, Any]:
    """Totales, apertura por mes y por plantilla."""
    total, correctas, avisos, criticos = _metricas()
    cond = _filtros(desde, hasta, template)

    # Lo verificado a mano se suma aparte: es la cifra que se puede defender
    # sin depender de que la validacion automatica no haya visto un problema.
    verif_corridas = func.count().filter(CenefaJob.verificado.is_(True))
    verif_cenefas = func.coalesce(
        func.sum(total).filter(CenefaJob.verificado.is_(True)), 0)

    fila = (await db.execute(
        select(
            func.count().label("corridas"),
            func.coalesce(func.sum(total), 0).label("cenefas"),
            func.coalesce(func.sum(correctas), 0).label("correctas"),
            func.coalesce(func.sum(avisos), 0).label("avisos"),
            func.coalesce(func.sum(criticos), 0).label("criticos"),
            verif_corridas.label("verif_corridas"),
            verif_cenefas.label("verif_cenefas"),
            func.min(CenefaJob.created_at).label("desde"),
            func.max(CenefaJob.created_at).label("hasta"),
        ).where(*cond)
    )).one()

    mes = func.to_char(func.date_trunc("month", CenefaJob.created_at), "YYYY-MM")
    por_mes = (await db.execute(
        select(
            mes.label("mes"),
            func.count().label("corridas"),
            func.coalesce(func.sum(total), 0).label("cenefas"),
            func.coalesce(func.sum(correctas), 0).label("correctas"),
            func.coalesce(func.sum(avisos), 0).label("avisos"),
            func.coalesce(func.sum(criticos), 0).label("criticos"),
            verif_corridas.label("verif_corridas"),
            verif_cenefas.label("verif_cenefas"),
        ).where(*cond).group_by(mes).order_by(mes)
    )).all()

    por_plantilla = (await db.execute(
        select(
            func.coalesce(CenefaJob.template_nombre, "").label("plantilla"),
            func.count().label("corridas"),
            func.coalesce(func.sum(total), 0).label("cenefas"),
            func.coalesce(func.sum(correctas), 0).label("correctas"),
            verif_corridas.label("verif_corridas"),
            verif_cenefas.label("verif_cenefas"),
        )
        .where(*cond)
        .group_by(CenefaJob.template_nombre)
        .order_by(func.coalesce(func.sum(total), 0).desc())
    )).all()

    # Apertura por mundo. El mundo se lee de la columna del job y NO de la
    # plantilla: la plantilla puede haberse borrado (FK ON DELETE SET NULL) y
    # ahi se perdia la atribucion. Un mundo borrado deja corridas con categoria
    # pero sin fila en cenefa_destinos: se asume cobrable, que es el default, y
    # se muestra con su slug como nombre.
    por_mundo = (await db.execute(
        select(
            func.coalesce(CenefaJob.categoria, "").label("mundo"),
            func.coalesce(CenefaDestino.nombre, "").label("nombre"),
            func.coalesce(CenefaDestino.cobrable, true()).label("cobrable"),
            func.count().label("corridas"),
            func.coalesce(func.sum(total), 0).label("cenefas"),
            func.coalesce(func.sum(correctas), 0).label("correctas"),
            func.coalesce(func.sum(avisos), 0).label("avisos"),
            func.coalesce(func.sum(criticos), 0).label("criticos"),
            verif_corridas.label("verif_corridas"),
            verif_cenefas.label("verif_cenefas"),
        )
        .select_from(CenefaJob)
        .outerjoin(CenefaDestino, CenefaDestino.slug == CenefaJob.categoria)
        .where(*cond)
        .group_by(CenefaJob.categoria, CenefaDestino.nombre, CenefaDestino.cobrable)
        .order_by(func.coalesce(func.sum(total), 0).desc())
    )).all()

    reales_por_categoria = await _reales_por_categoria(db, cond)

    # Produccion declarada: una cifra fija por mundo, sin corridas detras. Solo
    # se incluye en la vista sin filtros -- acotada a un mes o a una plantilla
    # no significa nada, porque no tiene fecha ni plantilla que filtrar.
    sin_filtros = desde is None and hasta is None and not template
    declaradas = (await db.execute(
        select(
            CenefaDestino.slug, CenefaDestino.nombre, CenefaDestino.cobrable,
            CenefaDestino.cenefas_previas, CenefaDestino.cenefas_previas_nota,
        )
        .where(CenefaDestino.cenefas_previas > 0)
        .order_by(CenefaDestino.orden, CenefaDestino.slug)
    )).all() if sin_filtros else []

    _CAMPOS = ("corridas", "cenefas", "correctas", "avisos", "criticos",
               "verif_corridas", "verif_cenefas")

    def cifras(r) -> dict[str, int]:
        """Los numeros de una fila, con 0 para lo que esa consulta no trajo."""
        if isinstance(r, dict):
            return r
        return {k: (getattr(r, k, 0) or 0) for k in _CAMPOS}

    def bloque(r, valorizar: bool = True, reales: int | None = None) -> dict[str, Any]:
        """Un bloque de cifras. `valorizar=False` lo deja en cero pesos sin
        esconder el volumen: es lo que se hace con los mundos sin costo y con
        lo que no se puede atribuir.

        `reales` es lo que efectivamente hacia falta -- filas del listado x
        formatos distintos, sin contar de nuevo el reproceso. Se pasa aparte
        en vez de salir de `c` porque no es una columna mas: sale de agrupar
        por listado, no de sumar filas."""
        c = cifras(r)
        d = {
            "corridas":  c["corridas"],
            "cenefas":   c["cenefas"],
            "correctas": c["correctas"],
            "avisos":    c["avisos"],
            "criticos":  c["criticos"],
            "verificadas_corridas": c["verif_corridas"],
            "verificadas":          c["verif_cenefas"],
            "costo":             round(c["cenefas"] * costo, 2) if valorizar else 0.0,
            "costo_correctas":   round(c["correctas"] * costo, 2) if valorizar else 0.0,
            "costo_verificadas": round(c["verif_cenefas"] * costo, 2) if valorizar else 0.0,
        }
        if reales is not None:
            d["cenefas_reales"] = reales
            d["costo_real"] = round(reales * costo, 2) if valorizar else 0.0
        return d

    def sumar(filas) -> dict[str, int]:
        return {k: sum(cifras(r)[k] for r in filas) for k in _CAMPOS}

    # Tres grupos excluyentes. "Sin clasificar" es categoria NULL: las corridas
    # anteriores a que el job guardara el mundo.
    g_cobrable  = [r for r in por_mundo if r.mundo and r.cobrable]
    g_sin_costo = [r for r in por_mundo if r.mundo and not r.cobrable]
    g_sin_clas  = [r for r in por_mundo if not r.mundo]

    medido_cobrable    = sumar(g_cobrable)
    declarado_cobrable = sum(r.cenefas_previas for r in declaradas if r.cobrable)
    cenefas_cobrables  = medido_cobrable["cenefas"] + declarado_cobrable

    # Lo declarado ya es una cifra real (no tiene corridas ni reproceso
    # detras), asi que se suma directo -- lo unico que hay que desagregar del
    # reproceso es lo medido.
    reales_cobrable        = sum(reales_por_categoria.get(r.mundo, 0) for r in g_cobrable)
    cenefas_reales_cobrable = reales_cobrable + declarado_cobrable

    return {
        "costo_unitario": costo,
        # `total` sigue siendo TODO lo medido, valorizado como siempre: es la
        # cifra bruta, la que responde "cuanto paso por el motor".
        "total": {
            **bloque(fila),
            "desde": fila.desde.isoformat() if fila.desde else None,
            "hasta": fila.hasta.isoformat() if fila.hasta else None,
        },
        "por_mes": [{"mes": r.mes, **bloque(r)} for r in por_mes],
        "por_plantilla": [
            # Hasta el 23/08/2026 no se guardaba el nombre de la plantilla en el
            # job, asi que la mitad del historial no puede atribuirse. Se muestra
            # como un grupo aparte en vez de esconderlo.
            {"plantilla": r.plantilla or "(sin registrar)", **bloque(r)}
            for r in por_plantilla
        ],
        "por_mundo": [
            {
                "mundo":    r.mundo or "",
                "nombre":   r.nombre or r.mundo or "(sin clasificar)",
                "cobrable": bool(r.mundo) and bool(r.cobrable),
                **bloque(r, valorizar=bool(r.mundo) and bool(r.cobrable),
                         reales=reales_por_categoria.get(r.mundo or "")),
            }
            for r in por_mundo
        ],
        "declaradas": [
            {
                "mundo":    r.slug,
                "nombre":   r.nombre,
                "cobrable": bool(r.cobrable),
                "cenefas":  r.cenefas_previas,
                "nota":     r.cenefas_previas_nota,
                "costo":    round(r.cenefas_previas * costo, 2) if r.cobrable else 0.0,
            }
            for r in declaradas
        ],
        # Lo que de verdad se factura: mundos cobrables, medido + declarado.
        "cobrable": {
            **bloque(medido_cobrable, reales=reales_cobrable),
            "declaradas":      declarado_cobrable,
            "cenefas_totales": cenefas_cobrables,
            "costo_total":     round(cenefas_cobrables * costo, 2),
            # Lo que hacia falta de verdad -- listado x formatos distintos,
            # sin pagar de nuevo el reproceso. Medido con esa regla + lo
            # declarado (que ya es real, no tiene corridas detras).
            "cenefas_reales_totales": cenefas_reales_cobrable,
            "costo_real_total":       round(cenefas_reales_cobrable * costo, 2),
        },
        "sin_costo":      bloque(sumar(g_sin_costo), valorizar=False),
        "sin_clasificar": bloque(sumar(g_sin_clas),  valorizar=False),
    }


async def detalle(
    db: AsyncSession,
    desde: date | None = None,
    hasta: date | None = None,
    template: str | None = None,
    costo: float = COSTO_POR_CENEFA,
    limite: int = 500,
) -> list[dict[str, Any]]:
    """Una fila por corrida, de la mas nueva a la mas vieja."""
    total, correctas, avisos, criticos = _metricas()
    filas = (await db.execute(
        select(
            CenefaJob.id, CenefaJob.created_at, CenefaJob.completed_at,
            CenefaJob.format, CenefaJob.template_nombre, CenefaJob.excel_nombre,
            CenefaJob.created_by,
            CenefaJob.verificado, CenefaJob.verificado_at,
            total.label("cenefas"), correctas.label("correctas"),
            avisos.label("avisos"), criticos.label("criticos"),
        )
        .where(*_filtros(desde, hasta, template))
        .order_by(CenefaJob.created_at.desc())
        .limit(limite)
    )).all()

    return [
        {
            "id":        str(r.id),
            "fecha":     r.created_at.isoformat() if r.created_at else None,
            "formato":   r.format,
            "plantilla": r.template_nombre or "(sin registrar)",
            "excel":     r.excel_nombre or "(sin registrar)",
            "usuario_id": r.created_by,
            "cenefas":   r.cenefas or 0,
            "correctas": r.correctas or 0,
            "avisos":    r.avisos or 0,
            "criticos":  r.criticos or 0,
            "verificado": bool(r.verificado),
            "verificado_at": r.verificado_at.isoformat() if r.verificado_at else None,
            "costo":     round((r.cenefas or 0) * costo, 2),
        }
        for r in filas
    ]


async def plantillas_del_historial(db: AsyncSession) -> list[str]:
    """Nombres de plantilla que aparecen en el historial, para el filtro."""
    filas = (await db.execute(
        select(CenefaJob.template_nombre)
        .where(CenefaJob.status == "done", CenefaJob.template_nombre.isnot(None))
        .distinct()
        .order_by(CenefaJob.template_nombre)
    )).scalars().all()
    return list(filas)


# ---------------------------------------------------------------------------
# Excel del informe
# ---------------------------------------------------------------------------

def a_excel(resumen_: dict[str, Any], filas: list[dict[str, Any]]) -> bytes:
    """El informe en Excel: una hoja de resumen y otra con el detalle.

    El resumen es lo que se muestra o se imprime; el detalle esta para poder
    respaldar cualquier cifra del resumen corrida por corrida, que es de lo
    que se trata poder demostrar lo que se hizo.
    """
    import io

    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    costo = resumen_["costo_unitario"]
    wb = openpyxl.Workbook()

    titulo_font = Font(bold=True, size=14)
    head_fill = PatternFill("solid", fgColor="1E3A5F")
    head_font = Font(bold=True, color="FFFFFF", size=11)
    dinero = '#,##0'

    def encabezar(ws, fila, nombres):
        for c, n in enumerate(nombres, 1):
            cell = ws.cell(row=fila, column=c, value=n)
            cell.fill, cell.font = head_fill, head_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

    # ── Resumen ────────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Resumen"
    ws["A1"] = "Informe de produccion de cenefas"
    ws["A1"].font = titulo_font
    t = resumen_["total"]
    periodo = f'{(t["desde"] or "")[:10]} a {(t["hasta"] or "")[:10]}' if t["desde"] else "sin datos"
    ws["A2"] = f'Periodo: {periodo}    Costo por cenefa: ${costo:g}'

    ws["A4"] = "Total"
    ws["A4"].font = Font(bold=True)
    encabezar(ws, 5, ["Corridas", "Cenefas", "Correctas", "Con avisos",
                      "No se pudieron armar", "Valor total",
                      "Corridas verificadas", "Cenefas verificadas", "Valor verificado"])
    ws.cell(row=6, column=1, value=t["corridas"])
    ws.cell(row=6, column=2, value=t["cenefas"])
    ws.cell(row=6, column=3, value=t["correctas"])
    ws.cell(row=6, column=4, value=t["avisos"])
    ws.cell(row=6, column=5, value=t["criticos"])
    ws.cell(row=6, column=6, value=t["costo"]).number_format = dinero
    ws.cell(row=6, column=7, value=t["verificadas_corridas"])
    ws.cell(row=6, column=8, value=t["verificadas"])
    ws.cell(row=6, column=9, value=t["costo_verificadas"]).number_format = dinero

    # ── Que se factura y que no ────────────────────────────────────────────
    # El "Total" de arriba es la cifra bruta: todo lo que paso por el motor.
    # Este bloque es el que se puede presentar, porque separa el trabajo
    # cobrable de los mundos sin costo y de lo que no se puede atribuir.
    cob = resumen_.get("cobrable") or {}
    sinc = resumen_.get("sin_costo") or {}
    sincl = resumen_.get("sin_clasificar") or {}
    declaradas = resumen_.get("declaradas") or []

    ws["A8"] = "Que se factura"
    ws["A8"].font = Font(bold=True)
    encabezar(ws, 9, ["Concepto", "Corridas", "Cenefas", "Valor", "Detalle"])
    fila = 10
    presentacion = [
        ("Cobrable (medido)", cob.get("corridas", 0), cob.get("cenefas", 0),
         cob.get("costo", 0), "Mundos cobrables, respaldado corrida por corrida"),
    ]
    for d in declaradas:
        presentacion.append((
            f'Declarado - {d["nombre"]}', 0, d["cenefas"], d["costo"], d["nota"],
        ))
    presentacion += [
        ("COBRABLE TOTAL", cob.get("corridas", 0), cob.get("cenefas_totales", 0),
         cob.get("costo_total", 0), "Medido + declarado"),
        ("Sin costo", sinc.get("corridas", 0), sinc.get("cenefas", 0), 0,
         "Mundos marcados sin costo (Redexpres, pruebas)"),
        ("Sin clasificar", sincl.get("corridas", 0), sincl.get("cenefas", 0), 0,
         "Corridas anteriores a que el job guardara el mundo; no se valorizan"),
    ]
    for concepto, corridas_, cenefas_, valor_, detalle_ in presentacion:
        ws.cell(row=fila, column=1, value=concepto)
        if concepto == "COBRABLE TOTAL":
            ws.cell(row=fila, column=1).font = Font(bold=True)
        ws.cell(row=fila, column=2, value=corridas_ or None)
        ws.cell(row=fila, column=3, value=cenefas_)
        ws.cell(row=fila, column=4, value=valor_).number_format = dinero
        ws.cell(row=fila, column=5, value=detalle_)
        fila += 1

    fila += 2
    for titulo, clave, etiqueta in (("Por mundo", "por_mundo", "nombre"),
                                    ("Por mes", "por_mes", "mes"),
                                    ("Por plantilla", "por_plantilla", "plantilla")):
        ws.cell(row=fila, column=1, value=titulo).font = Font(bold=True)
        rotulo = "Mundo" if clave == "por_mundo" else etiqueta.capitalize()
        encabezar(ws, fila + 1, [rotulo, "Corridas", "Cenefas",
                                 "Correctas", "Valor"])
        fila += 2
        for r in resumen_[clave]:
            ws.cell(row=fila, column=1, value=r[etiqueta])
            ws.cell(row=fila, column=2, value=r["corridas"])
            ws.cell(row=fila, column=3, value=r["cenefas"])
            ws.cell(row=fila, column=4, value=r["correctas"])
            ws.cell(row=fila, column=5, value=r["costo"]).number_format = dinero
            fila += 1
        fila += 2

    for col, ancho in zip("ABCDEFGHI", (34, 12, 12, 12, 20, 16, 20, 20, 18)):
        ws.column_dimensions[col].width = ancho

    # ── Detalle ────────────────────────────────────────────────────────────
    ws2 = wb.create_sheet("Detalle")
    cols = ["Fecha", "Plantilla", "Excel", "Formato", "Cenefas", "Correctas",
            "Con avisos", "No se pudieron armar", "Valor", "Verificada"]
    encabezar(ws2, 1, cols)
    for i, r in enumerate(filas, 2):
        ws2.cell(row=i, column=1, value=(r["fecha"] or "")[:16].replace("T", " "))
        ws2.cell(row=i, column=2, value=r["plantilla"])
        ws2.cell(row=i, column=3, value=r["excel"])
        ws2.cell(row=i, column=4, value=r["formato"])
        ws2.cell(row=i, column=5, value=r["cenefas"])
        ws2.cell(row=i, column=6, value=r["correctas"])
        ws2.cell(row=i, column=7, value=r["avisos"])
        ws2.cell(row=i, column=8, value=r["criticos"])
        ws2.cell(row=i, column=9, value=r["costo"]).number_format = dinero
        ws2.cell(row=i, column=10, value="si" if r["verificado"] else "")
    for c, ancho in enumerate((17, 34, 34, 10, 10, 10, 12, 21, 14, 12), 1):
        ws2.column_dimensions[get_column_letter(c)].width = ancho
    ws2.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Historial de intentos
# ---------------------------------------------------------------------------

def agrupar_intentos(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa las corridas por listado, para ver cuantos intentos llevo cada uno.

    Un mismo listado se reprocesa varias veces: se genera, se ve algo mal, se
    arregla y se vuelve a generar. En la lista plana eso son N corridas sueltas
    y no se entiende nada; agrupadas se lee de una que "este listado llevo 9
    intentos y el ultimo salio limpio".

    La clave es el Excel + la plantilla. Las corridas anteriores al 23/08/2026
    no guardaron esos nombres, asi que para esas se agrupa por formato y
    cantidad de carteles, que es lo unico que las distingue.

    Dentro de cada grupo los intentos van del mas viejo al mas nuevo, que es
    como se leen: el ultimo es el que quedo.
    """
    grupos: dict[tuple[str, str], dict[str, Any]] = {}
    for f in filas:
        excel = f["excel"] if f["excel"] != "(sin registrar)" else f'{f["cenefas"]} carteles'
        plantilla = f["plantilla"] if f["plantilla"] != "(sin registrar)" else (f["formato"] or "?")
        g = grupos.setdefault((excel, plantilla), {
            "excel": excel, "plantilla": plantilla,
            "sin_registrar": f["excel"] == "(sin registrar)",
            "intentos": [],
        })
        g["intentos"].append(f)

    salida = []
    for g in grupos.values():
        # Del mas viejo al mas nuevo: el ultimo es el que quedo.
        g["intentos"].sort(key=lambda x: x["fecha"] or "")
        ultimo = g["intentos"][-1]
        salida.append({
            "excel": g["excel"],
            "plantilla": g["plantilla"],
            "sin_registrar": g["sin_registrar"],
            "intentos": len(g["intentos"]),
            "primera": g["intentos"][0]["fecha"],
            "ultima": ultimo["fecha"],
            # Lo que vale es el ultimo intento: los anteriores se descartaron.
            "cenefas": ultimo["cenefas"],
            "correctas": ultimo["correctas"],
            "criticos": ultimo["criticos"],
            "verificado": ultimo["verificado"],
            "costo": ultimo["costo"],
            "detalle": g["intentos"],
        })
    # Primero los que mas intentos llevaron: son los que hay que mirar.
    salida.sort(key=lambda x: (-x["intentos"], x["ultima"] or ""), reverse=False)
    return salida
