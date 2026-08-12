"""Orquestación del flujo subir -> revisar -> confirmar/descartar. Separado
de extraccion.py (que solo sabe hablar con Claude) para que la lógica de
negocio de Facturación no dependa del detalle de cómo se arma el prompt."""
import asyncio

from sqlalchemy import func, select

from app.models.facturacion_canje import FacturacionCanje
from app.models.facturacion_cuenta import FacturacionCuenta
from app.models.facturacion_documento import FacturacionDocumento
from app.models.facturacion_movimiento import FacturacionMovimiento
from app.services.facturacion.cuentas import listar_cuentas
from app.services.facturacion.extraccion import extraer_factura_raw, registrar_uso_extraccion

_ESTADO_PENDIENTE = "pendiente_revision"


async def crear_documentos_y_extraer(
    db, archivos: list[tuple[str, str, bytes]], user_id: int
) -> list[FacturacionDocumento]:
    """archivos: [(filename, content_type, file_bytes), ...] -- procesa un
    lote de PDFs de una sola carga (uno o varios). Las llamadas a Claude
    corren en paralelo (asyncio.gather) porque son independientes entre sí
    y son la parte lenta; los inserts a la base y el logueo de uso de IA
    quedan secuenciales después, sobre la misma sesión -- AsyncSession no
    soporta uso concurrente desde varias corutinas a la vez, así que la
    parte que sí toca la base nunca se paraleliza, solo la llamada a Claude.

    Un PDF que DogTi no puede leer (borroso, no es una factura, error de
    red) NUNCA tira el resto del lote abajo -- esa fila queda con
    extraction_error seteado, para que el usuario la complete a mano en la
    revisión, igual que si fuera la única factura de la carga."""
    cuentas_activas = [c.nombre for c in await listar_cuentas(db)]

    resultados = await asyncio.gather(
        *[extraer_factura_raw(file_bytes, cuentas_activas) for _, _, file_bytes in archivos],
        return_exceptions=True,
    )

    documentos: list[FacturacionDocumento] = []
    for (filename, content_type, file_bytes), resultado in zip(archivos, resultados):
        documento = FacturacionDocumento(
            filename=filename,
            content_type=content_type or "application/pdf",
            file_size_bytes=len(file_bytes),
            file_bytes=file_bytes,
            status=_ESTADO_PENDIENTE,
            uploaded_by_id=user_id,
        )
        db.add(documento)
        if isinstance(resultado, Exception):
            documento.extraction_error = str(resultado)[:500]
        else:
            data, input_tokens, output_tokens = resultado
            documento.extraction_raw = data
            await registrar_uso_extraccion(db, user_id, input_tokens, output_tokens)
        documentos.append(documento)

    return documentos


def confirmar_documento(db, documento: FacturacionDocumento, tipo: str, payload: dict, user_id: int):
    """tipo: "movimiento" | "canje". payload trae los campos ya editados por
    el usuario en la revisión (ver ConfirmarDocumentoRequest en la ruta),
    cuenta_id incluido -- siempre requerido para un registro nuevo. No
    commitea -- el caller es dueño de la transacción."""
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
            cuenta_id=payload["cuenta_id"],
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
            cuenta_id=payload["cuenta_id"],
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
        "cuenta_id": m.cuenta_id,
        "documento_id": m.documento_id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


_SIN_CUENTA_LABEL = "Sin cuenta"


async def obtener_dashboard(
    db, limit: int = 50, offset: int = 0,
    presupuesto_cuenta_id: int | None = None,
    canjes_cuenta_id: int | None = None,
) -> dict:
    """Presupuesto y canjes se filtran cada uno por SU propia cuenta (dos
    selectores independientes en el dashboard -- ver plan) y default a la
    primera cuenta activa si no se pasa ninguna. La torta general nunca
    filtra: siempre muestra el total de TODAS las cuentas, desglosado una
    por una (incluye cuentas ya desactivadas si tienen historial, para no
    hacer desaparecer plata vieja del total solo porque la cuenta se
    desactivó -- ver FacturacionCuenta).

    Simplificación conocida: los totales suman `monto`/`valor` de todas las
    filas sin distinguir moneda (UYU/USD mezclados como si fueran el mismo
    número) -- cada movimiento individual sí guarda su moneda real, pero el
    agregado para las tortas asume que la inmensa mayoría es UYU (default de
    la extracción). Separar por moneda o convertir a un tipo de cambio queda
    para cuando haga falta de verdad, no antes."""
    cuentas_activas = await listar_cuentas(db, incluir_inactivas=False)
    cuentas_dict = [{"id": c.id, "nombre": c.nombre} for c in cuentas_activas]

    if presupuesto_cuenta_id is None and cuentas_activas:
        presupuesto_cuenta_id = cuentas_activas[0].id
    if canjes_cuenta_id is None and cuentas_activas:
        canjes_cuenta_id = cuentas_activas[0].id

    # ── Presupuesto (una cuenta a la vez) ───────────────────────────────
    if presupuesto_cuenta_id is not None:
        entradas_total = (await db.execute(
            select(func.coalesce(func.sum(FacturacionMovimiento.monto), 0))
            .where(FacturacionMovimiento.tipo == "entrada", FacturacionMovimiento.cuenta_id == presupuesto_cuenta_id)
        )).scalar_one()
        salidas_total = (await db.execute(
            select(func.coalesce(func.sum(FacturacionMovimiento.monto), 0))
            .where(FacturacionMovimiento.tipo == "salida", FacturacionMovimiento.cuenta_id == presupuesto_cuenta_id)
        )).scalar_one()
        movimientos_total = (await db.execute(
            select(func.count()).select_from(FacturacionMovimiento)
            .where(FacturacionMovimiento.cuenta_id == presupuesto_cuenta_id)
        )).scalar_one()
        movimientos_rows = (await db.execute(
            select(FacturacionMovimiento)
            .where(FacturacionMovimiento.cuenta_id == presupuesto_cuenta_id)
            .order_by(FacturacionMovimiento.fecha.desc(), FacturacionMovimiento.id.desc())
            .limit(limit).offset(offset)
        )).scalars().all()
    else:
        entradas_total = salidas_total = 0
        movimientos_total = 0
        movimientos_rows = []

    entradas_total = float(entradas_total)
    salidas_total = float(salidas_total)

    # ── Canjes (una cuenta a la vez, por estado) ────────────────────────
    if canjes_cuenta_id is not None:
        canjes_rows = (await db.execute(
            select(FacturacionCanje.estado, func.coalesce(func.sum(FacturacionCanje.valor), 0))
            .where(FacturacionCanje.cuenta_id == canjes_cuenta_id)
            .group_by(FacturacionCanje.estado)
        )).all()
    else:
        canjes_rows = []
    canjes_por_estado = {estado: float(total) for estado, total in canjes_rows}

    # ── General: todas las cuentas juntas, sin filtrar ──────────────────
    todas_las_cuentas = await listar_cuentas(db, incluir_inactivas=True)
    nombre_por_cuenta = {c.id: c.nombre for c in todas_las_cuentas}

    entradas_por_cuenta_rows = (await db.execute(
        select(FacturacionMovimiento.cuenta_id, func.sum(FacturacionMovimiento.monto))
        .where(FacturacionMovimiento.tipo == "entrada")
        .group_by(FacturacionMovimiento.cuenta_id)
    )).all()
    salidas_por_cuenta_rows = (await db.execute(
        select(FacturacionMovimiento.cuenta_id, func.sum(FacturacionMovimiento.monto))
        .where(FacturacionMovimiento.tipo == "salida")
        .group_by(FacturacionMovimiento.cuenta_id)
    )).all()
    canjes_valor_por_cuenta_rows = (await db.execute(
        select(FacturacionCanje.cuenta_id, func.sum(FacturacionCanje.valor))
        .group_by(FacturacionCanje.cuenta_id)
    )).all()

    entradas_por_cuenta = {cid: float(m) for cid, m in entradas_por_cuenta_rows}
    salidas_por_cuenta = {cid: float(m) for cid, m in salidas_por_cuenta_rows}
    canjes_valor_por_cuenta = {cid: float(m) for cid, m in canjes_valor_por_cuenta_rows}

    ids_con_movimiento = set(entradas_por_cuenta) | set(salidas_por_cuenta) | set(canjes_valor_por_cuenta)
    por_cuenta = []
    total_general = 0.0
    for cid in ids_con_movimiento:
        monto = (
            entradas_por_cuenta.get(cid, 0.0) - salidas_por_cuenta.get(cid, 0.0)
            + canjes_valor_por_cuenta.get(cid, 0.0)
        )
        total_general += monto
        por_cuenta.append({
            "cuenta_id": cid,
            "cuenta": nombre_por_cuenta.get(cid, _SIN_CUENTA_LABEL) if cid is not None else _SIN_CUENTA_LABEL,
            "monto": monto,
        })
    por_cuenta.sort(key=lambda x: x["monto"], reverse=True)

    return {
        "cuentas": cuentas_dict,
        "presupuesto": {
            "cuenta_id": presupuesto_cuenta_id,
            "entradas_total": entradas_total,
            "salidas_total": salidas_total,
            "saldo": entradas_total - salidas_total,
            "movimientos": [_movimiento_to_dict(m) for m in movimientos_rows],
            "movimientos_total": movimientos_total,
        },
        "canjes": {
            "cuenta_id": canjes_cuenta_id,
            "total_valor": sum(canjes_por_estado.values()),
            "por_estado": canjes_por_estado,
        },
        "general": {
            "total": total_general,
            "por_cuenta": por_cuenta,
        },
    }


_QUERY_LIMIT = 20  # tope de filas devueltas a DogTi por consulta -- el chat responde
# en prosa, no necesita (ni le conviene, por tokens) una lista larga; el total
# agregado sí se calcula sobre TODAS las filas que matchean, no solo las que se listan.


async def buscar_movimientos_filtrados(
    db, proveedor: str | None = None, desde: str | None = None, hasta: str | None = None,
    tipo: str | None = None, cuenta_id: int | None = None,
) -> dict:
    """Consulta de solo lectura para el chat de DogTi (ver dogti_agent.py) --
    nunca escribe nada. proveedor: substring, sin distinguir mayúsculas.
    desde/hasta: fechas YYYY-MM-DD, inclusive. tipo: "entrada" | "salida"."""
    filtros = []
    if proveedor:
        filtros.append(FacturacionMovimiento.proveedor_marca.ilike(f"%{proveedor}%"))
    if desde:
        filtros.append(FacturacionMovimiento.fecha >= desde)
    if hasta:
        filtros.append(FacturacionMovimiento.fecha <= hasta)
    if tipo in ("entrada", "salida"):
        filtros.append(FacturacionMovimiento.tipo == tipo)
    if cuenta_id is not None:
        filtros.append(FacturacionMovimiento.cuenta_id == cuenta_id)

    total_row = (await db.execute(
        select(func.count(), func.coalesce(func.sum(FacturacionMovimiento.monto), 0)).where(*filtros)
    )).one()
    cantidad, total_monto = total_row

    rows = (await db.execute(
        select(FacturacionMovimiento).where(*filtros)
        .order_by(FacturacionMovimiento.fecha.desc(), FacturacionMovimiento.id.desc())
        .limit(_QUERY_LIMIT)
    )).scalars().all()

    return {
        "cantidad_total": cantidad,
        "monto_total": float(total_monto),
        "movimientos": [_movimiento_to_dict(m) for m in rows],
        "mostrando": f"los {len(rows)} más recientes de {cantidad}" if cantidad > len(rows) else "todos",
    }


def _canje_to_dict(c: FacturacionCanje) -> dict:
    return {
        "id": c.id,
        "marca_proveedor": c.marca_proveedor,
        "valor": float(c.valor),
        "moneda": c.moneda,
        "estado": c.estado,
        "vigencia_desde": c.vigencia_desde.isoformat() if c.vigencia_desde else None,
        "vigencia_hasta": c.vigencia_hasta.isoformat() if c.vigencia_hasta else None,
        "descripcion": c.descripcion,
        "cuenta_id": c.cuenta_id,
    }


async def buscar_canjes_filtrados(db, estado: str | None = None, cuenta_id: int | None = None) -> dict:
    """Ídem buscar_movimientos_filtrados pero sobre FacturacionCanje -- solo
    lectura, para el chat de DogTi."""
    filtros = []
    if estado in ("pendiente", "activo", "cerrado"):
        filtros.append(FacturacionCanje.estado == estado)
    if cuenta_id is not None:
        filtros.append(FacturacionCanje.cuenta_id == cuenta_id)

    total_row = (await db.execute(
        select(func.count(), func.coalesce(func.sum(FacturacionCanje.valor), 0)).where(*filtros)
    )).one()
    cantidad, total_valor = total_row

    rows = (await db.execute(
        select(FacturacionCanje).where(*filtros)
        .order_by(FacturacionCanje.created_at.desc())
        .limit(_QUERY_LIMIT)
    )).scalars().all()

    return {
        "cantidad_total": cantidad,
        "valor_total": float(total_valor),
        "canjes": [_canje_to_dict(c) for c in rows],
        "mostrando": f"los {len(rows)} más recientes de {cantidad}" if cantidad > len(rows) else "todos",
    }
