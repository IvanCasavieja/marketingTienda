"""Orquestación del flujo subir -> revisar -> confirmar/descartar. Separado
de extraccion.py (que solo sabe hablar con Claude) para que la lógica de
negocio de Facturación no dependa del detalle de cómo se arma el prompt."""
from sqlalchemy import func, select

from app.models.facturacion_canje import FacturacionCanje
from app.models.facturacion_documento import FacturacionDocumento
from app.models.facturacion_movimiento import FacturacionMovimiento
from app.services.facturacion.extraccion import extraer_factura

_ESTADO_PENDIENTE = "pendiente_revision"


async def crear_documento_y_extraer(
    db, filename: str, content_type: str, file_bytes: bytes, user_id: int
) -> FacturacionDocumento:
    """Crea la fila del documento y le pide a DogTi que lo lea. Un PDF que
    DogTi no puede leer (borroso, no es una factura, error de red) NUNCA
    tira la request abajo -- la fila se guarda igual con extraction_error
    seteado, para que el usuario complete el resto a mano en la revisión."""
    documento = FacturacionDocumento(
        filename=filename,
        content_type=content_type or "application/pdf",
        file_size_bytes=len(file_bytes),
        file_bytes=file_bytes,
        status=_ESTADO_PENDIENTE,
        uploaded_by_id=user_id,
    )
    db.add(documento)
    await db.flush()

    try:
        documento.extraction_raw = await extraer_factura(file_bytes, db, user_id)
    except Exception as exc:
        documento.extraction_error = str(exc)[:500]

    return documento


def confirmar_documento(db, documento: FacturacionDocumento, tipo: str, payload: dict, user_id: int):
    """tipo: "movimiento" | "canje". payload trae los campos ya editados por
    el usuario en la revisión (ver ConfirmarDocumentoRequest en la ruta).
    No commitea -- el caller es dueño de la transacción."""
    if documento.status != _ESTADO_PENDIENTE:
        raise ValueError("Este documento ya fue procesado")

    if tipo == "movimiento":
        registro = FacturacionMovimiento(
            tipo=payload["tipo_movimiento"],
            monto=payload["monto"],
            moneda=payload.get("moneda") or "UYU",
            concepto=payload["concepto"],
            proveedor_marca=payload.get("proveedor_marca"),
            numero_factura=payload.get("numero_factura"),
            fecha=payload["fecha"],
            documento_id=documento.id,
            created_by_id=user_id,
        )
    elif tipo == "canje":
        registro = FacturacionCanje(
            marca_proveedor=payload.get("proveedor_marca") or payload["concepto"],
            valor=payload["monto"],
            moneda=payload.get("moneda") or "UYU",
            estado=payload.get("estado") or "pendiente",
            vigencia_desde=payload.get("vigencia_desde"),
            vigencia_hasta=payload.get("vigencia_hasta"),
            descripcion=payload.get("concepto"),
            documento_id=documento.id,
            created_by_id=user_id,
        )
    else:
        raise ValueError(f"Tipo inválido: {tipo}")

    db.add(registro)
    documento.status = "confirmado"
    return registro


def descartar_documento(documento: FacturacionDocumento) -> None:
    if documento.status != _ESTADO_PENDIENTE:
        raise ValueError("Este documento ya fue procesado")
    documento.status = "descartado"


def documento_to_dict(documento: FacturacionDocumento) -> dict:
    return {
        "id": documento.id,
        "filename": documento.filename,
        "status": documento.status,
        "extraccion": documento.extraction_raw,
        "extraction_error": documento.extraction_error,
        "created_at": documento.created_at.isoformat() if documento.created_at else None,
    }


_TOP_PROVEEDORES = 5


def _top_con_otros(rows: list[tuple[str, object]]) -> list[dict]:
    """rows: [(proveedor, monto_sum)] ya ordenado desc -- top 5 sueltos +
    el resto agrupado en "Otros", para no saturar la torta con un slice por
    cada proveedor distinto que haya en la base."""
    top = [{"proveedor": p, "monto": float(m)} for p, m in rows[:_TOP_PROVEEDORES]]
    resto = rows[_TOP_PROVEEDORES:]
    if resto:
        top.append({"proveedor": "Otros", "monto": float(sum(m for _, m in resto))})
    return top


def _movimiento_to_dict(m: FacturacionMovimiento) -> dict:
    return {
        "id": m.id,
        "tipo": m.tipo,
        "monto": float(m.monto),
        "moneda": m.moneda,
        "concepto": m.concepto,
        "proveedor_marca": m.proveedor_marca,
        "numero_factura": m.numero_factura,
        "fecha": m.fecha.isoformat(),
        "documento_id": m.documento_id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def obtener_dashboard(db, limit: int = 50, offset: int = 0) -> dict:
    """Totales del presupuesto (entradas/salidas) y de canjes (por estado) +
    un ledger paginado de los movimientos más recientes. Cuenta única de la
    empresa -- sin filtro de cliente/campaña todavía (ver plan).

    Simplificación conocida: los totales suman `monto`/`valor` de todas las
    filas sin distinguir moneda (UYU/USD mezclados como si fueran el mismo
    número) -- cada movimiento individual sí guarda su moneda real, pero el
    agregado para las tortas asume que la inmensa mayoría es UYU (default de
    la extracción). Separar por moneda o convertir a un tipo de cambio queda
    para cuando haga falta de verdad, no antes."""
    entradas_total = (await db.execute(
        select(func.coalesce(func.sum(FacturacionMovimiento.monto), 0))
        .where(FacturacionMovimiento.tipo == "entrada")
    )).scalar_one()
    salidas_total = (await db.execute(
        select(func.coalesce(func.sum(FacturacionMovimiento.monto), 0))
        .where(FacturacionMovimiento.tipo == "salida")
    )).scalar_one()

    canjes_rows = (await db.execute(
        select(FacturacionCanje.estado, func.coalesce(func.sum(FacturacionCanje.valor), 0))
        .group_by(FacturacionCanje.estado)
    )).all()
    canjes_por_estado = {estado: float(total) for estado, total in canjes_rows}
    canjes_total = sum(canjes_por_estado.values())

    movimientos_total = (await db.execute(
        select(func.count()).select_from(FacturacionMovimiento)
    )).scalar_one()
    movimientos_rows = (await db.execute(
        select(FacturacionMovimiento)
        .order_by(FacturacionMovimiento.fecha.desc(), FacturacionMovimiento.id.desc())
        .limit(limit).offset(offset)
    )).scalars().all()

    entradas_total = float(entradas_total)
    salidas_total = float(salidas_total)
    saldo = entradas_total - salidas_total

    salidas_por_proveedor_rows = (await db.execute(
        select(
            func.coalesce(FacturacionMovimiento.proveedor_marca, "Sin proveedor"),
            func.sum(FacturacionMovimiento.monto),
        )
        .where(FacturacionMovimiento.tipo == "salida")
        .group_by(func.coalesce(FacturacionMovimiento.proveedor_marca, "Sin proveedor"))
        .order_by(func.sum(FacturacionMovimiento.monto).desc())
    )).all()

    return {
        "presupuesto": {
            "entradas_total": entradas_total,
            "salidas_total": salidas_total,
            "saldo": saldo,
            "movimientos": [_movimiento_to_dict(m) for m in movimientos_rows],
            "movimientos_total": movimientos_total,
        },
        "canjes": {
            "total_valor": canjes_total,
            "por_estado": canjes_por_estado,
        },
        "general": {
            # Saldo del presupuesto (entradas - salidas) + valor de canjes --
            # "el total sumado entre ambos", no una comparación de volúmenes.
            "total": saldo + canjes_total,
            "salidas_por_proveedor": _top_con_otros(salidas_por_proveedor_rows),
        },
    }
