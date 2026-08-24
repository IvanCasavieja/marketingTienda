"""Informe de produccion de cenefas.

Responde una pregunta concreta: cuantas cenefas se hicieron, cuantas salieron
correctas, y cuanto vale eso. Cada cenefa disenada tiene un costo (45 pesos
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
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cenefa_job import CenefaJob

# Costo por cenefa disenada, en pesos. Es solo el valor por defecto: la
# pantalla lo deja cambiar y el numero viaja en cada consulta, para que
# actualizarlo no dependa de un deploy.
COSTO_POR_CENEFA = 45.0


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

    fila = (await db.execute(
        select(
            func.count().label("corridas"),
            func.coalesce(func.sum(total), 0).label("cenefas"),
            func.coalesce(func.sum(correctas), 0).label("correctas"),
            func.coalesce(func.sum(avisos), 0).label("avisos"),
            func.coalesce(func.sum(criticos), 0).label("criticos"),
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
        ).where(*cond).group_by(mes).order_by(mes)
    )).all()

    por_plantilla = (await db.execute(
        select(
            func.coalesce(CenefaJob.template_nombre, "").label("plantilla"),
            func.count().label("corridas"),
            func.coalesce(func.sum(total), 0).label("cenefas"),
            func.coalesce(func.sum(correctas), 0).label("correctas"),
        )
        .where(*cond)
        .group_by(CenefaJob.template_nombre)
        .order_by(func.coalesce(func.sum(total), 0).desc())
    )).all()

    def bloque(r) -> dict[str, Any]:
        return {
            "corridas":  r.corridas,
            "cenefas":   r.cenefas,
            "correctas": r.correctas,
            "avisos":    getattr(r, "avisos", 0),
            "criticos":  getattr(r, "criticos", 0),
            "costo":     round(r.cenefas * costo, 2),
            "costo_correctas": round(r.correctas * costo, 2),
        }

    return {
        "costo_unitario": costo,
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
                      "No se pudieron armar", "Valor total"])
    ws.cell(row=6, column=1, value=t["corridas"])
    ws.cell(row=6, column=2, value=t["cenefas"])
    ws.cell(row=6, column=3, value=t["correctas"])
    ws.cell(row=6, column=4, value=t["avisos"])
    ws.cell(row=6, column=5, value=t["criticos"])
    ws.cell(row=6, column=6, value=t["costo"]).number_format = dinero

    fila = 8
    for titulo, clave, etiqueta in (("Por mes", "por_mes", "mes"),
                                    ("Por plantilla", "por_plantilla", "plantilla")):
        ws.cell(row=fila, column=1, value=titulo).font = Font(bold=True)
        encabezar(ws, fila + 1, [etiqueta.capitalize(), "Corridas", "Cenefas",
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

    for col, ancho in zip("ABCDEF", (34, 12, 12, 12, 20, 16)):
        ws.column_dimensions[col].width = ancho

    # ── Detalle ────────────────────────────────────────────────────────────
    ws2 = wb.create_sheet("Detalle")
    cols = ["Fecha", "Plantilla", "Excel", "Formato", "Cenefas", "Correctas",
            "Con avisos", "No se pudieron armar", "Valor"]
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
    for c, ancho in enumerate((17, 34, 34, 10, 10, 10, 12, 21, 14), 1):
        ws2.column_dimensions[get_column_letter(c)].width = ancho
    ws2.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
